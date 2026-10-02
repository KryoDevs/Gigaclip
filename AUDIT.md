# Auditoría de Gigaclip

**Alcance:** lectura estática del backend Flask, pipeline FFmpeg/Whisper, selección LLM, publicador, interfaz, configuración y Docker. La revisión no pudo ejecutar una transcodificación de extremo a extremo porque este entorno no tiene instaladas las dependencias de ejecución ni modelos/FFmpeg.

## 10 cosas que están bien

1. **Responsabilidades separadas:** descarga, audio, transcripción, selección, recorte, subtítulos y publicación viven en módulos distintos.
2. **CLI y web reutilizan el mismo pipeline**, evitando duplicar la lógica principal de vídeo.
3. **Whisper se carga de forma perezosa** y el modelo de transcripción se reutiliza durante la vida del proceso.
4. **Hay caché de transcripciones**, útil para no repetir el trabajo costoso al volver a editar un mismo vídeo.
5. **Existe un modo de respaldo** si Ollama/OpenAI/DeepSeek no responde, y se puede ejecutar Ollama localmente.
6. **Los procesos externos se invocan con listas de argumentos**, no interpolando comandos en un shell.
7. **La configuración audiovisual está centralizada** (calidad, códec, duración, Whisper, Ollama).
8. **Hay opciones de subtítulos, calidad, estrategia de extracción y aceleración** que cubren usos distintos.
9. **El pipeline informa progreso y conserva metadatos/timestamps** para que la interfaz muestre resultados y permita re-renderizar.
10. **La interfaz ofrece carga local, vista previa y descarga**, y Docker crea una ruta reproducible para desplegar la app.

## 10 cosas que estaban mal (y estado de corrección)

| # | Hallazgo / impacto | Estado en esta revisión |
|---|---|---|
| 1 | `/api/process` aceptaba rutas locales arbitrarias; `/api/clip/re-render` podía leer cualquier archivo accesible por el proceso y entregarlo a FFmpeg. | **Corregido:** sólo se aceptan videos existentes dentro de las carpetas administradas, también tras resolver symlinks. |
| 2 | La interfaz insertaba títulos, subtítulos/metadatos y logs con `innerHTML`; el título también entraba en handlers inline. Un nombre o respuesta hostil podía ejecutar JavaScript (XSS). | **Corregido:** renderizado con `textContent`/nodos y listeners; los logs ya no se interpretan como HTML. |
| 3 | `GET /api/social/settings` devolvía claves LLM, tokens Telegram, IDs y la URL del webhook. | **Corregido:** la respuesta sólo incluye campos de UI y booleanos de “configurado”; valores vacíos al guardar conservan secretos. |
| 4 | Los parámetros de proceso se convertían a `int` sin control y se aceptaban estilos/duraciones/cantidades arbitrarios; solicitudes mal formadas acababan en 500 o trabajos desmedidos. | **Corregido:** validación de esquema, rangos y opciones permitidas antes de crear el trabajo. |
| 5 | Los timestamps del LLM sólo comprobaban `end > start`; podía pedir tramos fuera del video o fuera del rango configurado y el pipeline intentaba renderizarlos. | **Corregido:** se descartan clips no finitos, fuera de límites o con duración fuera del rango. |
| 6 | El upload usaba segundos + nombre del cliente (colisiones) y no validaba extensiones. El re-render también generaba nombres potencialmente repetidos por segundo. | **Corregido:** nombres UUID y lista de extensiones permitidas; nombres únicos para re-render. |
| 7 | La marca de agua se aceptaba en la API, pero no se pasaba al constructor de filtros; además, texto con delimitadores podía romper el filtro FFmpeg. | **Corregido:** se pasa al filtro y se escapan caracteres especiales. |
| 8 | El render usaba `-ss` junto a `-to` en posición de entrada, haciendo ambiguo/inconsistente el final del clip según FFmpeg. | **Corregido:** `-ss` para buscar y `-t` de salida con `end - start`. |
| 9 | El análisis de audio leía el WAV entero a RAM y descartaba la última ventana parcial; vídeos largos podían consumir memoria excesiva y perder datos. | **Corregido:** ventanas PCM leídas de forma incremental, incluida la cola parcial. |
| 10 | Los WAV temporales compartían nombre en trabajos concurrentes y no siempre se limpiaban; la caché identificaba el archivo sólo por nombre y tamaño, por lo que podía devolver una transcripción de otro video. | **Corregido:** temporales únicos con limpieza `finally`; clave de caché con ruta/tamaño/mtime/modelo y parámetros relevantes. |

