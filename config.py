"""
Configuracion central del pipeline. Ajusta esto segun tu hardware.
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

# --- Whisper (transcripcion) ---
# Modelos disponibles (de mas rapido/impreciso a mas lento/preciso):
# tiny, base, small, medium, large-v3
WHISPER_MODEL = "small"           # "small" es el mejor balance velocidad/calidad
WHISPER_DEVICE = "cpu"            # "cuda" si tienes GPU NVIDIA con drivers OK, si no "cpu"
WHISPER_COMPUTE_TYPE = "int8"     # "float16" en GPU, "int8" en CPU

# --- Ollama (seleccion de clips virales) ---
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"      # sube a "llama3.1:8b" si tu GPU tiene 6GB+ de VRAM libres

# --- Recorte / clips ---
NUM_CLIPS = 5             # cuantos clips generar por video
CLIP_MIN_SECONDS = 15
CLIP_MAX_SECONDS = 60
OUTPUT_ASPECT = (9, 16)   # formato vertical

# --- Descarga ---
# Limitar a 720p para acelerar descarga y procesamiento.
# Para clips 9:16 la resolucion final es ~405x720, asi que 4K es desperdicio.
DOWNLOAD_MAX_HEIGHT = 720

# --- Subtitulos ---
SUBTITLE_FONT = "Arial Black"
SUBTITLE_WORDS_PER_CHUNK = 3     # cuantas palabras se muestran a la vez
SUBTITLE_STYLE = "hormozi"       # "classic", "hormozi", "minimal", "karaoke"

# --- Face detection ---
FACE_SAMPLE_EVERY = 10           # cada cuantos frames samplear (mayor = mas rapido)

# --- Auto-deteccion de ffmpeg ---
FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
