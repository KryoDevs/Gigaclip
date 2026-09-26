"""
Orquestador central de Gigaclip.
Coordina el pipeline completo:
  1. Descarga del video fuente
  2. Analisis de energia de audio y picos
  3. Transcripcion con timestamps a nivel de palabra
  4. Seleccion de momentos virales con LLM
  5. Reencuadre vertical 9:16 (seguimiento facial, podcast split o fondo borroso)
  6. Subtitulos quemados con estilo viral y auto-emojis
  7. Generacion de metadatos sociales listos para publicar (TikTok, Shorts, Reels)
"""
import cv2
import subprocess
from pathlib import Path

from config import OUTPUT_DIR, TEMP_DIR, NUM_CLIPS, FFMPEG_BIN
from download import download_video
from audio_analysis import analyze_audio_energy, correlate_energy_with_segments
from transcribe import transcribe
from select_clips import select_clips
from crop import crop_to_vertical
from subtitles import burn_subtitles
from social_metadata import generate_social_metadata


def _words_between(words: list[dict], start: float, end: float) -> list[dict]:
    return [w for w in words if w["start"] >= start and w["end"] <= end]


def _extract_segment(source_path: str, start: float, end: float, out_path: str) -> None:
    cmd = [
        FFMPEG_BIN, "-y",
        "-ss", str(start), "-to", str(end),
        "-i", source_path,
        "-c", "copy",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        cmd[cmd.index("-c") + 1] = "libx264"
        subprocess.run(cmd, check=True)


def run(url: str, num_clips: int = NUM_CLIPS, subtitle_style: str = "hormozi",
        crop_mode: str = "face_track", progress_callback=None) -> list[dict]:
    
    def log(msg, step_pct=None):
        if progress_callback:
            progress_callback(msg, step_pct)
        else:
            print(msg)

    # 1. Descarga
    log(f"[1/6] Descargando video: {url}", 10)
    video = download_video(url)
    source_path = video["path"]
    log(f"      -> {video['title']} ({video['duration']}s)", 15)

    # 2. Analisis de energia de audio
    log("[2/6] Analizando picos de energia y emociones en audio...", 20)
    energy_data = analyze_audio_energy(source_path)

    # 3. Transcripcion
    log("[3/6] Transcribiendo con Whisper a nivel de palabra...", 30)
    transcript = transcribe(source_path)
    segments_with_energy = correlate_energy_with_segments(transcript["segments"], energy_data)
    log(f"      -> {len(transcript['words'])} palabras, {len(transcript['segments'])} segmentos", 45)

    # 4. Seleccion con LLM
    log("[4/6] Evaluando ganchos y potencial viral con LLM...", 55)
    clips = select_clips(segments_with_energy, num_clips=num_clips)
    log(f"      -> {len(clips)} momentos virales seleccionados", 60)

    final_clips_info = []
    for i, clip in enumerate(clips, start=1):
        title = clip.get("title", f"Clip {i}")
        pct = 60 + int((i / len(clips)) * 35)
        log(f"[5/6] Renderizando clip {i}/{len(clips)}: \"{title}\" ({clip['start']:.1f}s - {clip['end']:.1f}s)", pct)

        # 5.1 Corte crudo
        raw_clip_path = str(TEMP_DIR / f"raw_{i}.mp4")
        _extract_segment(source_path, clip["start"], clip["end"], raw_clip_path)

        # 5.2 Recorte vertical
        cropped_noaudio_path = str(TEMP_DIR / f"cropped_{i}.mp4")
        crop_to_vertical(raw_clip_path, cropped_noaudio_path, mode=crop_mode)

        cap = cv2.VideoCapture(cropped_noaudio_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        # 5.3 Subtitulos
        clip_words = _words_between(transcript["words"], clip["start"], clip["end"])
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:40].strip()
        final_name = f"{i:02d}_{safe_title or f'clip_{i}'}.mp4"
        final_path = str(OUTPUT_DIR / final_name)

        burn_subtitles(
            video_no_audio=cropped_noaudio_path,
            original_source=source_path,
            clip_start=clip["start"],
            clip_end=clip["end"],
            words_in_clip=clip_words,
            video_w=w, video_h=h,
            final_output=final_path,
            style=subtitle_style,
        )

        # 6. Metadatos sociales
        snippet = " ".join(w["word"] for w in clip_words[:40])
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

    log(f"[6/6] Listo. {len(final_clips_info)} clips listos para publicar.", 100)
    return final_clips_info


if __name__ == "__main__":
    import sys
    run(sys.argv[1])
