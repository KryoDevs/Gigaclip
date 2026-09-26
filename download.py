"""
Descarga el video fuente con yt-dlp y devuelve la ruta local + metadatos.
Soporta YouTube, Vimeo, Twitch y Kick (lo que soporte yt-dlp en general).
"""
from pathlib import Path
import yt_dlp

from config import DOWNLOAD_DIR, DOWNLOAD_MAX_HEIGHT


def download_video(url: str) -> dict:
    """
    Descarga el video en la mejor calidad hasta DOWNLOAD_MAX_HEIGHT.
    Devuelve un dict con: path, title, duration (segundos), id.
    """
    outtmpl = str(DOWNLOAD_DIR / "%(id)s.%(ext)s")
    max_h = DOWNLOAD_MAX_HEIGHT

    ydl_opts = {
        "format": f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/best[height<={max_h}][ext=mp4]/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
        # Si yt-dlp fusiono a mp4, el nombre final puede diferir en extension
        filepath = str(Path(filepath).with_suffix(".mp4"))

    return {
        "path": filepath,
        "title": info.get("title", "video"),
        "duration": info.get("duration", 0),
        "id": info.get("id"),
    }


if __name__ == "__main__":
    import sys
    result = download_video(sys.argv[1])
    print(result)
