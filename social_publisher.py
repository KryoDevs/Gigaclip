"""
Motor de automatizacion y publicacion directa para Gigaclip.
Soporta:
  - Subida directa a YouTube Shorts (YouTube Data API v3)
  - Publicacion automatica en TikTok e Instagram via Webhooks (Zapier/Make/n8n/Metricool)
  - Auto-Bot de Telegram / Discord para entrega directa al movil
  - Extraccion automatica de Miniaturas (Thumbnails) de alta calidad
  - Cola de programacion (Scheduler) para publicar en horarios estrategicos
"""
import json
import math
import os
import threading
import time
import uuid
import subprocess
import requests
from datetime import datetime
from urllib.parse import quote
from pathlib import Path

from config import OUTPUT_DIR, BASE_DIR, FFMPEG_BIN
from security import sign_media_link

CONFIG_DIR = Path(os.environ.get("GIGACLIP_CONFIG_DIR", str(BASE_DIR)))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "social_config.json"
QUEUE_FILE = CONFIG_DIR / "publish_queue.json"
_config_lock = threading.RLock()
_queue_lock = threading.RLock()


def _public_media_url(base_url: str, filename: str) -> str:
    if not base_url:
        return ""
    url = f"{base_url}/output/{quote(filename)}"
    key = os.environ.get("GIGACLIP_API_KEY", "")
    if key:
        expires = int(time.time()) + 24 * 60 * 60
        signature = sign_media_link(filename, expires, key)
        url += f"?expires={expires}&signature={signature}"
    return url


def _output_video(clip_filename: str) -> Path | None:
    """Return a video only if its name resolves directly inside OUTPUT_DIR."""
    if not isinstance(clip_filename, str) or not clip_filename or Path(clip_filename).name != clip_filename:
        return None
    candidate = (OUTPUT_DIR / clip_filename).resolve()
    try:
        candidate.relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return None
    if not candidate.is_file() or candidate.suffix.lower() != ".mp4":
        return None
    return candidate


def get_social_config() -> dict:
    with _config_lock:
        if CONFIG_FILE.exists():
            try:
                value = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    return value
            except (OSError, json.JSONDecodeError):
                pass
        return {
            "youtube_enabled": False,
            "youtube_privacy": "public",
            "webhook_url": "",
            "telegram_bot_token": "",
            "telegram_chat_id": "",
            "auto_publish_threshold": 88,
        }


def save_social_config(data: dict) -> None:
    with _config_lock:
        _atomic_json_write(CONFIG_FILE, data)


def _atomic_json_write(path: Path, value) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def get_publish_queue() -> list:
    with _queue_lock:
        if QUEUE_FILE.exists():
            try:
                value = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
                return value if isinstance(value, list) else []
            except (OSError, json.JSONDecodeError):
                return []
        return []


def save_publish_queue(queue: list) -> None:
    with _queue_lock:
        _atomic_json_write(QUEUE_FILE, queue)


