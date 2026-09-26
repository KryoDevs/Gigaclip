"""
Modulo de analisis de audio para deteccion de picos de energia,
volumen (RMS) y pausas de silencio. Ayuda al LLM a priorizar momentos
con alta carga emocional, risas, euforia o enfasis en el discurso.
"""
import subprocess
import numpy as np
from pathlib import Path

from config import FFMPEG_BIN, TEMP_DIR


def extract_audio_wav(video_path: str, output_wav: str = None) -> str:
    """Extrae el canal de audio en formato WAV a 16kHz mono para analisis rapido."""
    if output_wav is None:
        stem = Path(video_path).stem
        output_wav = str(TEMP_DIR / f"{stem}_analysis.wav")

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        output_wav
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_wav


def analyze_audio_energy(video_path: str, chunk_duration: float = 1.0) -> list[dict]:
    """
    Calcula el nivel de energia (RMS) y volumen por ventana de tiempo.
    Devuelve lista de {"start": float, "end": float, "energy": float, "is_peak": bool}
    """
    wav_path = None
    try:
        wav_path = extract_audio_wav(video_path)
        
        # Leer datos crudos PCM del WAV
        with open(wav_path, "rb") as f:
            # Saltar header WAV (44 bytes aprox)
            f.seek(44)
            audio_data = np.frombuffer(f.read(), dtype=np.int16).astype(np.float32)

        sample_rate = 16000
        samples_per_chunk = int(sample_rate * chunk_duration)
        total_chunks = len(audio_data) // samples_per_chunk

        if total_chunks == 0:
            return []

        chunks_energy = []
        rms_values = []

        for i in range(total_chunks):
            chunk = audio_data[i * samples_per_chunk : (i + 1) * samples_per_chunk]
            rms = np.sqrt(np.mean(chunk**2)) if len(chunk) > 0 else 0
            rms_values.append(rms)

        if not rms_values:
            return []

        # Normalizar energia 0.0 - 1.0
        max_rms = max(rms_values) if max(rms_values) > 0 else 1.0
        mean_rms = np.mean(rms_values)
        std_rms = np.std(rms_values)
        peak_threshold = mean_rms + 0.8 * std_rms

        for i, rms in enumerate(rms_values):
            norm_energy = round(float(rms / max_rms), 3)
            is_peak = bool(rms >= peak_threshold)
            chunks_energy.append({
                "start": round(i * chunk_duration, 1),
                "end": round((i + 1) * chunk_duration, 1),
                "energy": norm_energy,
                "is_peak": is_peak,
            })

        return chunks_energy

    except Exception as e:
        # Fallback tolerante si falla el analisis de audio
        return []
    finally:
        if wav_path and Path(wav_path).exists():
            try:
                Path(wav_path).unlink()
            except Exception:
                pass


def correlate_energy_with_segments(segments: list[dict], energy_data: list[dict]) -> list[dict]:
    """Agrega metrica de energia promedio y picos detectados a cada segmento de transcripcion."""
    if not energy_data:
        for s in segments:
            s["energy_score"] = 5.0
            s["has_energy_peak"] = False
        return segments

    for seg in segments:
        start, end = seg["start"], seg["end"]
        overlapping = [e for e in energy_data if not (e["end"] <= start or e["start"] >= end)]
        if overlapping:
            avg_energy = np.mean([e["energy"] for e in overlapping])
            has_peak = any(e["is_peak"] for e in overlapping)
            seg["energy_score"] = round(float(avg_energy * 10), 1)
            seg["has_energy_peak"] = has_peak
        else:
            seg["energy_score"] = 5.0
            seg["has_energy_peak"] = False

    return segments
