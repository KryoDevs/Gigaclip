"""
Orquesta el pipeline completo: descarga -> transcribe -> elige clips ->
recorta a vertical -> quema subtitulos. Este es el corazon de la Fase 1.
"""
import subprocess

import cv2

from config import OUTPUT_DIR, TEMP_DIR, NUM_CLIPS, FFMPEG_BIN
from download import download_video
from transcribe import transcribe
from select_clips import select_clips
from crop import crop_to_vertical
from subtitles import burn_subtitles


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
        # Fallback: re-encode si el corte "-c copy" falla
        # (pasa cuando el punto de corte no cae justo en un keyframe)
        cmd[cmd.index("-c") + 1] = "libx264"
        subprocess.run(cmd, check=True)


def run(url: str, num_clips: int = NUM_CLIPS) -> list[str]:
    print(f"[1/5] Descargando: {url}")
    video = download_video(url)
    source_path = video["path"]
    print(f"      -> {video['title']} ({video['duration']}s)")

    print("[2/5] Transcribiendo (esto puede tardar segun el largo del video)...")
    transcript = transcribe(source_path)
    print(f"      -> {len(transcript['words'])} palabras, {len(transcript['segments'])} segmentos")

    print("[3/5] Eligiendo los mejores momentos con el LLM local...")
    clips = select_clips(transcript["segments"], num_clips=num_clips)
    print(f"      -> {len(clips)} clips seleccionados")

    final_paths = []
    for i, clip in enumerate(clips, start=1):
        title = clip.get("title", "")
        print(f"[4/5] Procesando clip {i}/{len(clips)}: \"{title}\" "
              f"({clip['start']:.1f}s - {clip['end']:.1f}s)")

        # 1. Extrae el tramo crudo del video original (sin recortar aun)
        raw_clip_path = str(TEMP_DIR / f"raw_{i}.mp4")
        _extract_segment(source_path, clip["start"], clip["end"], raw_clip_path)

        # 2. Recorta a vertical siguiendo el rostro
        cropped_noaudio_path = str(TEMP_DIR / f"cropped_{i}.mp4")
        crop_to_vertical(raw_clip_path, cropped_noaudio_path)

        cap = cv2.VideoCapture(cropped_noaudio_path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        # 3. Subtitulos + audio + salida final
        clip_words = _words_between(transcript["words"], clip["start"], clip["end"])
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:40].strip()
        final_path = str(OUTPUT_DIR / f"{i:02d}_{safe_title or f'clip_{i}'}.mp4")

        burn_subtitles(
            video_no_audio=cropped_noaudio_path,
            original_source=source_path,
            clip_start=clip["start"],
            clip_end=clip["end"],
            words_in_clip=clip_words,
            video_w=w, video_h=h,
            final_output=final_path,
        )
        final_paths.append(final_path)

    print(f"[5/5] Listo. {len(final_paths)} clips en {OUTPUT_DIR}")
    return final_paths


if __name__ == "__main__":
    import sys
    run(sys.argv[1])
