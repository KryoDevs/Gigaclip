"""
Transcribe el video con faster-whisper, con timestamps a nivel de palabra.
Esto le da al LLM el material para elegir momentos virales, y a
subtitles.py los tiempos exactos para las palabras en pantalla.

Incluye cache: si el video ya fue transcrito, no lo re-procesa.
"""
import hashlib
import json
from pathlib import Path

from faster_whisper import WhisperModel

from config import WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, CACHE_DIR

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
    return _model


def _cache_key(path: str) -> Path:
    """Genera un hash del archivo para usar como clave de cache."""
    h = hashlib.md5(Path(path).name.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{h}_{WHISPER_MODEL}.json"


def transcribe(audio_or_video_path: str) -> dict:
    """
    Devuelve:
      - "words": lista de {"word": str, "start": float, "end": float}
      - "segments": frases naturales de Whisper (para el prompt del LLM)
      - "language": idioma detectado

    Si existe cache, devuelve directo sin re-transcribir.
    """
    cache_file = _cache_key(audio_or_video_path)
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    model = _get_model()
    segments, info = model.transcribe(
        audio_or_video_path,
        word_timestamps=True,
        vad_filter=True,  # filtra silencios largos, ayuda con podcasts/streams largos
    )

    words = []
    sentence_segments = []
    for seg in segments:
        sentence_segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        if seg.words:
            for w in seg.words:
                words.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                })

    result = {"words": words, "segments": sentence_segments, "language": info.language}

    # Guardar en cache
    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


if __name__ == "__main__":
    import sys
    result = transcribe(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
