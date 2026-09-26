"""
Descarga optimizada con yt-dlp usando fragmentos concurrentes para maxima velocidad.
"""
from pathlib import Path
import yt_dlp

from config import DOWNLOAD_DIR, DOWNLOAD_MAX_HEIGHT


def download_video(url: str) -> dict:
    """Descarga acelerada en calidad optima para clips verticales."""
    outtmpl = str(DOWNLOAD_DIR / "%(id)s.%(ext)s")
    max_h = DOWNLOAD_MAX_HEIGHT

    ydl_opts = {
        "format": f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/best[height<={max_h}][ext=mp4]/best[height<={max_h}]/best",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "concurrent_fragment_downloads": 4,  # Descarga paralela de fragmentos
        "socket_timeout": 15,
        "retries": 3,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
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
