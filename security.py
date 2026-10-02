"""Input validation and filesystem boundaries for the web API."""
from __future__ import annotations

import hashlib
import hmac
import math
import time
from pathlib import Path
from urllib.parse import urlparse

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg"}
SUBTITLE_STYLES = {"hormozi", "mrbeast", "ali_abdaal", "karaoke", "minimal", "classic"}
CROP_MODES = {"face_track", "podcast_split", "blur_background"}
QUALITIES = {"720p", "1080p"}
EXTRACTION_STRATEGIES = {"ai_viral", "sequential"}
HW_ACCELERATORS = {"cpu", "nvenc"}


class ValidationError(ValueError):
    """Raised when a request parameter is outside the supported bounds."""


def _integer(value, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise ValidationError(f"{name} debe ser un número entero")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError(f"{name} debe ser un número entero") from exc
    if parsed < minimum or parsed > maximum:
        raise ValidationError(f"{name} debe estar entre {minimum} y {maximum}")
    return parsed


def _choice(value, name: str, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValidationError(f"{name} no es válido")
    return value


def validate_process_options(data: dict, defaults: dict) -> dict:
    """Normalize and bound options accepted by /api/process."""
    num_clips = _integer(data.get("num_clips", defaults["num_clips"]), "num_clips", 1, 20)
    min_seconds = _integer(data.get("min_seconds", defaults["min_seconds"]), "min_seconds", 5, 600)
    max_seconds = _integer(data.get("max_seconds", defaults["max_seconds"]), "max_seconds", 5, 600)
    if min_seconds > max_seconds:
        raise ValidationError("La duración mínima no puede superar a la máxima")

    url = data.get("url", "")
    if not isinstance(url, str):
        raise ValidationError("La URL debe ser texto")
    url = url.strip()
    if url:
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            parsed.port
        except ValueError as exc:
            raise ValidationError("La URL no es válida") from exc
        if (len(url) > 2048 or parsed.scheme not in {"http", "https"} or not hostname
                or parsed.username or parsed.password):
            raise ValidationError("La URL debe ser una dirección HTTP o HTTPS válida, sin credenciales")

    local_path = data.get("local_path", "")
    if not isinstance(local_path, str):
        raise ValidationError("La ruta del archivo debe ser texto")
    local_path = local_path.strip()
    if not url and not local_path:
        raise ValidationError("La URL del video o un archivo local es obligatorio")
    if url and local_path:
        raise ValidationError("Envía una URL o un archivo local, no ambos")

    watermark = data.get("watermark", "")
    if not isinstance(watermark, str) or len(watermark) > 120:
        raise ValidationError("La marca de agua debe tener como máximo 120 caracteres")

    return {
        "url": url,
        "local_path": local_path,
        "num_clips": num_clips,
        "subtitle_style": _choice(data.get("subtitle_style", "hormozi"), "subtitle_style", SUBTITLE_STYLES),
        "crop_mode": _choice(data.get("crop_mode", "face_track"), "crop_mode", CROP_MODES),
        "quality": _choice(data.get("quality", defaults["quality"]), "quality", QUALITIES),
        "min_seconds": min_seconds,
        "max_seconds": max_seconds,
        "extraction_strategy": _choice(data.get("extraction_strategy", "ai_viral"), "extraction_strategy", EXTRACTION_STRATEGIES),
        "watermark": watermark.strip(),
        "hw_accel": _choice(data.get("hw_accel", "cpu"), "hw_accel", HW_ACCELERATORS),
    }


def resolve_managed_video(path_value: str, managed_dirs: tuple[Path, ...]) -> Path:
    """Resolve a video path, rejecting traversal, symlink escapes and non-video files."""
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValidationError("Ruta de video vacía")
    candidate = Path(path_value).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValidationError("Archivo de video no encontrado") from exc

    if not resolved.is_file() or resolved.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValidationError("El archivo debe ser un video compatible")

    for root in managed_dirs:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    raise ValidationError("La ruta no pertenece a una carpeta de medios administrada por Gigaclip")


def validate_clip_range(start, end, max_duration: float = 600.0) -> tuple[float, float]:
    try:
        start = float(start)
        end = float(end)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError("Los tiempos deben ser numéricos") from exc
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValidationError("El intervalo de tiempo no es válido")
    if end - start > max_duration:
        raise ValidationError(f"El intervalo no puede superar {int(max_duration)} segundos")
    return start, end


def validate_words(words, start: float, end: float) -> list[dict]:
    """Accept only bounded word-timestamp entries from a re-render request."""
    if not isinstance(words, list):
        raise ValidationError("words debe ser una lista")
    cleaned = []
    for word in words[:10000]:
        if not isinstance(word, dict) or not isinstance(word.get("word"), str):
            continue
        try:
            word_start = float(word["start"])
            word_end = float(word["end"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (math.isfinite(word_start) and math.isfinite(word_end) and
                start <= word_start < word_end <= end):
            cleaned.append({"word": word["word"][:100], "start": word_start, "end": word_end})
    return cleaned


def sign_media_link(filename: str, expires: int, secret: str) -> str:
    """Create the HMAC used by short-lived public links in webhook payloads."""
    message = f"{filename}:{int(expires)}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_media_link(filename: str, expires, signature: str, secret: str,
                      now: int | None = None, max_lifetime: int = 7 * 24 * 60 * 60) -> bool:
    """Verify an expiring HMAC media link without exposing the API key."""
    if not filename or Path(filename).name != filename or not secret or not isinstance(signature, str):
        return False
    try:
        expires = int(expires)
    except (TypeError, ValueError, OverflowError):
        return False
    current_time = int(time.time()) if now is None else int(now)
    if expires < current_time or expires > current_time + max_lifetime:
        return False
    expected = sign_media_link(filename, expires, secret)
    return bool(signature) and hmac.compare_digest(signature, expected)
