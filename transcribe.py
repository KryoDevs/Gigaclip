"""
Transcripcion ultra-rapida con faster-whisper.
Extrae audio WAV mono a 16kHz primero y usa decodificacion directa (beam_size=1)
para reducir el tiempo de transcripcion a solo unos segundos.
"""
import hashlib
import json
import subprocess
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


def _get_model():
    global _model
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
        size = p.stat().st_size
    except OSError:
        size = 0
    key_str = f"{p.name}_{size}"
    h = hashlib.md5(key_str.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{h}_{WHISPER_MODEL}.json"


def _extract_fast_audio(video_path: str) -> str:
    """Extrae audio mono liviano para alimentar directamente a Whisper."""
    wav_path = str(TEMP_DIR / f"{Path(video_path).stem}_whisper.wav")
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
        return json.loads(cache_file.read_text(encoding="utf-8"))

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
            for w in seg.words:
                words.append({
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                })

    result = {"words": words, "segments": sentence_segments, "language": info.language}
    cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Limpiar audio temporal
    try:
        Path(audio_path).unlink(missing_ok=True)
    except Exception:
        pass

    return result


if __name__ == "__main__":
    import sys
    result = transcribe(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2)[:2000])
