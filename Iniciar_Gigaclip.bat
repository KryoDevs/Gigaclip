@echo off
title Gigaclip Studio - Iniciador Profesional
color 0B

echo ========================================================
echo          GIGACLIP STUDIO - INICIADOR (1-CLICK)
echo ========================================================
echo.

:: Verificar si Python esta instalado
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no esta instalado o no esta en el PATH.
    echo Por favor instala Python 3.10 o superior (marca "Add Python to PATH").
    pause
    exit /b
)

:: Verificar si FFmpeg esta instalado
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ADVERTENCIA] FFmpeg no esta instalado en el sistema.
    echo Asegurate de tener FFmpeg instalado para que el renderizado funcione.
    echo.
)

:: Crear entorno virtual si no existe
if not exist "venv\" (
    echo [1/3] Creando entorno virtual aislado (venv)...
    python -m venv venv
)

:: Activar entorno e instalar dependencias silenciosamente
echo [2/3] Verificando dependencias...
call venv\Scripts\activate
pip install -r requirements.txt >nul 2>&1

:: Iniciar servidor
echo [3/3] Iniciando el servidor de Gigaclip Studio...
echo.
echo ========================================================
echo TODO LISTO! Puedes minimizar esta ventana negra.
echo Abre tu navegador en: http://127.0.0.1:5000
echo ========================================================
echo.

:: Abrir navegador automaticamente
start http://127.0.0.1:5000

:: Ejecutar Flask
python app.py

pause
