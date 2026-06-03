#!/bin/bash
# ============================================================
# Instalación Optimizada para Raspberry Pi 4 y Pi 5
# Ejecutar como: bash install_face_recognition.sh
# ============================================================

# Salir si ocurre un error
set -e

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

# --- TRUCO CRÍTICO PARA RASPBERRY PI 4 ---
# Aumentar temporalmente la memoria SWAP para que dlib no congele la Pi 4
echo "=== [Ajuste Pi 4] Incrementando memoria SWAP temporalmente ==="
sudo dphys-swapfile swapoff || true
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
# -----------------------------------------

echo "=== [3/5] Creando entorno virtual ==="
# Usamos --system-site-packages para heredar python3-picamera2 del sistema
python3 -m venv venv --system-site-packages
source venv/bin/activate

echo "=== [4/5] Instalando librerías Python ==="
pip install --upgrade pip

echo "=== Compilando dlib (Usa todos los cores disponibles) ==="
# El flag CMAKE_BUILD_PARALLEL_LEVEL acelera drásticamente la compilación en Pi 4/5
export CMAKE_BUILD_PARALLEL_LEVEL=$(nproc)
pip install dlib

echo "=== Instalando el resto del stack ==="
pip install face_recognition fastapi uvicorn pyserial opencv-python-headless numpy Pillow

# --- RESTAURAR SWAP ---
echo "=== [Ajuste Pi 4] Restaurando memoria SWAP original ==="
sudo dphys-swapfile swapoff || true
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=100/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
# -----------------------

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
print('Todo listo y funcionando perfectamente.')
"