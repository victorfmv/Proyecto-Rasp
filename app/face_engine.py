"""
app/face_engine.py
Módulo de reconocimiento facial.
Maneja: registro de caras, encodings, comparación en tiempo real.
"""

import os
import pickle
import logging
import numpy as np
import face_recognition
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# Carpeta donde se guardan las fotos originales de cada persona
FACES_DIR = Path("faces")
# Archivo donde se guardan los encodings calculados (para no recalcular siempre)
ENCODINGS_FILE = Path("faces/encodings.pkl")

# Umbral de similitud: menor = más estricto. 0.5 es conservador, 0.6 es estándar.
TOLERANCE = 0.5


class FaceEngine:
    """
    Motor de reconocimiento facial.
    Guarda encodings en disco para no recalcularlos cada vez que reinicia.
    """

    def __init__(self):
        FACES_DIR.mkdir(exist_ok=True)
        self.known_encodings: list[np.ndarray] = []
        self.known_names: list[str] = []
        self._load_encodings()

    # ------------------------------------------------------------------
    # Carga / guardado de encodings
    # ------------------------------------------------------------------

    def _load_encodings(self):
        """Carga encodings guardados desde disco."""
        if ENCODINGS_FILE.exists():
            with open(ENCODINGS_FILE, "rb") as f:
                data = pickle.load(f)
            self.known_encodings = data["encodings"]
            self.known_names = data["names"]
            logger.info(
                f"Encodings cargados: {len(self.known_names)} personas → {self.known_names}"
            )
        else:
            logger.info("No hay encodings guardados todavía.")

    def _save_encodings(self):
        """Persiste encodings a disco."""
        with open(ENCODINGS_FILE, "wb") as f:
            pickle.dump(
                {"encodings": self.known_encodings, "names": self.known_names}, f
            )
        logger.info("Encodings guardados en disco.")

    # ------------------------------------------------------------------
    # Registro de nuevas caras
    # ------------------------------------------------------------------

    def register_face(self, name: str, image_bytes: bytes) -> dict:
        """
        Registra una nueva cara a partir de imagen en bytes (JPEG/PNG).
        Retorna dict con resultado.
        """
        import io
        from PIL import Image

        # Convertir bytes → array RGB que entiende face_recognition
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        rgb_array = np.array(image)

        # Detectar caras en la imagen
        face_locations = face_recognition.face_locations(rgb_array)

        if len(face_locations) == 0:
            return {"success": False, "reason": "No se detectó ninguna cara en la imagen."}

        if len(face_locations) > 1:
            return {"success": False, "reason": f"Se detectaron {len(face_locations)} caras. Sube una foto con una sola cara."}

        # Calcular encoding de la cara encontrada
        encoding = face_recognition.face_encodings(rgb_array, face_locations)[0]

        # Verificar si ya existe una cara muy similar (duplicado)
        if self.known_encodings:
            distances = face_recognition.face_distance(self.known_encodings, encoding)
            if np.min(distances) < TOLERANCE:
                existing = self.known_names[np.argmin(distances)]
                return {
                    "success": False,
                    "reason": f"Esta cara ya existe como '{existing}'.",
                }

        # Guardar foto original para referencia visual
        photo_path = FACES_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        image.save(photo_path)

        # Agregar a listas en memoria y guardar en disco
        self.known_encodings.append(encoding)
        self.known_names.append(name)
        self._save_encodings()

        logger.info(f"Cara registrada: {name}")
        return {"success": True, "name": name, "total_registered": len(self.known_names)}

    def remove_face(self, name: str) -> dict:
        """Elimina todas las instancias de una persona por nombre."""
        if name not in self.known_names:
            return {"success": False, "reason": f"'{name}' no encontrado."}

        # Filtrar listas
        paired = [
            (enc, n)
            for enc, n in zip(self.known_encodings, self.known_names)
            if n != name
        ]
        if paired:
            self.known_encodings, self.known_names = zip(*paired)
            self.known_encodings = list(self.known_encodings)
            self.known_names = list(self.known_names)
        else:
            self.known_encodings = []
            self.known_names = []

        self._save_encodings()
        logger.info(f"Cara eliminada: {name}")
        return {"success": True, "removed": name}

    def list_faces(self) -> list[str]:
        """Lista nombres de todas las personas registradas."""
        return list(set(self.known_names))

    # ------------------------------------------------------------------
    # Reconocimiento en tiempo real
    # ------------------------------------------------------------------

    def recognize(self, frame_rgb: np.ndarray) -> dict:
        """
        Recibe un frame RGB (numpy array) y retorna resultado del reconocimiento.

        Retorna dict:
            authorized: bool
            name: str | None
            confidence: float  (0.0 = idéntico, 1.0 = completamente diferente)
            face_detected: bool
        """
        if len(self.known_encodings) == 0:
            return {
                "authorized": False,
                "name": None,
                "confidence": None,
                "face_detected": False,
                "reason": "No hay caras registradas.",
            }

        # Reducir frame para detección rápida (escala 1/4), luego encodings en full
        # Esto acelera la detección en la Pi sin perder precisión en los encodings
        small_frame = frame_rgb[::2, ::2]  # 50% del tamaño

        face_locations_small = face_recognition.face_locations(small_frame)

        if not face_locations_small:
            return {
                "authorized": False,
                "name": None,
                "confidence": None,
                "face_detected": False,
            }

        # Escalar coordenadas de vuelta al tamaño original
        face_locations = [
            (top * 2, right * 2, bottom * 2, left * 2)
            for top, right, bottom, left in face_locations_small
        ]

        # Calcular encodings en el frame original (más preciso)
        encodings = face_recognition.face_encodings(frame_rgb, face_locations)

        results = []
        for encoding in encodings:
            distances = face_recognition.face_distance(self.known_encodings, encoding)
            best_idx = np.argmin(distances)
            best_distance = distances[best_idx]

            if best_distance <= TOLERANCE:
                results.append(
                    {
                        "authorized": True,
                        "name": self.known_names[best_idx],
                        "confidence": round(float(1 - best_distance), 3),
                        "face_detected": True,
                    }
                )
            else:
                results.append(
                    {
                        "authorized": False,
                        "name": "Desconocido",
                        "confidence": round(float(1 - best_distance), 3),
                        "face_detected": True,
                    }
                )

        # Si hay múltiples caras, retornar la autorizada si existe
        authorized = [r for r in results if r["authorized"]]
        if authorized:
            return authorized[0]
        return results[0]
