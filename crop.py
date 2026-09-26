"""
Motor ultra-rapido de recorte vertical 9:16 con calculo ligero de centro de rostro.
Calcula la posicion del rostro en pocos keyframes y delega todo el recorte
a FFmpeg nativo (acelerado por C/Hardware), eliminando el cuello de botella de OpenCV frame a frame.
"""
import subprocess
import cv2
from pathlib import Path

from config import BASE_DIR, FFMPEG_BIN, FACE_SAMPLE_FPS


def get_crop_coordinates(video_path: str, start_time: float, end_time: float, target_ratio: float = 9 / 16) -> tuple:
    """
    Analiza rapidamente la posicion media del rostro en el tramo del clip
    y devuelve (crop_w, crop_h, crop_x, crop_y) para FFmpeg.
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    crop_h = height
    crop_w = int(height * target_ratio)
    if crop_w > width:
        crop_w = width
        crop_h = int(width / target_ratio)

    # Posicionar en el inicio del clip
    cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
    
    cascade_path = str(BASE_DIR / 'haarcascade_frontalface_default.xml')
    face_cascade = cv2.CascadeClassifier(cascade_path)

    detected_centers = []
    # Muestrear solo 5 a 8 frames distribuidos en el clip
    duration = max(1.0, end_time - start_time)
    num_samples = min(10, max(3, int(duration * FACE_SAMPLE_FPS)))
    interval_msec = (duration * 1000) / num_samples

    for i in range(num_samples):
        cap.set(cv2.CAP_PROP_POS_MSEC, (start_time * 1000) + (i * interval_msec))
        ret, frame = cap.read()
        if not ret:
            break
        # Reducir imagen a 360p para deteccion ultra rapida
        small = cv2.resize(frame, (360, int(360 * height / width)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.2, 4)
        if len(faces) > 0:
            best = max(faces, key=lambda f: f[2] * f[3])
            # Escalar de vuelta a coordenadas reales
            scale = width / 360
            cx = (best[0] + best[2] / 2) * scale
            cy = (best[1] + best[3] / 2) * scale
            detected_centers.append((cx, cy))

    cap.release()

    if detected_centers:
        avg_cx = sum(c[0] for c in detected_centers) / len(detected_centers)
        avg_cy = sum(c[1] for c in detected_centers) / len(detected_centers)
    else:
        avg_cx = width / 2
        avg_cy = height * 0.45  # Enfoque tipico de cabeza y hombros

    crop_x = int(max(0, min(width - crop_w, avg_cx - crop_w / 2)))
    crop_y = int(max(0, min(height - crop_h, avg_cy - crop_h / 2)))

    return crop_w, crop_h, crop_x, crop_y


def build_ffmpeg_filter(video_path: str, start: float, end: float, ass_path_rel: str, mode: str = "face_track") -> str:
    """Construye un filtro combinado de FFmpeg (recorte + subtitulos) en 1 solo paso."""
    if mode == "podcast_split":
        # Split vertical apilado con subtitulos
        filter_str = (
            f"[0:v]crop=iw/2:ih:0:0,scale=720:640[top];"
            f"[0:v]crop=iw/2:ih:iw/2:0,scale=720:640[bottom];"
            f"[top][bottom]vstack=inputs=2[v_split];"
            f"[v_split]ass={ass_path_rel}[outv]"
        )
        return filter_str
    elif mode == "blur_background":
        filter_str = (
            f"[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=20:5[bg];"
            f"[0:v]scale=720:1280:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v_comp];"
            f"[v_comp]ass={ass_path_rel}[outv]"
        )
        return filter_str
    else:
        # Modo Face Track
        w, h, x, y = get_crop_coordinates(video_path, start, end)
        return f"crop={w}:{h}:{x}:{y},scale=720:1280,ass={ass_path_rel}"