**Otros fallos detectados y tratados durante el loop:** el scheduler arrancaba al importar el módulo y ocultaba sus errores (ahora se inicia explícitamente y registra excepciones); la función de YouTube podía afirmar que subió un video sin hacer la llamada OAuth (ahora declara que no está implementada); el montaje de un archivo `social_config.json` inexistente en Docker podía crear un directorio incompatible (ahora la configuración persiste en `./data/`); el webhook usaba URLs `localhost` inutilizables desde servicios externos (ahora se configura la URL pública y, con API key, se firma por tiempo limitado el acceso al medio).

**Riesgo residual importante:** la API key es opcional para conservar el flujo de instalación local. Antes de exponer Gigaclip en una red, define `GIGACLIP_API_KEY` (y, si hay varios workers, un `GIGACLIP_SESSION_SECRET` estable); de lo contrario, cualquier usuario con acceso al puerto puede enviar trabajos y cambiar integraciones. El contenedor sigue publicando el puerto 5000. Además, el webhook envía metadatos, no el binario: el consumidor sólo obtiene el video si `GIGACLIP_PUBLIC_URL` es accesible para él.

## 10 cosas que se pueden mejorar

1. **Autenticación por defecto y límites de tasa/cuota**, no sólo una API key optativa. (La puerta de autenticación y protección de `/output/` ya están implementadas cuando se configura la variable.)
2. Persistir trabajos y progreso en SQLite/Redis; hoy `jobs` vive en memoria y desaparece al reiniciar.
3. Añadir pruebas de integración con Flask, FFmpeg y medios sintéticos; por ahora hay tests puros de validación.
4. Fijar versiones de dependencias y añadir CI (lint, tipos, tests y build Docker).
5. Validar duración/códecs/streams con `ffprobe` antes de usar CPU/GPU y ofrecer errores claros cuando un video no tenga audio.
6. Cambiar el promedio de rostros de todo el clip por seguimiento temporal con suavizado; hoy el “face track” es un centro promedio.
7. Hacer la interfaz responsive y accesible (teclado, etiquetas, contraste, manejo de carga/progreso y errores).
8. Completar la subida real a YouTube OAuth/YouTube Data API; ahora se devuelve “no implementada”, no éxito ficticio.
9. Ofrecer envío real del video a webhooks o almacenamiento temporal firmado; hoy se transmite JSON de metadatos y una URL opcional.
10. Usar un worker/cola durable para scheduler y transcodificación, con reintentos, idempotencia y observabilidad multi-proceso.

## Loop de revisión aplicado

1. **Inventario y lectura:** inspeccioné todos los módulos, rutas API, plantilla, configuración y despliegue Docker; compilación Python inicial correcta.
2. **Primera pasada de hallazgos:** identifiqué exposición de rutas/secretos, XSS, validación insuficiente, problemas de recorte/audio/cache, scheduler y falsos positivos en publicación.
3. **Implementación:** apliqué límites de entrada/rutas, salida segura en DOM, ocultación de secretos, autenticación opcional, correcciones de FFmpeg/Whisper/audio, seguridad de publicación, persistencia Docker y tests unitarios.
4. **Segunda pasada:** busqué usos restantes de `innerHTML`/`localhost`, revisé el diff, corregí la autenticación para incluir `/output/` y retiré cachés de transcripciones que estaban versionadas.
5. **Revalidación:** `python -m unittest discover -s tests -v` (10/10 OK), `compileall` y `git diff --check`.
