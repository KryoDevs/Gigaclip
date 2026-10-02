"""
Motor avanzado de subtitulos virales para Gigaclip.
Soporta auto-emojis contextuales y multiples estilos modernos:
  - "hormozi":    Palabra activa en oro/amarillo brillante, escala sutil.
  - "mrbeast":    Tipografia gruesa, bordes pronunciados, colores llamativos (amarillo/cian).
  - "ali_abdaal": Estilo sticker redondeado con resaltador blanco/dorado.
  - "karaoke":    Llenado progresivo de color palabra a palabra.
  - "minimal":    Discreto, moderno, sin saturar la composicion.
  - "classic":    Blanco nitido con contorno negro solido.
"""
import os
import re
import subprocess
from pathlib import Path

from config import SUBTITLE_FONT, SUBTITLE_WORDS_PER_CHUNK, SUBTITLE_STYLE, FFMPEG_BIN

# Diccionario inteligente de palabras clave a emojis para retencion visual
EMOJI_KEYWORDS = {
    # Dinero / Negocios
    r"\b(dinero|plata|dolares|dólares|riqueza|rico|pagar|precio|costo|gana|ganar|ganancia|cash)\b": "💸",
    r"\b(negocio|negocios|empresa|emprendedor|ventas|vender|inversion|inversión)\b": "📈",
    r"\b(exito|éxito|crecer|crecimiento|triunfo|logro)\b": "🚀",
    r"\b(millonario|billonario|fortuna)\b": "👑",
    # Emocion / Energia
    r"\b(fuego|increible|increíble|brutal|locura|loco|epico|épico|viral)\b": "🔥",
    r"\b(idea|mente|pensar|cerebro|sabias|sabías|aprender|secreto)\b": "💡",
    r"\b(cuidado|peligro|atencion|atención|ojo|alerta)\b": "⚠️",
    r"\b(tiempo|vida|anos|años|horas|minutos|segundos|tarde|rapido|rápido)\b": "⏳",
    r"\b(amor|pasion|pasión|feliz|felicidad|gusto)\b": "❤️",
    r"\b(objetivo|meta|foco|clave)\b": "🎯",
    r"\b(verdad|real|cierto|realidad|hecho)\b": "💯",
    r"\b(hablar|decir|escucha|escuchar|pregunta|consejo)\b": "🗣️",
}


def _inject_emojis(word: str) -> str:
    """Inserta un emoji pertinente si la palabra coincide con una palabra clave."""
    clean_w = re.sub(r"[^\wáéíóúÁÉÍÓÚñÑ]", "", word.lower())
    for pattern, emoji in EMOJI_KEYWORDS.items():
        if re.search(pattern, clean_w, re.IGNORECASE):
            return f"{word} {emoji}"
    return word


