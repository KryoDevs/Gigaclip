"""
Pipeline Pro de Gigaclip.
Soporta renderizado en 1080p Full HD (CRF 18, audio 192k),
rangos de duracion ajustables por el usuario y metadatos virales.
"""
import os
import subprocess
from pathlib import Path

from config import (
    OUTPUT_DIR,
    NUM_CLIPS,
    CLIP_MIN_SECONDS,
    CLIP_MAX_SECONDS,
    FFMPEG_BIN,
    VIDEO_QUALITY_PRESETS,
    DEFAULT_QUALITY,
)
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
                      final_output: str, style: str = "hormozi", crop_mode: str = "face_track",
                      quality: str = DEFAULT_QUALITY) -> None:
    """Renderiza el clip en alta calidad con parÃ¡metros optimizados."""
    preset_data = VIDEO_QUALITY_PRESETS.get(quality, VIDEO_QUALITY_PRESETS["1080p"])
    target_w = preset_data["width"]
    target_h = preset_data["height"]
    crf = preset_data["crf"]
    v_bitrate = preset_data["video_bitrate"]
    a_bitrate = preset_data["audio_bitrate"]
    ff_preset = preset_data["preset"]

    # 1. Generar archivo .ass con resolucion exacta del target
    ass_path = str(Path(final_output).with_suffix(".ass"))
    builder = _STYLE_BUILDERS.get(style, _build_ass_hormozi)
    
    relative_words = [
        {"word": w["word"], "start": w["start"] - start, "end": w["end"] - start}
        for w in words_in_clip
    ]
    builder(relative_words, target_w, target_h, ass_path)

    ass_path_rel = os.path.relpath(ass_path).replace("\\", "/")

    # 2. Construir filtro combinado (crop + scale + subtitle + sharpen)
    filter_str = build_ffmpeg_filter(source_path, start, end, ass_path_rel, mode=crop_mode, quality=quality)

    whoosh_path = str(BASE_DIR / 'assets' / 'sfx' / 'whoosh.wav')
    pop_path = str(BASE_DIR / 'assets' / 'sfx' / 'pop.wav')
    pop_delay = int((end - start) * 500)
    
    if crop_mode in ('podcast_split', 'blur_background'):
        v_filter = filter_str
    else:
        v_filter = f'[0:v]{filter_str}[outv]'
        
    complex_filter = (
        f'{v_filter}; '
        f'[1:a]adelay=0|0[sfx1]; '
        f'[2:a]adelay={pop_delay}|{pop_delay}[sfx2]; '
        f'[0:a][sfx1][sfx2]amix=inputs=3:duration=first:dropout_transition=2:normalize=0[outa]'
    )

    cmd = [
        FFMPEG_BIN, '-y',
        '-ss', str(start), '-to', str(end),
        '-i', source_path,
        '-i', whoosh_path,
        '-i', pop_path,
        '-filter_complex', complex_filter,
        '-map', '[outv]',
        '-map', '[outa]',
        '-c:v', 'libx264', '-preset', ff_preset, '-crf', crf,
        '-b:v', v_bitrate, '-maxrate', '8000k', '-bufsize', '12000k',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', a_bitrate, '-ar', '48000',
        '-shortest',
        final_output
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def run(url: str = None, local_path: str = None, num_clips: int = NUM_CLIPS, subtitle_style: str = "hormozi",
        crop_mode: str = "face_track", quality: str = DEFAULT_QUALITY,
        min_seconds: int = None, max_seconds: int = None, progress_callback=None) -> dict:
    
    def log(msg, step_pct=None):
        if progress_callback:
            progress_callback(msg, step_pct)
        else:
            print(msg)

    min_s = min_seconds or CLIP_MIN_SECONDS
    max_s = max_seconds or CLIP_MAX_SECONDS

    # 1. Descarga o Archivo Local
    if local_path and os.path.exists(local_path):
        log(f"[1/5] ðŸ“ Procesando archivo local: {os.path.basename(local_path)}", 20)
        source_path = local_path
        # Extraemos algo de metadata basica
        video_title = os.path.basename(local_path).rsplit(".", 1)[0]
        video_duration = 0 # No es critico para el pipeline
        video = {"title": video_title, "duration": video_duration, "path": source_path}
    elif url:
        log(f"[1/5] âš¡ Descargando video en HD: {url}", 15)
        video = download_video(url)
        source_path = video["path"]
        log(f"      â†’ {video['title']} ({video['duration']}s)", 20)
    else:
        raise ValueError("Se debe proveer una 'url' o un 'local_path'")

    # 2. Analisis acustico y transcripcion Whisper
    log("[2/5] ðŸŽ™ï¸ Analizando energia de audio y transcribiendo...", 30)
    energy_data = analyze_audio_energy(source_path)
    transcript = transcribe(source_path)
    segments_with_energy = correlate_energy_with_segments(transcript["segments"], energy_data)
    log(f"      â†’ {len(transcript['words'])} palabras analizadas", 55)

    # 3. Seleccion con LLM respetando rango de duracion
    log(f"[3/5] ðŸ§  Seleccionando momentos virales ({min_s}s - {max_s}s)...", 65)
    clips = select_clips(segments_with_energy, num_clips=num_clips, min_seconds=min_s, max_seconds=max_s)
    log(f"      â†’ {len(clips)} clips seleccionados", 70)

    final_clips_info = []
    for i, clip in enumerate(clips, start=1):
        title = clip.get("title", f"Clip {i}")
        pct = 70 + int((i / len(clips)) * 25)
        log(f"[4/5] ðŸŽ¬ Renderizando clip {i}/{len(clips)} en {quality} Full HD...", pct)

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
            crop_mode=crop_mode,
            quality=quality,
        )

        snippet = " ".join(w["word"] for w in clip_words[:35])
        social_meta = generate_social_metadata(title, snippet)

        # Extraer miniatura automatica
        from social_publisher import extract_thumbnail
        thumb_file = ""
        try:
            thumb_path = extract_thumbnail(final_path, timestamp_sec=1.0)
            thumb_file = Path(thumb_path).name
        except Exception:
            pass

        clip_data = {
            "filename": final_name,
            "thumbnail": thumb_file,
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
            "quality": quality,
            "words": clip_words,
            "source_path": source_path,
        }
        final_clips_info.append(clip_data)

    log(f"[5/5] ðŸŽ‰ Â¡Listo! {len(final_clips_info)} clips en {quality} generados.", 100)
    return {
        "clips": final_clips_info,
        "transcript": transcript,
        "video_info": video,
    }


if __name__ == "__main__":
    import sys
    run(sys.argv[1])


