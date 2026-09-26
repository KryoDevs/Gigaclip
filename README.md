# Clon de Ssemble — Fase 1 (nucleo del pipeline)

Convierte un video largo (YouTube, Vimeo, Twitch, Kick) en varios clips
verticales listos para Shorts/TikTok/Reels: recorte con seguimiento de
rostro + subtitulos automaticos, usando solo herramientas gratuitas que
corren en tu propia maquina.

## Instalacion (Windows)

1. **Python 3.10 o 3.11** (evita 3.13 por ahora; mediapipe puede no tener
   wheels compatibles todavia). Verifica con `python --version`.

2. **ffmpeg** — necesario para cortar y codificar video.
   ```
   winget install ffmpeg
   ```
   Verifica con `ffmpeg -version` en una terminal nueva.

3. **Ollama** (LLM local) — https://ollama.com/download
   Una vez instalado:
   ```
   ollama pull llama3.2:3b
   ```
   Esto deja el servicio corriendo en `localhost:11434`.

4. **GPU (opcional pero muy recomendable)** — Si tienes GPU NVIDIA con
   drivers actualizados, instala CUDA Toolkit + cuDNN para que
   faster-whisper use la GPU (mucho mas rapido). Si da problemas, cambia
   `WHISPER_DEVICE = "cpu"` en `config.py` — funciona igual, solo mas lento.

5. Dependencias de Python:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

## Uso

```
python main.py "https://www.youtube.com/watch?v=XXXXXXXX" --clips 5
```

Los clips finales quedan en `output/`.

## Ajustes utiles (config.py)

- `WHISPER_MODEL`: sube a `"large-v3"` si tu GPU aguanta, para mejor
  precision de transcripcion (importante en espanol con acentos/modismos).
- `OLLAMA_MODEL`: si tu GPU tiene 6GB+ de VRAM libres, prueba
  `"llama3.1:8b"` para mejores decisiones de que momentos son "virales".
- `CLIP_MIN_SECONDS` / `CLIP_MAX_SECONDS`: rango de duracion de los clips.
- `SUBTITLE_WORDS_PER_CHUNK`: cuantas palabras se muestran a la vez en los
  subtitulos (3 = estilo TikTok tipico).

## Que falta para llegar al nivel de Ssemble (proximas fases)

- Interfaz web (Next.js + FastAPI) en vez de linea de comandos — Fase 2
- Publicacion automatica a YouTube/TikTok/Instagram — Fase 3
- Cola de trabajos para procesar varios videos sin bloquear la app — Fase 2
- Modo Deportes, audio multilingue, automatizacion de canal — Fase 4

## Notas honestas

- Que tan bien elige "lo viral" depende 100% de la calidad del modelo de
  Ollama que uses. Con un modelo de 3B vas a tener que revisar y ajustar
  los clips a mano mas seguido que con un modelo grande (los que usa
  Ssemble por detras son mucho mas grandes y corren en servidores propios).
- El recorte por rostro (`crop.py`) usa un detector simple por ahora: si en
  el video hablan dos o mas personas alternadamente, la camara puede
  "saltar" de forma menos elegante que en Ssemble. Se puede mejorar mas
  adelante agregando deteccion de quien esta hablando (active speaker
  detection).
