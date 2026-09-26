"""
Configuracion Pro de Gigaclip.
Controla calidad de video HD/Full HD, algoritmos de mejora de imagen,
tiempos de corte y modelos de IA.
"""
import shutil
from pathlib import Path

# --- Rutas del Sistema ---
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"
CACHE_DIR = BASE_DIR / "cache"

for d in (DOWNLOAD_DIR, OUTPUT_DIR, TEMP_DIR, CACHE_DIR):
    d.mkdir(exist_ok=True)

# --- Calidad de Video y Renderizado Profesional ---
VIDEO_QUALITY_PRESETS = {
    "1080p": {
        "width": 1080,
        "height": 1920,
        "crf": "18",            # Calidad visual prácticamente sin pérdidas
        "video_bitrate": "5500k",
        "audio_bitrate": "192k",
        "preset": "fast",
        "sharpen": True         # Realce de nitidez inteligente
    },
    "720p": {
        "width": 720,
        "height": 1280,
        "crf": "20",
        "video_bitrate": "3500k",
        "audio_bitrate": "160k",
        "preset": "veryfast",
        "sharpen": False
    }
}
DEFAULT_QUALITY = "1080p"

# --- Whisper (Transcripcion Inteligente) ---
WHISPER_MODEL = "base"            # "base" para velocidad, "small" para máxima precisión
WHISPER_DEVICE = "cpu"            # "cuda" si se dispone de GPU
WHISPER_COMPUTE_TYPE = "int8"     # int8 en CPU, float16 en GPU
WHISPER_BEAM_SIZE = 1

# --- Ollama (Curacion de Contenido Viral) ---
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

# --- Duracion y Cantidad de Clips ---
NUM_CLIPS = 3
CLIP_MIN_SECONDS = 20
CLIP_MAX_SECONDS = 60
OUTPUT_ASPECT = (9, 16)

# --- Descarga en Alta Definicion ---
DOWNLOAD_MAX_HEIGHT = 1080        # Descarga en 1080p para clips cristalinos

# --- Tipografia y Subtitulos ---
SUBTITLE_FONT = "Arial Black"
SUBTITLE_WORDS_PER_CHUNK = 3
SUBTITLE_STYLE = "hormozi"

# --- Tracking Facial de Precision ---
FACE_SAMPLE_FPS = 3

# --- Binario FFmpeg ---
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
