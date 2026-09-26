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
import os
import threading
import time
import subprocess
import requests
from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR, BASE_DIR, TEMP_DIR, FFMPEG_BIN

CONFIG_FILE = BASE_DIR / "social_config.json"
QUEUE_FILE = BASE_DIR / "publish_queue.json"


def get_social_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
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
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_publish_queue() -> list:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_publish_queue(queue: list) -> None:
    QUEUE_FILE.write_text(json.dumps(queue, indent=2), encoding="utf-8")


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

    file_path = OUTPUT_DIR / clip_filename
    if not file_path.exists():
        return {"success": False, "error": f"Archivo {clip_filename} no encontrado"}

    thumb_file = OUTPUT_DIR / f"{Path(clip_filename).stem}_thumb.jpg"

    payload = {
        "event": "gigaclip_auto_publish",
        "platform": platform,
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "filename": clip_filename,
        "video_url": f"http://localhost:5000/output/{clip_filename}",
        "thumbnail_url": f"http://localhost:5000/output/{thumb_file.name}" if thumb_file.exists() else "",
        "timestamp": datetime.now().isoformat(),
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

    file_path = OUTPUT_DIR / clip_filename
    if not file_path.exists():
        return {"success": False, "error": "Archivo no encontrado"}

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
    queue = get_publish_queue()
    item_id = str(int(time.time() * 1000))[-6:]
    
    item = {
        "id": item_id,
        "clip_filename": clip_filename,
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "platform": platform,
        "publish_at": publish_at_timestamp,
        "publish_at_str": datetime.fromtimestamp(publish_at_timestamp).strftime("%Y-%m-%d %H:%M"),
        "status": "pending",
        "created_at": time.time(),
    }
    queue.append(item)
    save_publish_queue(queue)
    return {"success": True, "item": item}


# Scheduler Worker en segundo plano
def _scheduler_loop():
    while True:
        try:
            now = time.time()
            queue = get_publish_queue()
            changed = False
            for item in queue:
                if item["status"] == "pending" and now >= item["publish_at"]:
                    # Ejecutar publicacion
                    res = publish_to_webhook(
                        clip_filename=item["clip_filename"],
                        title=item["title"],
                        caption=item["caption"],
                        hashtags=item["hashtags"],
                        platform=item["platform"]
                    )
                    if res["success"]:
                        item["status"] = "published"
                        item["published_at"] = now
                    else:
                        item["status"] = "failed"
                        item["error"] = res.get("error", "Fallo")
                    changed = True
            if changed:
                save_publish_queue(queue)
        except Exception:
            pass
        time.sleep(30)


# Iniciar hilo del scheduler
_scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
_scheduler_thread.start()
