"""
Configuracion optimizada para maxima velocidad de Gigaclip.
"""
import shutil
from pathlib import Path

# --- Rutas ---
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"
CACHE_DIR = BASE_DIR / "cache"

for d in (DOWNLOAD_DIR, OUTPUT_DIR, TEMP_DIR, CACHE_DIR):
    d.mkdir(exist_ok=True)

# --- Whisper (transcripcion ultra rapida) ---
# "base" es 5x mas rapido que "medium" y toma solo segundos en CPU.
WHISPER_MODEL = "base"
WHISPER_DEVICE = "cpu"            # "cuda" si tienes GPU NVIDIA
WHISPER_COMPUTE_TYPE = "int8"     # int8 para velocidad maxima en CPU
WHISPER_BEAM_SIZE = 1             # Greedy decoding (3x mas rapido que beam_size=5)

# --- Ollama (seleccion de clips virales) ---
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

# --- Recorte / clips ---
NUM_CLIPS = 3
CLIP_MIN_SECONDS = 15
CLIP_MAX_SECONDS = 60
OUTPUT_ASPECT = (9, 16)

# --- Descarga Turbo ---
DOWNLOAD_MAX_HEIGHT = 720

# --- Subtitulos ---
SUBTITLE_FONT = "Arial Black"
SUBTITLE_WORDS_PER_CHUNK = 3
SUBTITLE_STYLE = "hormozi"

# --- Muestreo Facial Acelerado ---
FACE_SAMPLE_FPS = 2               # Muestrear solo 2 frames por segundo (ultra rapido)

# --- Binario FFmpeg ---
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
