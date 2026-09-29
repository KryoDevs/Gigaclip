FROM python:3.11-slim

# Evitar que Python escriba archivos .pyc y forzar logs inmediatos
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar FFmpeg (dependencia critica) y librerias para OpenCV
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el codigo fuente
COPY . .

# Crear carpetas necesarias
RUN mkdir -p /app/downloads /app/output /app/assets/sfx /app/assets/fonts

# Exponer el puerto
EXPOSE 5000

# Iniciar la aplicacion
CMD ["python", "app.py"]