def _safe_ass_text(value: str) -> str:
    """Escape subtitle content so recognized speech cannot inject ASS override tags."""
    return str(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\r", " ").replace("\n", " ")


def _format_ass_time(seconds: float) -> str:
    seconds = max(seconds, 0)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _build_ass_hormozi(words, video_w, video_h, out_path):
    """Estilo Hormozi: palabra activa en oro brillante + pop de escala."""
    font_size = int(video_h * 0.052)
    margin_v = int(video_h * 0.12)

    white = "&H00FFFFFF"
    gold = "&H0000D7FF"     # Amarillo oro intenso
    outline = "&H00000000"
    shadow = "&H90000000"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,{SUBTITLE_FONT},{font_size},{white},&H000000FF,{outline},{shadow},1,1,4,2,2,20,20,{margin_v}

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
                word_text = _safe_ass_text(_inject_emojis(w["word"].upper()))
                if wj == wi:
                    parts.append(f"{{\\c{gold}\\fscx112\\fscy112\\bord5}}{word_text}{{\\c{white}\\fscx100\\fscy100\\bord4}}")
                else:
                    parts.append(word_text)

            text = " ".join(parts)
            lines.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _build_ass_mrbeast(words, video_w, video_h, out_path):
    """Estilo MrBeast: fuente extra negrita, contorno negro grueso, colores de alto contraste."""
    font_size = int(video_h * 0.056)
    margin_v = int(video_h * 0.14)

    yellow = "&H0000FFFF"
    cyan = "&H00FFFF00"
    outline = "&H00000000"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,{SUBTITLE_FONT},{font_size},{yellow},&H000000FF,{outline},&HB0000000,1,1,6,3,2,15,15,{margin_v}

[Events]
Format: Layer, Start, End, Style, Text
"""
    lines = [header]
    chunk = max(1, SUBTITLE_WORDS_PER_CHUNK - 1)  # 2 palabras por golpe para mayor dinamismo

    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        if not group:
            continue

        for wi, active_word in enumerate(group):
            w_start = active_word["start"]
            w_end = active_word["end"]

            parts = []
            for wj, w in enumerate(group):
                word_text = _safe_ass_text(_inject_emojis(w["word"].upper()))
                if wj == wi:
                    parts.append(f"{{\\c{cyan}\\fscx115\\fscy115}}{word_text}{{\\c{yellow}\\fscx100\\fscy100}}")
                else:
                    parts.append(word_text)

            text = " ".join(parts)
            lines.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _build_ass_ali_abdaal(words, video_w, video_h, out_path):
    """Estilo Ali Abdaal: caja sutil de fondo, texto blanco limpio con palabras clave coloreadas."""
    font_size = int(video_h * 0.048)
    margin_v = int(video_h * 0.12)

    white = "&H00FFFFFF"
    accent_green = "&H0080FF00"
    box_back = "&H90101010"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,Arial,{font_size},{white},&H000000FF,&H00000000,{box_back},1,3,10,0,2,20,20,{margin_v}

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
                word_text = _safe_ass_text(_inject_emojis(w["word"]))
                if wj == wi:
                    parts.append(f"{{\\c{accent_green}\\fscx108\\fscy108}}{word_text}{{\\c{white}\\fscx100\\fscy100}}")
                else:
                    parts.append(word_text)

            text = " ".join(parts)
            lines.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _build_ass_karaoke(words, video_w, video_h, out_path):
    """Estilo Karaoke progresivo."""
    font_size = int(video_h * 0.052)
    margin_v = int(video_h * 0.12)

    cyan = "&H00FFFF00"
    white = "&H00FFFFFF"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,{SUBTITLE_FONT},{font_size},{white},&H000000FF,&H00000000,&H80000000,1,1,4,1,2,20,20,{margin_v}

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
                word_text = _safe_ass_text(_inject_emojis(w["word"].upper()))
                if wj == wi:
                    parts.append(f"{{\\c{cyan}\\fscx112\\fscy112\\bord5}}{word_text}{{\\c{white}\\fscx100\\fscy100\\bord4}}")
                elif wj < wi:
                    parts.append(f"{{\\c&H00A0A0A0&}}{word_text}{{\\c{white}}}")
                else:
                    parts.append(word_text)

            text = " ".join(parts)
            lines.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _build_ass_minimal(words, video_w, video_h, out_path):
    font_size = int(video_h * 0.038)
    margin_v = int(video_h * 0.06)

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
    chunk = SUBTITLE_WORDS_PER_CHUNK + 2
    for i in range(0, len(words), chunk):
        group = words[i:i + chunk]
        if not group:
            continue
        start = group[0]["start"]
        end = group[-1]["end"]
        text = " ".join(_safe_ass_text(w["word"]) for w in group)
        lines.append(f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


def _build_ass_classic(words, video_w, video_h, out_path):
    font_size = int(video_h * 0.052)
    margin_v = int(video_h * 0.10)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_w}
PlayResY: {video_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,{SUBTITLE_FONT},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,1,4,1,2,20,20,{margin_v}

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
        text = " ".join(_safe_ass_text(w["word"]) for w in group).upper()
        lines.append(f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,{text}\n")

    Path(out_path).write_text("".join(lines), encoding="utf-8-sig")


_STYLE_BUILDERS = {
    "hormozi": _build_ass_hormozi,
    "mrbeast": _build_ass_mrbeast,
    "ali_abdaal": _build_ass_ali_abdaal,
    "karaoke": _build_ass_karaoke,
    "minimal": _build_ass_minimal,
    "classic": _build_ass_classic,
}


def burn_subtitles(video_no_audio: str, original_source: str, clip_start: float, clip_end: float,
                    words_in_clip: list[dict], video_w: int, video_h: int, final_output: str,
                    style: str = None) -> None:
    style = style or SUBTITLE_STYLE
    builder = _STYLE_BUILDERS.get(style, _build_ass_hormozi)

    relative_words = [
        {"word": w["word"], "start": w["start"] - clip_start, "end": w["end"] - clip_start}
        for w in words_in_clip
    ]

    ass_path = str(Path(final_output).with_suffix(".ass"))
    builder(relative_words, video_w, video_h, ass_path)

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
