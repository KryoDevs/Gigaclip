"""
Interfaz web para el pipeline Ssemble Clone.
Permite procesar videos desde el navegador en vez de la terminal.
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory

from config import OUTPUT_DIR, DOWNLOAD_DIR, TEMP_DIR, NUM_CLIPS

app = Flask(__name__, template_folder="templates", static_folder="static")

# ---- Estado global de los trabajos ----
jobs = {}  # job_id -> {status, progress, logs, clips, error, ...}


def _run_pipeline_job(job_id: str, url: str, num_clips: int, subtitle_style: str = "hormozi"):
    """Ejecuta el pipeline en un thread de fondo y actualiza el estado del job."""
    job = jobs[job_id]
    try:
        job["logs"].append("[1/5] Descargando video...")
        job["progress"] = 10
        from download import download_video
        video = download_video(url)
        source_path = video["path"]
        job["logs"].append(f"      → {video['title']} ({video['duration']}s)")
        job["video_title"] = video.get("title", "video")

        job["logs"].append("[2/5] Transcribiendo (esto puede tardar)...")
        job["progress"] = 25
        from transcribe import transcribe
        transcript = transcribe(source_path)
        job["logs"].append(f"      → {len(transcript['words'])} palabras, {len(transcript['segments'])} segmentos")

        job["logs"].append("[3/5] Eligiendo mejores momentos con LLM local...")
        job["progress"] = 50
        from select_clips import select_clips
        clips = select_clips(transcript["segments"], num_clips=num_clips)
        job["logs"].append(f"      → {len(clips)} clips seleccionados")

        import cv2
        import subprocess
        from crop import crop_to_vertical
        from subtitles import burn_subtitles

        def _words_between(words, start, end):
            return [w for w in words if w["start"] >= start and w["end"] <= end]

        def _extract_segment(source, start, end, out):
            from config import FFMPEG_BIN
            cmd = [FFMPEG_BIN, "-y", "-ss", str(start), "-to", str(end), "-i", source, "-c", "copy", out]
            result = subprocess.run(cmd, capture_output=True)
            if result.returncode != 0:
                cmd[cmd.index("-c") + 1] = "libx264"
                subprocess.run(cmd, check=True)

        final_paths = []
        for i, clip in enumerate(clips, start=1):
            title = clip.get("title", "")
            pct = 50 + int((i / len(clips)) * 45)
            job["progress"] = pct
            job["logs"].append(
                f"[4/5] Procesando clip {i}/{len(clips)}: \"{title}\" "
                f"({clip['start']:.1f}s - {clip['end']:.1f}s)"
            )

            raw_clip_path = str(TEMP_DIR / f"raw_{i}.mp4")
            _extract_segment(source_path, clip["start"], clip["end"], raw_clip_path)

            cropped_noaudio_path = str(TEMP_DIR / f"cropped_{i}.mp4")
            crop_to_vertical(raw_clip_path, cropped_noaudio_path)

            cap = cv2.VideoCapture(cropped_noaudio_path)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap.release()

            clip_words = _words_between(transcript["words"], clip["start"], clip["end"])
            safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:40].strip()
            final_name = f"{i:02d}_{safe_title or f'clip_{i}'}.mp4"
            final_path = str(OUTPUT_DIR / final_name)

            burn_subtitles(
                video_no_audio=cropped_noaudio_path,
                original_source=source_path,
                clip_start=clip["start"],
                clip_end=clip["end"],
                words_in_clip=clip_words,
                video_w=w, video_h=h,
                final_output=final_path,
                style=subtitle_style,
            )
            final_paths.append({
                "filename": final_name,
                "title": title,
                "start": clip["start"],
                "end": clip["end"],
                "score": clip.get("score", 0),
                "hook": clip.get("hook", ""),
            })

        job["clips"] = final_paths
        job["progress"] = 100
        job["status"] = "done"
        job["logs"].append(f"[5/5] ¡Listo! {len(final_paths)} clips generados.")

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["logs"].append(f"❌ Error: {e}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json()
    url = data.get("url", "").strip()
    num_clips = int(data.get("num_clips", NUM_CLIPS))
    subtitle_style = data.get("subtitle_style", "hormozi")

    if not url:
        return jsonify({"error": "URL es requerida"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "logs": [],
        "clips": [],
        "error": None,
        "video_title": "",
        "url": url,
        "num_clips": num_clips,
        "subtitle_style": subtitle_style,
        "started_at": time.time(),
    }

    thread = threading.Thread(
        target=_run_pipeline_job,
        args=(job_id, url, num_clips, subtitle_style),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job no encontrado"}), 404
    return jsonify(job)


@app.route("/api/jobs")
def api_jobs():
    """Lista todos los jobs (para mostrar historial)."""
    result = []
    for jid, j in jobs.items():
        result.append({
            "job_id": jid,
            "status": j["status"],
            "progress": j["progress"],
            "video_title": j.get("video_title", ""),
            "url": j.get("url", ""),
            "num_clips": j.get("num_clips", 0),
            "clips_count": len(j.get("clips", [])),
        })
    return jsonify(result)


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)


@app.route("/api/output-files")
def list_output_files():
    """Lista los archivos mp4 en la carpeta output."""
    files = []
    if OUTPUT_DIR.exists():
        for f in sorted(OUTPUT_DIR.iterdir()):
            if f.suffix == ".mp4":
                files.append({
                    "filename": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                })
    return jsonify(files)


if __name__ == "__main__":
    print("\n[*] Ssemble Clone - Interfaz Web")
    print("   Abre tu navegador en: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
