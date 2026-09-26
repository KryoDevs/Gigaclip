"""
Servidor API y Backend Web Pro de Gigaclip.
Maneja pipeline asincrono, ajuste preciso de timestamps por timeline,
re-renderizado en 1080p y generacion de metadatos sociales.
"""
import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory

from config import (
    OUTPUT_DIR,
    DOWNLOAD_DIR,
    TEMP_DIR,
    NUM_CLIPS,
    BASE_DIR,
    FFMPEG_BIN,
    DEFAULT_QUALITY,
    CLIP_MIN_SECONDS,
    CLIP_MAX_SECONDS,
)
from pipeline import run as run_pipeline, _render_clip_fast
from social_metadata import generate_social_metadata

app = Flask(__name__, template_folder="templates", static_folder="static")

jobs = {}  # job_id -> {status, progress, logs, clips, transcript, error, ...}


def _run_job_thread(job_id: str, url: str, num_clips: int, subtitle_style: str,
                    crop_mode: str, quality: str, min_seconds: int, max_seconds: int):
    job = jobs[job_id]
    
    def callback(msg, pct):
        job["logs"].append(msg)
        if pct is not None:
            job["progress"] = pct

    try:
        result = run_pipeline(
            url=url,
            num_clips=num_clips,
            subtitle_style=subtitle_style,
            crop_mode=crop_mode,
            quality=quality,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
            progress_callback=callback
        )
        job["clips"] = result["clips"]
        job["transcript"] = result.get("transcript", {})
        job["video_info"] = result.get("video_info", {})
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
    quality = data.get("quality", DEFAULT_QUALITY)
    min_seconds = int(data.get("min_seconds", CLIP_MIN_SECONDS))
    max_seconds = int(data.get("max_seconds", CLIP_MAX_SECONDS))

    if not url:
        return jsonify({"error": "La URL del video es obligatoria"}), 400

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "running",
        "progress": 5,
        "logs": ["[*] Iniciando motor Pro de Gigaclip..."],
        "clips": [],
        "transcript": {},
        "video_info": {},
        "error": None,
        "url": url,
        "num_clips": num_clips,
        "subtitle_style": subtitle_style,
        "crop_mode": crop_mode,
        "quality": quality,
        "min_seconds": min_seconds,
        "max_seconds": max_seconds,
        "created_at": time.time(),
    }

    thread = threading.Thread(
        target=_run_job_thread,
        args=(job_id, url, num_clips, subtitle_style, crop_mode, quality, min_seconds, max_seconds),
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
    """Ajuste fino de timeline, re-renderizado instantaneo en 1080p y cambio de subtitulos."""
    data = request.get_json() or {}
    source_path = data.get("source_path")
    start = float(data.get("start", 0))
    end = float(data.get("end", 10))
    subtitle_style = data.get("subtitle_style", "hormozi")
    crop_mode = data.get("crop_mode", "face_track")
    quality = data.get("quality", "1080p")
    title = data.get("title", "clip_editado")
    words = data.get("words", [])

    if not source_path or not Path(source_path).exists():
        return jsonify({"error": "Archivo de video original no encontrado"}), 400

    if end <= start:
        return jsonify({"error": "El tiempo de fin debe ser mayor al de inicio"}), 400

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
            quality=quality,
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
            "quality": quality,
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


@app.route("/api/social/settings", methods=["GET", "POST"])
def api_social_settings():
    from social_publisher import get_social_config, save_social_config
    if request.method == "POST":
        data = request.get_json() or {}
        save_social_config(data)
        return jsonify({"success": True, "message": "Ajustes sociales guardados"})
    return jsonify(get_social_config())


@app.route("/api/publish/direct", methods=["POST"])
def api_publish_direct():
    from social_publisher import publish_to_webhook
    data = request.get_json() or {}
    clip_filename = data.get("filename", "")
    title = data.get("title", "")
    caption = data.get("caption", "")
    hashtags = data.get("hashtags", "")
    platform = data.get("platform", "all")
    webhook_url = data.get("webhook_url", None)

    res = publish_to_webhook(
        clip_filename=clip_filename,
        title=title,
        caption=caption,
        hashtags=hashtags,
        platform=platform,
        custom_webhook=webhook_url
    )
    return jsonify(res)


@app.route("/api/publish/telegram", methods=["POST"])
def api_publish_telegram():
    from social_publisher import publish_to_telegram
    data = request.get_json() or {}
    clip_filename = data.get("filename", "")
    caption = data.get("caption", "")

    res = publish_to_telegram(clip_filename=clip_filename, caption=caption)
    return jsonify(res)


@app.route("/api/publish/schedule", methods=["POST"])
def api_publish_schedule():
    from social_publisher import schedule_post
    data = request.get_json() or {}
    clip_filename = data.get("filename", "")
    title = data.get("title", "")
    caption = data.get("caption", "")
    hashtags = data.get("hashtags", "")
    platform = data.get("platform", "all")
    publish_at = float(data.get("publish_at", time.time() + 3600))

    res = schedule_post(
        clip_filename=clip_filename,
        title=title,
        caption=caption,
        hashtags=hashtags,
        platform=platform,
        publish_at_timestamp=publish_at
    )
    return jsonify(res)


@app.route("/api/publish/queue", methods=["GET"])
def api_publish_queue():
    from social_publisher import get_publish_queue
    return jsonify(get_publish_queue())


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
    print("\n[*] Gigaclip Pro - Servidor Activo")
    print("   Abre en tu navegador: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
