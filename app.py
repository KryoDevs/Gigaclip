"""
Servidor API y Backend Web Pro de Gigaclip.
Maneja pipeline asincrono, ajuste preciso de timestamps por timeline,
re-renderizado en 1080p y generacion de metadatos sociales.
"""
import os
import hmac
import secrets
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory, session

from config import (
    OUTPUT_DIR,
    DOWNLOAD_DIR,
    TEMP_DIR,
    NUM_CLIPS,
    DEFAULT_QUALITY,
    CLIP_MIN_SECONDS,
    CLIP_MAX_SECONDS,
)
from pipeline import run as run_pipeline, _render_clip_fast
from social_metadata import generate_social_metadata
from security import (
    ValidationError,
    validate_process_options,
    resolve_managed_video,
    validate_clip_range,
    validate_words,
    SUBTITLE_STYLES,
    CROP_MODES,
    QUALITIES,
    verify_media_link,
)
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2 GB max upload
app.secret_key = os.environ.get("GIGACLIP_SESSION_SECRET") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("GIGACLIP_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}


def _valid_signed_media_link() -> bool:
    key = os.environ.get("GIGACLIP_API_KEY", "")
    filename = request.view_args.get("filename", "") if request.view_args else ""
    if not key or not filename or Path(filename).name != filename:
        return False
    return verify_media_link(
        filename=filename,
        expires=request.args.get("expires", ""),
        signature=request.args.get("signature", ""),
        secret=key,
    )


@app.before_request
def require_api_key_when_configured():
    expected_key = os.environ.get("GIGACLIP_API_KEY", "")
    protected_path = request.path.startswith("/api/") or request.path.startswith("/output/")
    signed_media = request.path.startswith("/output/") and _valid_signed_media_link()
    if (expected_key and protected_path and request.endpoint != "api_auth" and
            not signed_media and not session.get("api_authenticated")):
        return jsonify({"error": "Autenticación requerida"}), 401


@app.route("/api/auth", methods=["POST"])
def api_auth():
    expected_key = os.environ.get("GIGACLIP_API_KEY", "")
    if not expected_key:
        return jsonify({"success": True, "auth_required": False})
    if session.get("api_authenticated"):
        return jsonify({"success": True})
    data = request.get_json(silent=True)
    supplied_key = data.get("key", "") if isinstance(data, dict) else ""
    if not isinstance(supplied_key, str) or not hmac.compare_digest(supplied_key, expected_key):
        return jsonify({"error": "Clave de acceso incorrecta"}), 401
    session["api_authenticated"] = True
    return jsonify({"success": True})

jobs = {}  # job_id -> {status, progress, logs, clips, transcript, error, ...}


def _prune_jobs(max_jobs: int = 100, max_age_seconds: int = 12 * 60 * 60) -> None:
    """Bound in-memory job history without removing active work."""
    now = time.time()
    finished = sorted(
        ((job.get("created_at", now), job_id) for job_id, job in jobs.items()
         if job.get("status") in {"done", "error"}),
        key=lambda pair: pair[0],
    )
    for created_at, job_id in finished:
        if now - created_at > max_age_seconds or len(jobs) > max_jobs:
            jobs.pop(job_id, None)


UPLOAD_DIR = TEMP_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def _run_job_thread(job_id: str, url: str, local_path: str, num_clips: int, subtitle_style: str,
                    crop_mode: str, quality: str, min_seconds: int, max_seconds: int, extraction_strategy: str,
                    watermark: str, hw_accel: str):
    job = jobs[job_id]
    
    def callback(msg, pct):
        job["logs"].append(msg)
        if pct is not None:
            job["progress"] = pct

    try:
        result = run_pipeline(
            url=url,
            local_path=local_path,
            num_clips=num_clips,
            subtitle_style=subtitle_style,
            crop_mode=crop_mode,
            quality=quality,
            min_seconds=min_seconds,
            max_seconds=max_seconds,
            extraction_strategy=extraction_strategy,
            watermark=watermark,
            hw_accel=hw_accel,
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


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    safe_name = secure_filename(file.filename)
    if not safe_name or Path(safe_name).suffix.lower() not in {
        ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg"
    }:
        return jsonify({"error": "Formato de video no compatible"}), 400
    # UUID avoids same-second collisions and never trusts a client-supplied path.
    filepath = UPLOAD_DIR / f"{uuid.uuid4().hex}_{safe_name}"
    try:
        file.save(str(filepath))
    except Exception:
        filepath.unlink(missing_ok=True)
        raise
    return jsonify({"success": True, "local_path": str(filepath)})


@app.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo de la solicitud debe ser un objeto JSON"}), 400
    defaults = {
        "num_clips": NUM_CLIPS,
        "min_seconds": CLIP_MIN_SECONDS,
        "max_seconds": CLIP_MAX_SECONDS,
        "quality": DEFAULT_QUALITY,
    }
    try:
        options = validate_process_options(data, defaults)
        if options["local_path"]:
            options["local_path"] = str(resolve_managed_video(
                options["local_path"], (UPLOAD_DIR, DOWNLOAD_DIR)
            ))
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    url = options["url"]
    local_path = options["local_path"]
    num_clips = options["num_clips"]
    subtitle_style = options["subtitle_style"]
    crop_mode = options["crop_mode"]
    quality = options["quality"]
    min_seconds = options["min_seconds"]
    max_seconds = options["max_seconds"]
    extraction_strategy = options["extraction_strategy"]
    watermark = options["watermark"]
    hw_accel = options["hw_accel"]

    _prune_jobs()
    job_id = uuid.uuid4().hex
    jobs[job_id] = {
        "status": "running",
        "progress": 5,
        "logs": ["[*] Iniciando motor Pro de Gigaclip..."],
        "clips": [],
        "transcript": {},
        "video_info": {},
        "error": None,
        "url": url,
        "local_path": local_path,
        "num_clips": num_clips,
        "subtitle_style": subtitle_style,
        "crop_mode": crop_mode,
        "quality": quality,
        "min_seconds": min_seconds,
        "max_seconds": max_seconds,
        "extraction_strategy": extraction_strategy,
        "watermark": watermark,
        "hw_accel": hw_accel,
        "created_at": time.time(),
    }

    thread = threading.Thread(
        target=_run_job_thread,
        args=(job_id, url, local_path, num_clips, subtitle_style, crop_mode, quality, min_seconds, max_seconds, extraction_strategy, watermark, hw_accel),
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
    """Ajuste fino de timeline, re-renderizado y cambio de subtítulos."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo de la solicitud debe ser un objeto JSON"}), 400
    try:
        source = resolve_managed_video(data.get("source_path", ""), (UPLOAD_DIR, DOWNLOAD_DIR))
        start, end = validate_clip_range(data.get("start", 0), data.get("end", 10))
        subtitle_style = data.get("subtitle_style", "hormozi")
        crop_mode = data.get("crop_mode", "face_track")
        quality = data.get("quality", DEFAULT_QUALITY)
        if subtitle_style not in SUBTITLE_STYLES:
            raise ValidationError("subtitle_style no es válido")
        if crop_mode not in CROP_MODES:
            raise ValidationError("crop_mode no es válido")
        if quality not in QUALITIES:
            raise ValidationError("quality no es válida")
        title = str(data.get("title", "clip_editado"))[:120]
        words = validate_words(data.get("words", []), start, end)
    except ValidationError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:35].strip() or "clip_editado"
        final_name = f"edit_{safe_title}_{uuid.uuid4().hex[:8]}.mp4"
        final_path = str(OUTPUT_DIR / final_name)

        _render_clip_fast(
            source_path=str(source),
            start=start,
            end=end,
            words_in_clip=words,
            final_output=final_path,
            style=subtitle_style,
            crop_mode=crop_mode,
            quality=quality,
        )

        snippet = " ".join(w["word"] for w in words[:35])
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
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400
    title = data.get("title", "")
    snippet = data.get("snippet", "")
    if not isinstance(title, str) or not isinstance(snippet, str):
        return jsonify({"error": "Título y fragmento deben ser texto"}), 400
    metadata = generate_social_metadata(title[:200], snippet[:2000])
    return jsonify(metadata)


@app.route("/api/social/test-llm", methods=["GET"])
def api_test_llm():
    from select_clips import test_llm_connection
    res = test_llm_connection()
    return jsonify(res)

@app.route("/api/social/settings", methods=["GET", "POST"])
def api_social_settings():
    from social_publisher import get_social_config, save_social_config
    if request.method == "POST":
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400
        allowed = {"llm_provider", "llm_api_key", "llm_model", "webhook_url", "telegram_bot_token", "telegram_chat_id"}
        if set(data) - allowed:
            return jsonify({"error": "La solicitud contiene campos no permitidos"}), 400
        current = get_social_config()
        merged = dict(current)
        for key in allowed:
            merged.setdefault(key, "")
        for key, value in data.items():
            # Blank secret inputs mean “keep existing”, avoiding secret disclosure on GET.
            if key in {"llm_api_key", "telegram_bot_token", "telegram_chat_id", "webhook_url"} and value == "":
                continue
            if not isinstance(value, str) or len(value) > 4096:
                return jsonify({"error": f"El campo {key} no es válido"}), 400
            merged[key] = value.strip()
        provider = merged.get("llm_provider") or "ollama"
        if provider not in {"openai", "deepseek", "ollama"}:
            return jsonify({"error": "Proveedor LLM no válido"}), 400
        save_social_config(merged)
        return jsonify({"success": True, "message": "Ajustes sociales guardados"})
    stored = get_social_config()
    # Return only UI fields; never expose other integration credentials in the file.
    config = {key: stored.get(key, "") for key in ("llm_provider", "llm_model")}
    for key in ("llm_api_key", "telegram_bot_token", "telegram_chat_id", "webhook_url"):
        config[key] = ""
        config[f"{key}_configured"] = bool(stored.get(key))
    return jsonify(config)


@app.route("/api/publish/direct", methods=["POST"])
def api_publish_direct():
    from social_publisher import publish_to_webhook
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400
    clip_filename = data.get("filename", "")
    title = data.get("title", "")
    caption = data.get("caption", "")
    hashtags = data.get("hashtags", "")
    platform = data.get("platform", "all")
    if not all(isinstance(value, str) for value in (clip_filename, title, caption, hashtags, platform)):
        return jsonify({"error": "Los datos de publicación no son válidos"}), 400

    res = publish_to_webhook(
        clip_filename=clip_filename,
        title=title,
        caption=caption,
        hashtags=hashtags,
        platform=platform,
    )
    return jsonify(res)


@app.route("/api/publish/telegram", methods=["POST"])
def api_publish_telegram():
    from social_publisher import publish_to_telegram
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400
    clip_filename = data.get("filename", "")
    caption = data.get("caption", "")
    if not isinstance(clip_filename, str) or not isinstance(caption, str):
        return jsonify({"error": "Los datos de publicación no son válidos"}), 400

    res = publish_to_telegram(clip_filename=clip_filename, caption=caption)
    return jsonify(res)


@app.route("/api/publish/schedule", methods=["POST"])
def api_publish_schedule():
    from social_publisher import schedule_post
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON"}), 400
    clip_filename = data.get("filename", "")
    title = data.get("title", "")
    caption = data.get("caption", "")
    hashtags = data.get("hashtags", "")
    platform = data.get("platform", "all")
    try:
        publish_at = float(data.get("publish_at", time.time() + 3600))
    except (TypeError, ValueError, OverflowError):
        return jsonify({"error": "Fecha de publicación no válida"}), 400
    if not all(isinstance(value, str) for value in (clip_filename, title, caption, hashtags, platform)):
        return jsonify({"error": "Los datos de publicación no son válidos"}), 400

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
    from social_publisher import start_scheduler
    start_scheduler()
    print("\n[*] Gigaclip Pro - Servidor Activo")
    print("   Abre en tu navegador: http://localhost:5000\n")
    print("   Aviso: no expongas este servidor a Internet sin autenticación/proxy seguro.\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
