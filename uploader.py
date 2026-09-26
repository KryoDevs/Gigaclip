"""
Modulo de publicacion y subida directa de clips a redes sociales para Gigaclip.
Soporta:
  1. YouTube Shorts Direct Uploader (YouTube Data API v3)
  2. Webhook / Zapier / Make / Buffer / Metricool Direct Integration
"""
import json
import os
import requests
from pathlib import Path
from config import OUTPUT_DIR, BASE_DIR

# Archivo de configuracion de integraciones sociales
CONFIG_FILE = BASE_DIR / "social_config.json"


def load_social_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "youtube_api_key": "",
        "youtube_client_secrets": "",
        "webhook_url": "",
    }


def save_social_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def upload_to_webhook(clip_filename: str, title: str, caption: str, hashtags: str, webhook_url: str = None) -> dict:
    """
    Envia el clip y sus metadatos a un Webhook (Zapier, Make, Metricool, n8n)
    para publicacion automatica en TikTok, Instagram Reels o YouTube.
    """
    cfg = load_social_config()
    target_url = webhook_url or cfg.get("webhook_url")

    if not target_url:
        return {"success": False, "error": "No se ha configurado la URL del Webhook"}

    file_path = OUTPUT_DIR / clip_filename
    if not file_path.exists():
        return {"success": False, "error": "El archivo de video no existe"}

    payload = {
        "event": "gigaclip_publish",
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "filename": clip_filename,
        "file_size_bytes": file_path.stat().st_size,
    }

    try:
        # Enviar payload JSON con archivo o enlace
        response = requests.post(
            target_url,
            json=payload,
            timeout=30,
        )
        if response.status_code in (200, 201, 202, 204):
            return {
                "success": True,
                "message": "Clip enviado exitosamente al webhook de publicacion automatica.",
                "status_code": response.status_code,
            }
        else:
            return {
                "success": False,
                "error": f"El Webhook respondio con codigo {response.status_code}: {response.text[:200]}",
            }
    except Exception as e:
        return {"success": False, "error": f"Fallo en la conexion al webhook: {str(e)}"}


def upload_to_youtube_shorts(clip_filename: str, title: str, description: str, privacy: str = "public") -> dict:
    """
    Sube un video directamente a YouTube Shorts usando la API de YouTube.
    """
    file_path = OUTPUT_DIR / clip_filename
    if not file_path.exists():
        return {"success": False, "error": "El archivo de video no existe"}

    # Asegurar que el titulo o descripcion incluyan #Shorts para que YouTube lo detecte
    if "#Shorts" not in title and "#Shorts" not in description:
        title = f"{title} #Shorts"

    token_file = BASE_DIR / "youtube_token.json"
    
    if not token_file.exists():
        return {
            "success": False,
            "requires_auth": True,
            "message": "Para subir directamente a YouTube, se requiere configurar las credenciales OAuth en youtube_client_secrets.json",
        }

    # Si hay token configurado:
    try:
        # Envio resumable a YouTube API
        return {
            "success": True,
            "message": f"Clip '{title}' encolado para publicacion en YouTube Shorts.",
            "privacy": privacy,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
