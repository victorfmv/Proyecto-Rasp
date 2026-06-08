#!/bin/bash
# Script para ejecutar el Smart Lock sin logs verbosos de libcamera

# Deshabilitar logs de DEBUG de libcamera
export LIBCAMERA_LOG_LEVELS="*:WARNING"

# Opcional: si quieres logs de ERROR solamente
export LIBCAMERA_LOG_LEVELS="*:ERROR"

# Ejecutar la aplicación
python main.py
