# Gigaclip 🎬

Convierte videos largos (YouTube, Vimeo, Twitch, Kick) en clips verticales virales (Shorts, TikTok, Reels) con IA: recorte inteligente con seguimiento de rostro + subtítulos automáticos dinámicos (estilo Alex Hormozi), todo ejecutado localmente con herramientas gratuitas.

---

## 🚀 Características

- 🎯 **Detección y seguimiento de rostro** para recorte vertical 9:16 automático.
- ⚡ **Subtítulos dinámicos** con 4 estilos: Hormozi (palabra activa resaltada en oro), Karaoke, Clásico y Minimal.
- 🧠 **Selección inteligente de momentos virales** impulsada por LLM local (Ollama `llama3.2:3b`).
- 🏎️ **Transcripción ultra rápida** con faster-whisper y sistema de caché de transcripciones.
- 🌐 **Interfaz Web Moderna (Gigaclip UI)** para procesar y previsualizar clips en el navegador.

---

## 🛠️ Instalación y Requisitos (Windows)

1. **Python 3.10 - 3.14**
2. **FFmpeg** (necesario para procesamiento de video y subtítulos):
   ```powershell
   winget install ffmpeg
   ```
3. **Ollama** (LLM local para selección de clips):
   - Descarga desde [ollama.com](https://ollama.com)
   - Descarga el modelo:
     ```powershell
     ollama pull llama3.2:3b
     ```

4. **Instalar dependencias de Python:**
   ```powershell
   pip install -r requirements.txt
   ```

---

## 💻 Uso

### Opción 1: Interfaz Web (Recomendado)
Inicia el servidor web:
```powershell
python app.py
```
Abre en tu navegador: **[http://localhost:5000](http://localhost:5000)**

### Opción 2: Línea de Comandos (CLI)
```powershell
python main.py "https://www.youtube.com/watch?v=XXXXXXXX" --clips 5
```

Los clips finales se guardan en la carpeta `output/`.

### Seguridad y publicación por webhook

- El servidor escucha en `0.0.0.0:5000` para admitir Docker y acceso desde la red. Puedes proteger la API definiendo `GIGACLIP_API_KEY` (la interfaz solicitará la clave al usar la API); en Docker, colócalas en un `.env` local (ignorado por Git). Configura además un `GIGACLIP_SESSION_SECRET` estable si ejecutas varios workers y `GIGACLIP_COOKIE_SECURE=true` detrás de HTTPS. Sin `GIGACLIP_API_KEY`, **no publiques el servidor en Internet**: úsalo sólo en un equipo/red de confianza o detrás de un proxy con autenticación y TLS. Usa siempre HTTPS cuando la clave viaje por una red no confiable.
- Los videos de la interfaz sólo se pueden elegir desde las carpetas administradas de cargas/descargas; el servidor valida opciones, rutas y nombres de salida.
- Los secretos de LLM/Telegram/webhook no se devuelven a la interfaz una vez guardados. Para cambiarlos, introduce un valor nuevo; vacío conserva el actual.
- Los webhooks reciben metadatos y una URL, no el archivo binario. Si el automatizador necesita descargar el video, configura `GIGACLIP_PUBLIC_URL` con una URL HTTPS públicamente accesible que apunte a esta instancia. No uses una URL localhost.
- En Docker, los ajustes y la cola se conservan en `./data/`.

Pruebas de validación sin modelos ni FFmpeg:
```bash
python -m unittest discover -s tests -v
```

---

## ⚙️ Configuración (`config.py`)

- `WHISPER_DEVICE`: `"cpu"` o `"cuda"` (si tienes GPU NVIDIA con CUDA).
- `WHISPER_MODEL`: `"small"`, `"medium"`, o `"large-v3"`.
- `SUBTITLE_STYLE`: `"hormozi"`, `"karaoke"`, `"classic"`, o `"minimal"`.
- `DOWNLOAD_MAX_HEIGHT`: `720` (optimizado para velocidad).
