"""
Servidor API y Backend Web de Gigaclip.
Maneja la ejecucion asincrona de pipelines, re-renderizado de clips,
edicion de subtitulos en tiempo real y generacion de metadatos para redes sociales.
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory

from config import OUTPUT_DIR, DOWNLOAD_DIR, TEMP_DIR, NUM_CLIPS, BASE_DIR, FFMPEG_BIN
from pipeline import run as run_pipeline, _render_clip_fast
from social_metadata import generate_social_metadata

app = Flask(__name__, template_folder="templates", static_folder="static")

jobs = {}  # job_id -> {status, progress, logs, clips, error, ...}


def _run_job_thread(job_id: str, url: str, num_clips: int, subtitle_style: str, crop_mode: str):
    job = jobs[job_id]
    
    def callback(msg, pct):
        job["logs"].append(msg)
        if pct is not None:
            job["progress"] = pct

    try:
        clips = run_pipeline(
            url=url,
            num_clips=num_clips,
            subtitle_style=subtitle_style,
            crop_mode=crop_mode,
            progress_callback=callback
        )
        job["clips"] = clips
        job["status"] = "done"
        job["progress"] = 100
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["logs"].append(f"❌ Error en ejecucion: {e}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    num_clips = int(data.get("num_clips", NUM_CLIPS))
    subtitle_style = data.get("subtitle_style", "hormozi")
    crop_mode = data.get("crop_mode", "face_track")

    if not url:
        return jsonify({"error": "La URL del video es obligatoria"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running",
        "progress": 5,
        "logs": ["[*] Iniciando pipeline de Gigaclip..."],
        "clips": [],
        "error": None,
        "url": url,
        "num_clips": num_clips,
        "subtitle_style": subtitle_style,
        "crop_mode": crop_mode,
        "created_at": time.time(),
    }

    thread = threading.Thread(
        target=_run_job_thread,
        args=(job_id, url, num_clips, subtitle_style, crop_mode),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Trabajo no encontrado"}), 404
    return jsonify(job)


@app.route("/api/clip/re-render", methods=["POST"])
def api_rerender_clip():
    """Permite ajustar los puntos de corte o estilo de subtitulos de un clip existente."""
    data = request.get_json() or {}
    source_path = data.get("source_path")
    start = float(data.get("start", 0))
    end = float(data.get("end", 10))
    subtitle_style = data.get("subtitle_style", "hormozi")
    crop_mode = data.get("crop_mode", "face_track")
    title = data.get("title", "clip_editado")
    words = data.get("words", [])

    if not source_path or not Path(source_path).exists():
        return jsonify({"error": "Archivo de video original no encontrado"}), 400

    try:
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:35].strip()
        final_name = f"edit_{safe_title}_{int(time.time())}.mp4"
        final_path = str(OUTPUT_DIR / final_name)

        filtered_words = [w for w in words if w["start"] >= start and w["end"] <= end]

        _render_clip_fast(
            source_path=source_path,
            start=start,
            end=end,
            words_in_clip=filtered_words,
            final_output=final_path,
            style=subtitle_style,
            crop_mode=crop_mode,
        )

        snippet = " ".join(w["word"] for w in filtered_words[:35])
        social = generate_social_metadata(title, snippet)

        return jsonify({
            "success": True,
            "filename": final_name,
            "title": title,
            "start": start,
            "end": end,
            "duration": round(end - start, 1),
            "social": social,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clip/social", methods=["POST"])
def api_generate_social():
    data = request.get_json() or {}
    title = data.get("title", "")
    snippet = data.get("snippet", "")
    metadata = generate_social_metadata(title, snippet)
    return jsonify(metadata)


@app.route("/output/<path:filename>")
def serve_output(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)


@app.route("/api/output-files")
def list_output_files():
    files = []
    if OUTPUT_DIR.exists():
        for f in sorted(OUTPUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.suffix == ".mp4":
                files.append({
                    "filename": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                })
    return jsonify(files)


if __name__ == "__main__":
    print("\n[*] Gigaclip - Servidor Activo")
    print("   Abre en tu navegador: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
