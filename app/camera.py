"""
app/camera.py
Módulo de captura de cámara con Pi Camera (libcamera).
"""

import logging
import threading
import numpy as np

logger = logging.getLogger(__name__)


class Camera:
    """
    Captura de cámara usando picamera2 (libcamera architecture).
    Requiere cámara Pi Camera conectada al puerto CSI.
    """

    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self._cam = None
        self._capture_lock = threading.Lock()
        self._init_camera()

    def _init_camera(self):
        """Inicializa la cámara Pi usando picamera2."""
        try:
            from picamera2 import Picamera2

            self._cam = Picamera2()
            config = self._cam.create_preview_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}
            )
            self._cam.configure(config)
            self._cam.start()
            logger.info(f"✓ Cámara Pi iniciada con libcamera ({self.width}x{self.height})")
            
        except ImportError:
            logger.error("❌ ERROR: picamera2 no está instalado. Instala con: pip install picamera2")
            raise RuntimeError("picamera2 requerido pero no disponible")
        except Exception as e:
            logger.error(f"❌ ERROR inicializando cámara Pi: {e}")
            logger.error("Verifica que la cámara está conectada al puerto CSI y habilitada en raspi-config")
            raise RuntimeError(f"Error al inicializar cámara: {e}")

    def capture_rgb(self) -> np.ndarray:
        """
        Captura un frame RGB de la cámara.
        Retorna: array numpy RGB (H, W, 3)
        """
        if not self._cam:
            raise RuntimeError("Cámara no inicializada")

        with self._capture_lock:
            try:
                frame = self._cam.capture_array()
                return frame
            except Exception as e:
                logger.error(f"Error capturando frame: {e}")
                raise

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
            self._cam.stop()
            logger.info("✓ Cámara cerrada correctamente")