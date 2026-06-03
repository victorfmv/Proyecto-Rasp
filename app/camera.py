"""
app/camera.py
Módulo de captura de cámara con soporte de simulación para desarrollo sin hardware.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class Camera:
    """
    Abstracción de cámara. Intenta usar picamera2 (Pi Camera CSI).
    Si no está disponible, usa OpenCV (webcam USB).
    Si ninguna está disponible, activa el modo simulación automática.
    """

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self._cam = None
        self._backend = None
        self._init_camera()

    def _init_camera(self):
        # 1. Intentar picamera2 primero (Pi Camera CSI de la Pi 5 / Pi 4)
        try:
            from picamera2 import Picamera2

            self._cam = Picamera2()
            config = self._cam.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}
            )
            self._cam.configure(config)
            self._cam.start()
            self._backend = "picamera2"
            logger.info(f"Cámara iniciada con picamera2 ({self.width}x{self.height})")
            return
        except Exception as e:
            logger.warning(f"picamera2 no disponible ({e}), intentando OpenCV...")

        # 2. Fallback a OpenCV (Webcam USB o cámara integrada)
        try:
            import cv2

            self._cam = cv2.VideoCapture(0)
            self._cam.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            if self._cam.isOpened():
                self._backend = "opencv"
                logger.info(f"Cámara iniciada con OpenCV ({self.width}x{self.height})")
                return
        except Exception as e:
            logger.warning(f"OpenCV no pudo abrir hardware de video ({e})")

        # 3. Modo Simulación (Si no hay ninguna cámara física conectada)
        self._backend = "simulation"
        logger.info("--- [MODO SIMULACIÓN] Iniciado sin cámara física ---")

    def capture_rgb(self) -> np.ndarray:
        """
        Captura un frame real o genera uno simulado si no hay hardware.
        Retorna array numpy RGB (H, W, 3).
        """
        if self._backend == "picamera2":
            return self._cam.capture_array()

        elif self._backend == "opencv":
            import cv2

            ret, frame = self._cam.read()
            if not ret:
                raise RuntimeError("Error leyendo frame de la cámara física.")
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        elif self._backend == "simulation":
            # Generar un frame gris sintético de 640x480
            frame = np.ones((self.height, self.width, 3), dtype=np.uint8) * 60
            
            # Dibujar un texto que indique que es una simulación
            import cv2
            import time
            cv2.putText(
                frame,
                f"SIMULACION - SIN CAMARA PHYSICAL",
                (30, self.height // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )
            cv2.putText(
                frame,
                f"Timestamp: {time.strftime('%H:%M:%S')}",
                (30, (self.height // 2) + 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                1
            )
            return frame

    def capture_jpeg(self, quality: int = 85) -> bytes:
        """Captura un frame y lo retorna como bytes JPEG para la UI."""
        import cv2

        frame_rgb = self.capture_rgb()
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        _, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buffer.tobytes()

    def release(self):
        """Libera recursos de la cámara."""
        if self._cam:
            if self._backend == "picamera2":
                self._cam.stop()
            elif self._backend == "opencv":
                self._cam.release()
        logger.info("Recursos de cámara cerrados.")