def extract_thumbnail(clip_path: str, timestamp_sec: float = 1.0) -> str:
    """Extrae un frame de alta resolucion para usar de portada/miniatura."""
    p = Path(clip_path)
    thumb_path = str(OUTPUT_DIR / f"{p.stem}_thumb.jpg")
    cmd = [
        FFMPEG_BIN, "-y",
        "-ss", str(timestamp_sec),
        "-i", clip_path,
        "-vframes", "1",
        "-q:v", "2",
        thumb_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return thumb_path


def publish_to_webhook(clip_filename: str, title: str, caption: str, hashtags: str,
                       platform: str = "all", custom_webhook: str = None) -> dict:
    """Publica en TikTok/Instagram/Shorts a traves de Webhooks de automatizacion."""
    cfg = get_social_config()
    url = custom_webhook or cfg.get("webhook_url")

    if not url:
        return {
            "success": False,
            "error": "No has configurado una URL de Webhook (Zapier, Make, Metricool o n8n)."
        }

    file_path = _output_video(clip_filename)
    if file_path is None:
        return {"success": False, "error": "Archivo de video no encontrado o nombre no válido"}

    thumb_file = OUTPUT_DIR / f"{file_path.stem}_thumb.jpg"
    public_base_url = os.environ.get("GIGACLIP_PUBLIC_URL", "").rstrip("/")
    video_url = _public_media_url(public_base_url, file_path.name)
    thumbnail_url = _public_media_url(public_base_url, thumb_file.name) if thumb_file.is_file() else ""

    payload = {
        "event": "gigaclip_auto_publish",
        "platform": platform,
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "filename": file_path.name,
        "file_size_bytes": file_path.stat().st_size,
        "video_url": video_url,
        "thumbnail_url": thumbnail_url,
        "timestamp": datetime.now().isoformat(),
        "note": "video_url está disponible sólo cuando GIGACLIP_PUBLIC_URL apunta a una instancia accesible por el webhook.",
    }

    try:
        res = requests.post(url, json=payload, timeout=25)
        if res.status_code in (200, 201, 202, 204):
            return {
                "success": True,
                "message": f"¡Clip enviado exitosamente a tu automatizador para {platform.upper()}!",
                "status_code": res.status_code
            }
        else:
            return {
                "success": False,
                "error": f"El Webhook respondio con error {res.status_code}: {res.text[:150]}"
            }
    except Exception as e:
        return {"success": False, "error": f"Error de conexion: {str(e)}"}


def publish_to_telegram(clip_filename: str, caption: str) -> dict:
    """Envia el clip de video directo a tu Telegram listo para publicar desde el movil."""
    cfg = get_social_config()
    token = cfg.get("telegram_bot_token")
    chat_id = cfg.get("telegram_chat_id")

    if not token or not chat_id:
        return {"success": False, "error": "Falta configurar Token de Bot y Chat ID de Telegram"}

    file_path = _output_video(clip_filename)
    if file_path is None:
        return {"success": False, "error": "Archivo de video no encontrado o nombre no válido"}

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    try:
        with open(file_path, "rb") as video_file:
            files = {"video": video_file}
            data = {"chat_id": chat_id, "caption": caption[:1000], "supports_streaming": True}
            res = requests.post(url, files=files, data=data, timeout=120)
            if res.status_code == 200:
                return {"success": True, "message": "¡Video enviado a tu Telegram con éxito!"}
            else:
                return {"success": False, "error": res.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def schedule_post(clip_filename: str, title: str, caption: str, hashtags: str,
                  platform: str, publish_at_timestamp: float) -> dict:
    """Encola un clip para ser publicado automaticamente en una fecha/hora especifica."""
    if _output_video(clip_filename) is None:
        return {"success": False, "error": "Archivo de video no encontrado o nombre no válido"}
    try:
        publish_at_timestamp = float(publish_at_timestamp)
        if not math.isfinite(publish_at_timestamp):
            raise ValueError
        publish_at_text = datetime.fromtimestamp(publish_at_timestamp).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return {"success": False, "error": "Fecha de publicación no válida"}

    with _queue_lock:
        queue = get_publish_queue()
        item = {
            "id": uuid.uuid4().hex[:12],
            "clip_filename": clip_filename,
            "title": str(title)[:200],
            "caption": str(caption)[:2000],
            "hashtags": str(hashtags)[:500],
            "platform": str(platform)[:40],
            "publish_at": publish_at_timestamp,
            "publish_at_str": publish_at_text,
            "status": "pending",
            "created_at": time.time(),
        }
        queue.append(item)
        save_publish_queue(queue)
    return {"success": True, "item": item}


# El scheduler sólo se inicia explícitamente desde el entrypoint, no al importar
# este módulo (importarlo en varios workers duplicaba publicaciones).
_scheduler_thread = None


def _scheduler_loop():
    import logging
    while True:
        try:
            # Serializa la lectura/modificación/escritura con las nuevas programaciones.
            with _queue_lock:
                now = time.time()
                queue = get_publish_queue()
                changed = False
                for item in queue:
                    if item.get("status") == "pending" and now >= item.get("publish_at", float("inf")):
                        result = publish_to_webhook(
                            clip_filename=item.get("clip_filename", ""),
                            title=item.get("title", ""),
                            caption=item.get("caption", ""),
                            hashtags=item.get("hashtags", ""),
                            platform=item.get("platform", "all"),
                        )
                        if result["success"]:
                            item["status"] = "published"
                            item["published_at"] = now
                        else:
                            item["status"] = "failed"
                            item["error"] = result.get("error", "Fallo")
                        changed = True
                if changed:
                    save_publish_queue(queue)
        except Exception:
            logging.exception("Error procesando la cola de publicaciones")
        time.sleep(30)


def start_scheduler() -> None:
    """Start one scheduler thread in this process; safe to call repeatedly."""
    global _scheduler_thread
    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_thread = threading.Thread(target=_scheduler_loop, name="gigaclip-scheduler", daemon=True)
        _scheduler_thread.start()
