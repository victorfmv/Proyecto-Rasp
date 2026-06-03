"""
app/camera.py
Módulo de captura de cámara.
Usa picamera2 (la librería oficial para Pi 5) con fallback a OpenCV para pruebas.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class Camera:
    """
    Abstracción de cámara. Intenta usar picamera2 (Pi Camera CSI).
    Si no está disponible, usa OpenCV (webcam USB o cámara virtual).
    """

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self._cam = None
        self._backend = None
        self._init_camera()

    def _init_camera(self):
        # Intentar picamera2 primero (Pi Camera CSI)
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
        except Exception as e:
            logger.warning(f"picamera2 no disponible ({e}), usando OpenCV.")

            # Fallback a OpenCV (USB o cámara virtual para desarrollo)
            import cv2

            self._cam = cv2.VideoCapture(0)
            self._cam.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._cam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            if not self._cam.isOpened():
                raise RuntimeError("No se pudo abrir ninguna cámara.")

            self._backend = "opencv"
            logger.info(f"Cámara iniciada con OpenCV ({self.width}x{self.height})")

    def capture_rgb(self) -> np.ndarray:
        """
        Captura un frame y lo retorna como array numpy RGB (H, W, 3).
        face_recognition espera RGB, OpenCV da BGR — se hace la conversión.
        """
        if self._backend == "picamera2":
            # picamera2 ya entrega RGB888
            return self._cam.capture_array()

        elif self._backend == "opencv":
            import cv2

            ret, frame = self._cam.read()
            if not ret:
                raise RuntimeError("Error leyendo frame de la cámara.")
            # OpenCV es BGR → convertir a RGB
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def capture_jpeg(self, quality: int = 85) -> bytes:
        """
        Captura un frame y lo retorna como bytes JPEG.
        Útil para enviar a la UI web.
        """
        import cv2

        frame_rgb = self.capture_rgb()
        # RGB → BGR para que OpenCV encodifique bien
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
            logger.info("Cámara liberada.")
