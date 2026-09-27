"""
Motor de reencuadre vertical 9:16 de alta fidelidad para Gigaclip.
Soporta escalado Lanczos de alta nitidez, resoluciones 1080p Full HD / 720p HD,
y 3 modos de composicion: Face Track, Podcast Split y Blur Canvas.
"""
import subprocess
import cv2
from pathlib import Path

from config import BASE_DIR, FFMPEG_BIN, FACE_SAMPLE_FPS, VIDEO_QUALITY_PRESETS, DEFAULT_QUALITY


def get_crop_coordinates(video_path: str, start_time: float, end_time: float, target_ratio: float = 9 / 16) -> tuple:
    """
    Analiza la posicion del rostro en el tramo temporal exacto
    y calcula el bounding box centrado para recorte vertical.
    """
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    crop_h = height
    crop_w = int(height * target_ratio)
    if crop_w > width:
        crop_w = width
        crop_h = int(width / target_ratio)

    cascade_path = str(BASE_DIR / 'haarcascade_frontalface_default.xml')
    face_cascade = cv2.CascadeClassifier(cascade_path)

    detected_centers = []
    duration = max(1.0, end_time - start_time)
    num_samples = min(12, max(4, int(duration * FACE_SAMPLE_FPS)))
    interval_msec = (duration * 1000) / num_samples

    for i in range(num_samples):
        cap.set(cv2.CAP_PROP_POS_MSEC, (start_time * 1000) + (i * interval_msec))
        ret, frame = cap.read()
        if not ret:
            break
        # Deteccion sobre miniatura para maxima velocidad
        small_w = 480
        small_h = int(small_w * height / width)
        small = cv2.resize(frame, (small_w, small_h))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.15, 4)
        if len(faces) > 0:
            best = max(faces, key=lambda f: f[2] * f[3])
            scale = width / small_w
            cx = (best[0] + best[2] / 2) * scale
            cy = (best[1] + best[3] / 2) * scale
            detected_centers.append((cx, cy))

    cap.release()

    if detected_centers:
        avg_cx = sum(c[0] for c in detected_centers) / len(detected_centers)
        avg_cy = sum(c[1] for c in detected_centers) / len(detected_centers)
    else:
        avg_cx = width / 2
        avg_cy = height * 0.42

    crop_x = int(max(0, min(width - crop_w, avg_cx - crop_w / 2)))
    crop_y = int(max(0, min(height - crop_h, avg_cy - crop_h / 2)))

    return crop_w, crop_h, crop_x, crop_y


def build_ffmpeg_filter(video_path: str, start: float, end: float, ass_path_rel: str,
                        mode: str = "face_track", quality: str = DEFAULT_QUALITY) -> str:
    """
    Genera el grafo de filtros FFmpeg con escalado Lanczos,
    filtro de nitidez unsharp y subtitulos ASS.
    """
    preset_data = VIDEO_QUALITY_PRESETS.get(quality, VIDEO_QUALITY_PRESETS["1080p"])
    target_w = preset_data["width"]
    target_h = preset_data["height"]
    sharpen_filter = ",unsharp=5:5:0.6:5:5:0.0" if preset_data["sharpen"] else ""

    if mode == "podcast_split":
        # Split vertical apilado con escalado Lanczos
        half_h = target_h // 2
        filter_str = (
            f"[0:v]crop=iw/2:ih:0:0,scale={target_w}:{half_h}:flags=lanczos[top];"
            f"[0:v]crop=iw/2:ih:iw/2:0,scale={target_w}:{half_h}:flags=lanczos[bottom];"
            f"[top][bottom]vstack=inputs=2[v_split];"
            f"[v_split]ass={ass_path_rel}{sharpen_filter}[outv]"
        )
        return filter_str
    elif mode == "blur_background":
        filter_str = (
            f"[0:v]scale={target_w}:{target_h}:flags=lanczos:force_original_aspect_ratio=increase,crop={target_w}:{target_h},boxblur=25:6[bg];"
            f"[0:v]scale={target_w}:{target_h}:flags=lanczos:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v_comp];"
            f"[v_comp]ass={ass_path_rel}{sharpen_filter}[outv]"
        )
        return filter_str
    else:
        # Modo Face Track con escalado de alta precision
        w, h, x, y = get_crop_coordinates(video_path, start, end)
        return f"crop={w}:{h}:{x}:{y},scale={target_w}:{target_h}:flags=lanczos,zoompan=z='if(between(mod(in_time,6),3,6),1.15,1.0)':d=1:x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':s={target_w}x{target_h}:fps=30{sharpen_filter},ass={ass_path_rel}"


