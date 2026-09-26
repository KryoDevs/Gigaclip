"""
Motor de reencuadre vertical 9:16 para Gigaclip.
Soporta tres modos de recorte:
  1. "face_track":     Seguimiento facial dinamico y suavizado.
  2. "podcast_split":  Modo Podcast/Entrevista: divide el video en dos tomas
                       apiladas verticalmente (arriba y abajo) en formato 9:16.
  3. "blur_background": Canvas 9:16 con fondo desenfocado y video centrado.
"""
import subprocess
import numpy as np
import cv2
from pathlib import Path

from config import FACE_SAMPLE_EVERY, BASE_DIR, FFMPEG_BIN, TEMP_DIR


def _detect_face_centers(video_path: str, sample_every: int = FACE_SAMPLE_EVERY):
    """Detecta la posicion central de rostros frame a frame con suavizado."""
    cap = cv2.VideoCapture(video_path)
    detections = []
    idx = 0
    
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cascade_path = str(BASE_DIR / 'haarcascade_frontalface_default.xml')
    face_cascade = cv2.CascadeClassifier(cascade_path)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % sample_every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.3, 5)
            if len(faces) > 0:
                best_face = max(faces, key=lambda f: f[2] * f[3])
                x, y, w, h = best_face
                cx = (x + w / 2) / width
                cy = (y + h / 2) / height
                detections.append((idx, cx, cy))
        idx += 1

    cap.release()
    return detections


def _interpolate_centers(detections, total_frames: int,
                          default_cx: float = 0.5, default_cy: float = 0.4) -> np.ndarray:
    centers = np.tile([default_cx, default_cy], (total_frames, 1)).astype(float)
    if not detections:
        return centers

    idxs = np.array([d[0] for d in detections])
    cxs = np.array([d[1] for d in detections])
    cys = np.array([d[2] for d in detections])

    all_idx = np.arange(total_frames)
    centers[:, 0] = np.interp(all_idx, idxs, cxs)
    centers[:, 1] = np.interp(all_idx, idxs, cys)

    # Suavizado exponencial / media movil
    window = 15
    kernel = np.ones(window) / window
    for col in range(2):
        padded = np.pad(centers[:, col], (window // 2, window // 2), mode="edge")
        centers[:, col] = np.convolve(padded, kernel, mode="valid")[:total_frames]

    return centers


def _crop_face_track(input_path: str, output_path_noaudio: str, target_ratio: float = 9 / 16) -> None:
    """Recorte vertical siguiendo al hablante con OpenCV."""
    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    crop_h = height
    crop_w = int(height * target_ratio)
    if crop_w > width:
        crop_w = width
        crop_h = int(width / target_ratio)

    detections = _detect_face_centers(input_path)
    centers = _interpolate_centers(detections, total_frames)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path_noaudio, fourcc, fps, (crop_w, crop_h))

    cap = cv2.VideoCapture(input_path)
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        cx_norm, cy_norm = centers[min(idx, len(centers) - 1)]
        cx = int(cx_norm * width)
        cy = int(cy_norm * height)

        x0 = int(np.clip(cx - crop_w / 2, 0, width - crop_w))
        y0 = int(np.clip(cy - crop_h / 2, 0, height - crop_h))

        cropped = frame[y0:y0 + crop_h, x0:x0 + crop_w]
        writer.write(cropped)
        idx += 1

    cap.release()
    writer.release()


def _crop_podcast_split(input_path: str, output_path_noaudio: str) -> None:
    """
    Modo Podcast: Divide un video horizontal (16:9) en dos mitades (izquierda y derecha)
    y las apila verticalmente en una composicion 9:16 perfecta.
    """
    cap = cv2.VideoCapture(input_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    # Filtro complejo FFmpeg para split screen apilado vertical
    # Mitad izquierda arriba, mitad derecha abajo
    half_w = w // 2
    filter_complex = (
        f"[0:v]crop={half_w}:{h}:0:0,scale=720:640[top];"
        f"[0:v]crop={half_w}:{h}:{half_w}:0,scale=720:640[bottom];"
        f"[top][bottom]vstack=inputs=2[out]"
    )

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        output_path_noaudio
    ]
    subprocess.run(cmd, check=True)


def _crop_blur_background(input_path: str, output_path_noaudio: str) -> None:
    """
    Modo Fondo Desenfocado: Canvas 9:16 vertical con fondo borroso y video centrado.
    Ideal para clips donde el recorte facial cortaria elementos visuales clave.
    """
    filter_complex = (
        "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=20:5[bg];"
        "[0:v]scale=720:1280:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
    )

    cmd = [
        FFMPEG_BIN, "-y",
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-an",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        output_path_noaudio
    ]
    subprocess.run(cmd, check=True)


def crop_to_vertical(input_path: str, output_path_noaudio: str, mode: str = "face_track") -> None:
    """
    Enrutador principal de recorte a formato vertical 9:16.
    mode: 'face_track' | 'podcast_split' | 'blur_background'
    """
    if mode == "podcast_split":
        _crop_podcast_split(input_path, output_path_noaudio)
    elif mode == "blur_background":
        _crop_blur_background(input_path, output_path_noaudio)
    else:
        _crop_face_track(input_path, output_path_noaudio)


if __name__ == "__main__":
    import sys
    crop_to_vertical(sys.argv[1], sys.argv[2])
