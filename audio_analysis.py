"""
Análisis de energía de audio mediante ventanas pequeñas, sin cargar el WAV completo
 en memoria. Las métricas orientan al selector de clips.
"""
import math
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from config import FFMPEG_BIN, TEMP_DIR


def extract_audio_wav(video_path: str, output_wav: str = None) -> str:
    """Extrae audio mono PCM a 16 kHz. Los nombres temporales son únicos por trabajo."""
    if output_wav is None:
        handle = tempfile.NamedTemporaryFile(prefix="gigaclip_audio_", suffix=".wav", dir=TEMP_DIR, delete=False)
        output_wav = handle.name
        handle.close()
    cmd = [
        FFMPEG_BIN, "-y", "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
        "-f", "wav", output_wav,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_wav


def analyze_audio_energy(video_path: str, chunk_duration: float = 1.0) -> list[dict]:
    """Devuelve RMS normalizado por ventana, incluyendo la última ventana parcial."""
    if not math.isfinite(chunk_duration) or chunk_duration <= 0:
        return []
    wav_path = None
    try:
        wav_path = extract_audio_wav(video_path)
        with wave.open(wav_path, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2 or sample_rate <= 0:
                return []
            samples_per_chunk = max(1, int(sample_rate * chunk_duration))
            chunks_energy = []
            rms_values = []
            index = 0
            while True:
                raw = wav_file.readframes(samples_per_chunk)
                if not raw:
                    break
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                if not samples.size:
                    continue
                rms = float(np.sqrt(np.mean(samples ** 2)))
                duration = len(samples) / sample_rate
                rms_values.append(rms)
                chunks_energy.append({
                    "start": index * chunk_duration,
                    "end": index * chunk_duration + duration,
                    "energy": 0.0,
                    "is_peak": False,
                })
                index += 1

        if not rms_values:
            return []
        max_rms = max(rms_values) or 1.0
        mean_rms = float(np.mean(rms_values))
        std_rms = float(np.std(rms_values))
        peak_threshold = mean_rms + 0.8 * std_rms
        for item, rms in zip(chunks_energy, rms_values):
            item["start"] = round(item["start"], 2)
            item["end"] = round(item["end"], 2)
            item["energy"] = round(rms / max_rms, 3)
            item["is_peak"] = bool(rms >= peak_threshold)
        return chunks_energy
    except Exception:
        # La falta de audio no impide transcribir/procesar el video.
        return []
    finally:
        if wav_path:
            Path(wav_path).unlink(missing_ok=True)


def correlate_energy_with_segments(segments: list[dict], energy_data: list[dict]) -> list[dict]:
    """Agrega energía promedio y presencia de picos a los segmentos de transcripción."""
    if not energy_data:
        for segment in segments:
            segment["energy_score"] = 5.0
            segment["has_energy_peak"] = False
        return segments

    for segment in segments:
        overlapping = [
            item for item in energy_data
            if not (item["end"] <= segment["start"] or item["start"] >= segment["end"])
        ]
        if overlapping:
            segment["energy_score"] = round(float(np.mean([item["energy"] for item in overlapping]) * 10), 1)
            segment["has_energy_peak"] = any(item["is_peak"] for item in overlapping)
        else:
            segment["energy_score"] = 5.0
            segment["has_energy_peak"] = False
    return segments
