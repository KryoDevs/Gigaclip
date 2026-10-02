"""
Transcripcion ultra-rapida con faster-whisper.
Extrae audio WAV mono a 16kHz primero y usa decodificacion directa (beam_size=1)
para reducir el tiempo de transcripcion a solo unos segundos.
"""
import hashlib
import json
import subprocess
import tempfile
import threading
from pathlib import Path

from faster_whisper import WhisperModel

from config import (
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_BEAM_SIZE,
    CACHE_DIR,
    TEMP_DIR,
    FFMPEG_BIN,
)

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = WhisperModel(
                    WHISPER_MODEL,
                    device=WHISPER_DEVICE,
                    compute_type=WHISPER_COMPUTE_TYPE,
                    cpu_threads=4,
                )
    return _model


def _cache_key(path: str) -> Path:
    p = Path(path)
    try:
        stat = p.stat()
        identity = f"{p.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        identity = str(p.resolve())
    # Include cache schema and decode settings to avoid stale transcript collisions.
    key_str = f"v2|{identity}|{WHISPER_MODEL}|{WHISPER_BEAM_SIZE}"
    h = hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:20]
    return CACHE_DIR / f"{h}_{WHISPER_MODEL}.json"


def _extract_fast_audio(video_path: str) -> str:
    """Extrae audio mono liviano para alimentar directamente a Whisper."""
    handle = tempfile.NamedTemporaryFile(prefix="gigaclip_whisper_", suffix=".wav", dir=TEMP_DIR, delete=False)
    wav_path = handle.name
    handle.close()
    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_path,
        "-vn", "-ac", "1", "-ar", "16000",
        "-f", "wav",
        wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return wav_path


def transcribe(audio_or_video_path: str) -> dict:
    cache_file = _cache_key(audio_or_video_path)
    if cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache_file.unlink(missing_ok=True)

    audio_path = None
    try:
        audio_path = _extract_fast_audio(audio_or_video_path)
        model = _get_model()
        segments, info = model.transcribe(
            audio_path,
            word_timestamps=True,
            vad_filter=True,
            beam_size=WHISPER_BEAM_SIZE,
            best_of=1,
            temperature=0.0,
        )

        words = []
        sentence_segments = []
        for seg in segments:
            sentence_segments.append({
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
            })
            if seg.words:
                for word in seg.words:
                    words.append({
                        "word": word.word.strip(),
                        "start": round(word.start, 3),
                        "end": round(word.end, 3),
                    })

        result = {"words": words, "segments": sentence_segments, "language": info.language}
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    finally:
        if audio_path:
            Path(audio_path).unlink(missing_ok=True)


if __name__ == "__main__":
    import sys
    result = transcribe(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
