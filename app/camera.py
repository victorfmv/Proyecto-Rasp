"""
app/camera.py - MODO PRUEBA SIN CÁMARA
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self._backend = "dummy"
        logger.info("Modo prueba activo — sin cámara física.")

    def capture_rgb(self) -> np.ndarray:
        import cv2
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        cv2.putText(frame, "Sin camara - modo prueba",
                    (80, 240), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (80, 80, 80), 2)
        return frame

    def capture_jpeg(self, quality: int = 85) -> bytes:
        import cv2
        frame_rgb = self.capture_rgb()
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        _, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buffer.tobytes()

    def release(self):
        logger.info("Cámara dummy liberada.")
