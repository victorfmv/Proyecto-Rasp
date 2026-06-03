#!/bin/bash
# ============================================================
# Instalación Universal y Optimizada: Smart Lock (Pi 4 y Pi 5)
# Ejecutar como: bash install_face_recognition.sh
# ============================================================

# Detener el script si ocurre un error inesperado
set -e

echo "=== [1/5] Actualizando repositorios del sistema ==="
sudo apt update && sudo apt upgrade -y

echo "=== [2/5] Instalando dependencias nativas de Linux ==="
# Nota: libatlas-base-dev fue retirado; usamos libopenblas-dev en su lugar.
sudo apt install -y \
    python3-pip \
    python3-venv \
    cmake \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libjpeg-dev \
    libpng-dev \
    python3-picamera2 \
    libcamera-dev

# --- TRUCO DE MEMORIA PARA EVITAR CONGELAMIENTOS EN PI 4 ---
echo "=== [Ajuste de Memoria] Creando archivo SWAP temporal de 2GB ==="
# Si el sistema ya tiene un swapfile activo de pruebas previas, lo limpia de forma segura
if [ -f /swapfile ]; then
    sudo swapoff /swapfile || true
    sudo rm /swapfile
fi
sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
# -----------------------------------------------------------

echo "=== [3/5] Configurando el Entorno Virtual (venv) ==="
# --system-site-packages es mandatorio para que el venv herede la librería picamera2 del OS
python3 -m venv venv --system-site-packages
source venv/bin/activate

echo "=== [4/5] Instalando librerías de Python ==="
pip install --upgrade pip

echo "--> Compilando dlib a máxima velocidad..."
# nproc detecta cuántos núcleos tiene el CPU (4 en la Pi 4) y los usa todos en paralelo
export CMAKE_BUILD_PARALLEL_LEVEL=$(nproc)
pip install dlib

echo "--> Instalando dependencias desde requirements.txt..."
pip install -r requirements.txt

# --- LIMPIEZA DE ENTORNO ---
echo "=== [Limpieza] Removiendo archivo SWAP temporal ==="
sudo swapoff /swapfile || true
sudo rm /swapfile
# ----------------------------

echo "=== [5/5] Verificación de Componentes ==="
python3 -c "
import face_recognition
import cv2
import serial
import fastapi
import multipart
print('-> face_recognition:', face_recognition.__version__)
print('-> opencv-headless:', cv2.__version__)
print('-> python-multipart: OK')
print('-> pyserial: OK')
print('-> fastapi: OK')
print('\n[ÉXITO] Todo el entorno se ha configurado correctamente.')
"

echo ""
echo "Para iniciar tu ambiente de trabajo ejecuta siempre:"
echo "  source venv/bin/activate"
echo "Para arrancar el servidor de la cerradura inteligente:"
echo "  python main.py"