"""
Genera subtitulos estilo viral (pocas palabras a la vez, con la palabra
activa resaltada en color) y los quema en el video final con ffmpeg.

Estilos disponibles:
  - "classic":  Blanco con borde negro, todas las palabras iguales
  - "hormozi":  Blanco base, palabra activa en amarillo/dorado (estilo Alex Hormozi)
  - "minimal":  Blanco semitransparente, pequeno, abajo del todo
  - "karaoke":  Palabra activa crece y cambia de color progresivamente
"""
import os
import subprocess
from pathlib import Path

from config import SUBTITLE_FONT, SUBTITLE_WORDS_PER_CHUNK, SUBTITLE_STYLE, FFMPEG_BIN


def _format_ass_time(seconds: float) -> str:
    seconds = max(seconds, 0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _build_ass_classic(words, video_w, video_h, out_path):
    """Subtitulos clasicos: blanco con borde negro."""
    font_size = int(video_h * 0.055)
    margin_v = int(video_h * 0.10)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,{SUBTITLE_FONT},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,1,3,1,2,20,20,{margin_v}

[Events]
Format: Layer, Start, End, Style, Text
"""
    lines = [header]
    chunk = SUBTITLE_WORDS_PER_CHUNK
    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        if not group:
            continue
        start = group[0]["start"]
        end = group[-1]["end"]
        text = " ".join(w["word"] for w in group).upper()
        lines.append(f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _build_ass_hormozi(words, video_w, video_h, out_path):
    """
    Estilo Hormozi: muestra un grupo de palabras, y la palabra activa
    se resalta en amarillo/dorado mientras las demas quedan en blanco.
    No invasivo pero genera enganche visual.
    """
    font_size = int(video_h * 0.052)
    margin_v = int(video_h * 0.10)

    # Colores ASS (formato &HBBGGRR)
    white = "&H00FFFFFF"
    gold = "&H0000D4FF"     # amarillo/dorado
    outline = "&H00000000"
    shadow_col = "&H80000000"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,{SUBTITLE_FONT},{font_size},{white},&H000000FF,{outline},{shadow_col},1,1,3,1,2,20,20,{margin_v}

[Events]
Format: Layer, Start, End, Style, Text
"""
    lines = [header]
    chunk = SUBTITLE_WORDS_PER_CHUNK

    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        if not group:
            continue

        # Para cada palabra en el grupo, crear un evento donde ESA palabra esta resaltada
        for wi, active_word in enumerate(group):
            w_start = active_word["start"]
            w_end = active_word["end"]

            # Construir el texto con la palabra activa en dorado
            parts = []
            for wj, w in enumerate(group):
                word_text = w["word"].upper()
                if wj == wi:
                    # Palabra activa: dorado + ligeramente mas grande
                    parts.append(f"{{\\c{gold}\\fscx110\\fscy110}}{word_text}{{\\c{white}\\fscx100\\fscy100}}")
                else:
                    parts.append(word_text)

            text = " ".join(parts)
            lines.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _build_ass_minimal(words, video_w, video_h, out_path):
    """Subtitulos minimalistas: pequenos, blancos, abajo."""
    font_size = int(video_h * 0.035)
    margin_v = int(video_h * 0.05)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,1,2,0,2,30,30,{margin_v}

[Events]
Format: Layer, Start, End, Style, Text
"""
    lines = [header]
    chunk = SUBTITLE_WORDS_PER_CHUNK + 2  # Mas palabras por linea en minimal
    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        if not group:
            continue
        start = group[0]["start"]
        end = group[-1]["end"]
        text = " ".join(w["word"] for w in group)
        lines.append(f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _build_ass_karaoke(words, video_w, video_h, out_path):
    """Estilo karaoke: palabra activa crece y se ilumina progresivamente."""
    font_size = int(video_h * 0.052)
    margin_v = int(video_h * 0.10)

    cyan = "&H00FFFF00"
    white = "&H00FFFFFF"
    outline = "&H00000000"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,{SUBTITLE_FONT},{font_size},{white},&H000000FF,{outline},&H80000000,1,1,3,1,2,20,20,{margin_v}

[Events]
Format: Layer, Start, End, Style, Text
"""
    lines = [header]
    chunk = SUBTITLE_WORDS_PER_CHUNK

    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        if not group:
            continue

        for wi, active_word in enumerate(group):
            w_start = active_word["start"]
            w_end = active_word["end"]

            parts = []
            for wj, w in enumerate(group):
                word_text = w["word"].upper()
                if wj == wi:
                    parts.append(f"{{\\c{cyan}\\fscx115\\fscy115\\bord4}}{word_text}{{\\c{white}\\fscx100\\fscy100\\bord3}}")
                elif wj < wi:
                    # Palabras ya dichas: ligeramente dim
                    parts.append(f"{{\\c&H00CCCCCC&}}{word_text}{{\\c{white}}}")
                else:
                    parts.append(word_text)

            text = " ".join(parts)
            lines.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


# Dispatcher de estilos
_STYLE_BUILDERS = {
    "classic": _build_ass_classic,
    "hormozi": _build_ass_hormozi,
    "minimal": _build_ass_minimal,
    "karaoke": _build_ass_karaoke,
}


def burn_subtitles(video_no_audio: str, original_source: str, clip_start: float, clip_end: float,
                    words_in_clip: list[dict], video_w: int, video_h: int, final_output: str,
                    style: str = None) -> None:
    """
    - video_no_audio: el clip ya recortado a 9:16, sin audio (salida de crop.py)
    - original_source: el video original completo, de donde se extrae el tramo de audio
    - words_in_clip: palabras (con timestamps ABSOLUTOS del video original)
    - final_output: mp4 final, con audio + subtitulos quemados
    - style: estilo de subtitulos ("classic", "hormozi", "minimal", "karaoke")
    """
    style = style or SUBTITLE_STYLE
    builder = _STYLE_BUILDERS.get(style, _build_ass_hormozi)

    # Los timestamps de las palabras deben quedar relativos al inicio del clip
    relative_words = [
        {"word": w["word"], "start": w["start"] - clip_start, "end": w["end"] - clip_start}
        for w in words_in_clip
    ]

    ass_path = str(Path(final_output).with_suffix(".ass"))
    builder(relative_words, video_w, video_h, ass_path)

    # ffmpeg en Windows: usar path relativo para evitar problemas con 'C:'
    ass_path_ffmpeg = os.path.relpath(ass_path).replace("\\", "/")

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", video_no_audio,
        "-ss", str(clip_start), "-to", str(clip_end), "-i", original_source,
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", f"ass={ass_path_ffmpeg}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest",
        final_output,
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    print("Este modulo se usa desde pipeline.py")
