"""
Recorta el video a formato vertical 9:16 siguiendo el rostro (estilo Ssemble).

Estrategia:
1. Muestrea la posicion del rostro cada N frames con MediaPipe (rapido).
2. Suaviza esa trayectoria (evita saltos bruscos de camara).
3. Recorre el video frame a frame con OpenCV, recortando una ventana 9:16
   centrada en la posicion interpolada del rostro para ese frame.
4. Escribe el video recortado (sin audio). El audio se agrega despues
   en subtitles.py, junto con los subtitulos quemados.
"""
import numpy as np
import cv2

from config import FACE_SAMPLE_EVERY, BASE_DIR


def _detect_face_centers(video_path: str, sample_every: int = FACE_SAMPLE_EVERY):
    """
    Devuelve una lista de (frame_index, center_x_norm, center_y_norm) muestreada.
    Si no detecta rostro en un frame muestreado, ese punto simplemente no
    se agrega (se interpola despues con los vecinos).
    """
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
                # Toma el rostro mas grande (asume que es el hablante principal)
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
    """
    Interpola linealmente entre los puntos detectados para tener un centro
    por cada frame. Si no hay detecciones en todo el video, usa un centro
    por defecto (0.5, 0.4 -> ligeramente arriba del centro geometrico,
    encuadre tipico de rostro).
    """
    centers = np.tile([default_cx, default_cy], (total_frames, 1)).astype(float)

    if not detections:
        return centers

    idxs = np.array([d[0] for d in detections])
    cxs = np.array([d[1] for d in detections])
    cys = np.array([d[2] for d in detections])

    all_idx = np.arange(total_frames)
    centers[:, 0] = np.interp(all_idx, idxs, cxs)
    centers[:, 1] = np.interp(all_idx, idxs, cys)

    # Suavizado (media movil) para que la "camara" no tiemble entre frames
    window = 15
    kernel = np.ones(window) / window
    for col in range(2):
        padded = np.pad(centers[:, col], (window // 2, window // 2), mode="edge")
        centers[:, col] = np.convolve(padded, kernel, mode="valid")[:total_frames]

    return centers


def crop_to_vertical(input_path: str, output_path_noaudio: str, target_ratio: float = 9 / 16) -> None:
    """
    Genera output_path_noaudio: el video recortado a 9:16, SIN audio.
    """
    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # Ventana de recorte: alto completo, ancho = alto * 9/16 (video horizontal tipico)
    crop_h = height
    crop_w = int(height * target_ratio)
    if crop_w > width:
        # El video ya es angosto: usa ancho completo y recorta el alto
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


if __name__ == "__main__":
    import sys
    crop_to_vertical(sys.argv[1], sys.argv[2])
