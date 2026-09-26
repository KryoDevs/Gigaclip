"""
Pipeline turbo de Gigaclip.
Ejecuta recorte facial, escalado a 9:16, quemado de subtitulos y mezcla de audio
en una UNICA pasada de FFmpeg ultrarrapida por clip (-preset veryfast).
"""
import os
import subprocess
from pathlib import Path

from config import OUTPUT_DIR, NUM_CLIPS, FFMPEG_BIN
from download import download_video
from audio_analysis import analyze_audio_energy, correlate_energy_with_segments
from transcribe import transcribe
from select_clips import select_clips
from crop import build_ffmpeg_filter
from subtitles import _STYLE_BUILDERS, _build_ass_hormozi
from social_metadata import generate_social_metadata


def _words_between(words: list[dict], start: float, end: float) -> list[dict]:
    return [w for w in words if w["start"] >= start and w["end"] <= end]


def _render_clip_fast(source_path: str, start: float, end: float, words_in_clip: list[dict],
                      final_output: str, style: str = "hormozi", crop_mode: str = "face_track") -> None:
    """Renderiza el clip en 1 sola pasada combinada de FFmpeg."""
    # 1. Generar archivo .ass temporal
    ass_path = str(Path(final_output).with_suffix(".ass"))
    builder = _STYLE_BUILDERS.get(style, _build_ass_hormozi)
    
    relative_words = [
        {"word": w["word"], "start": w["start"] - start, "end": w["end"] - start}
        for w in words_in_clip
    ]
    # Resolucion vertical estandar 720x1280 (9:16)
    builder(relative_words, 720, 1280, ass_path)

    ass_path_rel = os.path.relpath(ass_path).replace("\\", "/")

    # 2. Construir filtro combinado (crop + scale + subtitle)
    if crop_mode in ("podcast_split", "blur_background"):
        filter_str = build_ffmpeg_filter(source_path, start, end, ass_path_rel, mode=crop_mode)
        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", str(start), "-to", str(end),
            "-i", source_path,
            "-filter_complex", filter_str,
            "-map", "[outv]",
            "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            final_output
        ]
    else:
        filter_str = build_ffmpeg_filter(source_path, start, end, ass_path_rel, mode="face_track")
        cmd = [
            FFMPEG_BIN, "-y",
            "-ss", str(start), "-to", str(end),
            "-i", source_path,
            "-vf", filter_str,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            final_output
        ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def run(url: str, num_clips: int = NUM_CLIPS, subtitle_style: str = "hormozi",
        crop_mode: str = "face_track", progress_callback=None) -> list[dict]:
    
    def log(msg, step_pct=None):
        if progress_callback:
            progress_callback(msg, step_pct)
        else:
            print(msg)

    # 1. Descarga Turbo
    log(f"[1/5] ⚡ Descargando video: {url}", 15)
    video = download_video(url)
    source_path = video["path"]
    log(f"      → {video['title']} ({video['duration']}s)", 20)

    # 2. Analisis de audio y transcripcion paralela/rapida
    log("[2/5] 🎙️ Analizando audio y transcribiendo con Whisper...", 30)
    energy_data = analyze_audio_energy(source_path)
    transcript = transcribe(source_path)
    segments_with_energy = correlate_energy_with_segments(transcript["segments"], energy_data)
    log(f"      → {len(transcript['words'])} palabras analizadas", 55)

    # 3. Seleccion con LLM
    log("[3/5] 🧠 Seleccionando mejores momentos virales...", 65)
    clips = select_clips(segments_with_energy, num_clips=num_clips)
    log(f"      → {len(clips)} clips seleccionados", 70)

    final_clips_info = []
    for i, clip in enumerate(clips, start=1):
        title = clip.get("title", f"Clip {i}")
        pct = 70 + int((i / len(clips)) * 25)
        log(f"[4/5] ⚡ Renderizando clip {i}/{len(clips)}: \"{title}\"...", pct)

        clip_words = _words_between(transcript["words"], clip["start"], clip["end"])
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:35].strip()
        final_name = f"{i:02d}_{safe_title or f'clip_{i}'}.mp4"
        final_path = str(OUTPUT_DIR / final_name)

        _render_clip_fast(
            source_path=source_path,
            start=clip["start"],
            end=clip["end"],
            words_in_clip=clip_words,
            final_output=final_path,
            style=subtitle_style,
            crop_mode=crop_mode
        )

        snippet = " ".join(w["word"] for w in clip_words[:35])
        social_meta = generate_social_metadata(title, snippet)

        clip_data = {
            "filename": final_name,
            "title": title,
            "start": clip["start"],
            "end": clip["end"],
            "duration": round(clip["end"] - clip["start"], 1),
            "score": clip.get("score", 90),
            "hook_strength": clip.get("hook_strength", 90),
            "retention_score": clip.get("retention_score", 88),
            "hook": clip.get("hook", ""),
            "reason": clip.get("reason", ""),
            "social": social_meta,
            "style": subtitle_style,
            "crop_mode": crop_mode,
            "words": clip_words,
            "source_path": source_path,
        }
        final_clips_info.append(clip_data)

    log(f"[5/5] 🎉 ¡Listo! {len(final_clips_info)} clips listos en tiempo record.", 100)
    return final_clips_info


if __name__ == "__main__":
    import sys
    run(sys.argv[1])
