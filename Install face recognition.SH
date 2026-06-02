#!/bin/bash
# ============================================================
# Instalación de face_recognition en Raspberry Pi 5
# Ejecutar como: bash install_face_recognition.sh
# Tiempo estimado: 20-40 minutos (compilar dlib es lento)
# ============================================================

echo "=== [1/5] Actualizando paquetes del sistema ==="
sudo apt update && sudo apt upgrade -y

echo "=== [2/5] Instalando dependencias del sistema ==="
sudo apt install -y \
    python3-pip \
    python3-venv \
    cmake \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libjpeg-dev \
    libpng-dev \
    libatlas-base-dev \
    python3-picamera2 \
    libcamera-dev

echo "=== [3/5] Creando entorno virtual ==="
python3 -m venv venv --system-site-packages
# --system-site-packages es IMPORTANTE para acceder a picamera2
# que se instala a nivel sistema en la Pi

source venv/bin/activate

echo "=== [4/5] Instalando librerías Python ==="
pip install --upgrade pip

# dlib primero (es el más pesado, ~20-30 min compilando en Pi)
pip install dlib

# face_recognition encima de dlib
pip install face_recognition

# El resto del stack
pip install \
    fastapi \
    uvicorn \
    pyserial \
    opencv-python-headless \
    numpy \
    Pillow

echo "=== [5/5] Verificando instalación ==="
python3 -c "
import face_recognition
import cv2
import serial
import fastapi
print('face_recognition:', face_recognition.__version__ if hasattr(face_recognition, '__version__') else 'OK')
print('opencv:', cv2.__version__)
print('pyserial: OK')
print('fastapi: OK')
print()
print('Todo instalado correctamente.')
"

echo ""
echo "Para activar el entorno siempre usa:"
echo "  source venv/bin/activate"
echo "Luego corre el proyecto con:"
echo "  python main.py"