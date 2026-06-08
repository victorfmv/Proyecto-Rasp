"""
main.py
Servidor principal — Smart Lock con reconocimiento facial.
Equipo: [sus nombres aquí]

Endpoints:
  GET  /              → estado del sistema
  GET  /status        → estado de cerradura + cámara + serial
  POST /unlock/manual → abrir manualmente desde la UI
  POST /lock          → cerrar manualmente
  POST /faces/register → registrar nueva cara (sube foto)
  POST /faces/register/camera → registrar cara usando la cámara en vivo
  DELETE /faces/{name} → eliminar cara registrada
  GET  /faces         → listar caras registradas
  POST /recognize     → reconocer una cara usando la cámara en vivo
  GET  /stream        → MJPEG stream de la cámara en vivo con overlay
  GET  /stream/preview → preview de 10 segundos con reconocimiento y overlay de color
  GET  /logs          → últimos registros de acceso
  GET  /logs/stats    → estadísticas
"""

import io
import time
import logging
import threading
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from app.face_engine import FaceEngine
from app.camera import Camera
from app.lock_controller import LockController
from app import database as db

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log"),
    ],
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Estado global del sistema
# ------------------------------------------------------------------
face_engine: FaceEngine = None
camera: Camera = None
lock: LockController = None

# Hilo de reconocimiento continuo
recognition_thread: threading.Thread = None
recognition_active = threading.Event()

# Última detección (shared entre hilo y endpoints)
last_recognition: dict = {
    "name": None,
    "authorized": False,
    "confidence": None,
    "face_detected": False,
    "timestamp": None,
}
_state_lock = threading.Lock()

# Lock para sincronizar acceso a face_recognition (dlib no es thread-safe)
# Previene corrupción de memoria al usar face_recognition simultáneamente
recognition_lock = threading.Lock()

# Control de streaming en vivo
streaming_stop = threading.Event()
stream_count = 0
stream_count_lock = threading.Lock()


def _increment_stream_count():
    global stream_count
    with stream_count_lock:
        stream_count += 1


def _decrement_stream_count():
    global stream_count
    with stream_count_lock:
        if stream_count > 0:
            stream_count -= 1


# ------------------------------------------------------------------
# Hilo de reconocimiento continuo
# ------------------------------------------------------------------

def recognition_loop():
    """
    Corre en background. Captura frames continuamente y evalúa si hay caras.
    Cuando detecta cara autorizada → abre la cerradura y registra en DB.
    """
    global last_recognition
    logger.info("Hilo de reconocimiento iniciado.")

    # Cooldown: no abrir la cerradura más de 1 vez cada N segundos
    COOLDOWN = 8.0
    last_open_time = 0.0

    while recognition_active.is_set():
        try:
            frame = camera.capture_rgb()
            
            # Sincronizar acceso a face_recognition (dlib) - no es thread-safe
            with recognition_lock:
                result = face_engine.recognize(frame)

            with _state_lock:
                last_recognition = {
                    **result,
                    "timestamp": time.strftime("%H:%M:%S"),
                }

            if result["authorized"] and result["face_detected"]:
                now = time.time()
                if now - last_open_time > COOLDOWN:
                    last_open_time = now
                    logger.info(f"Cara autorizada: {result['name']} (confianza {result['confidence']})")
                    lock_result = lock.open_lock()
                    db.log_access(
                        name=result["name"],
                        authorized=True,
                        confidence=result["confidence"],
                        action=lock_result.get("action"),
                    )

            elif result["face_detected"] and not result["authorized"]:
                db.log_access(
                    name=result.get("name", "Desconocido"),
                    authorized=False,
                    confidence=result.get("confidence"),
                    action="denied",
                )

        except Exception as e:
            logger.error(f"Error en hilo de reconocimiento: {e}")
            time.sleep(1)

        # ~10 FPS de evaluación (ajustable)
        time.sleep(0.1)

    logger.info("Hilo de reconocimiento detenido.")


# ------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global face_engine, camera, lock, recognition_thread

    logger.info("=== Iniciando Smart Lock ===")
    db.init_db()

    face_engine = FaceEngine()
    camera = Camera(width=640, height=480)
    lock = LockController()  # detecta puerto automáticamente

    # Arrancar hilo de reconocimiento continuo
    recognition_active.set()
    recognition_thread = threading.Thread(target=recognition_loop, daemon=True)
    recognition_thread.start()

    logger.info("Sistema listo.")
    yield

    # Shutdown
    logger.info("=== Apagando Smart Lock ===")
    recognition_active.clear()
    if recognition_thread:
        recognition_thread.join(timeout=3)
    lock.close_serial()
    camera.release()


# ------------------------------------------------------------------
# App FastAPI
# ------------------------------------------------------------------

app = FastAPI(
    title="Smart Lock — Reconocimiento Facial",
    description="API de cerradura inteligente con reconocimiento facial local.",
    version="1.0.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "project": "Smart Lock",
        "status": "online",
        "registered_faces": len(face_engine.list_faces()),
        "lock_connected": lock.connected,
    }


@app.get("/status")
def get_status():
    lock_status = lock.get_status()
    with _state_lock:
        recognition = dict(last_recognition)
    with stream_count_lock:
        active_streams = stream_count
    return {
        "lock": lock_status,
        "camera": {
            "active": True,
            "streaming": active_streams > 0,
            "streams_active": active_streams,
        },
        "last_recognition": recognition,
        "registered_faces": face_engine.list_faces(),
    }


@app.get("/faces")
def list_faces():
    return {"faces": face_engine.list_faces()}


@app.post("/faces/register")
async def register_face(name: str, file: UploadFile = File(...)):
    """
    Registra una nueva cara. Sube una foto con el parámetro ?name=NombrePersona
    """
    if not name or len(name.strip()) < 2:
        raise HTTPException(400, "El nombre debe tener al menos 2 caracteres.")

    image_bytes = await file.read()
    
    # Sincronizar acceso a face_recognition (dlib) - no es thread-safe
    with recognition_lock:
        result = face_engine.register_face(name.strip(), image_bytes)

    if not result["success"]:
        raise HTTPException(400, result["reason"])

    return result


@app.post("/faces/register/camera")
def register_face_camera(name: str):
    """
    Registra una nueva cara usando una captura desde la cámara en vivo.
    """
    if not name or len(name.strip()) < 2:
        raise HTTPException(400, "El nombre debe tener al menos 2 caracteres.")

    try:
        frame_rgb = camera.capture_rgb()
    except Exception as e:
        logger.error(f"Error capturando imagen para registro: {e}")
        raise HTTPException(500, "No se pudo capturar la imagen desde la cámara.")

    import cv2
    _, buffer = cv2.imencode('.jpg', cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    image_bytes = buffer.tobytes()

    with recognition_lock:
        result = face_engine.register_face(name.strip(), image_bytes)

    if not result["success"]:
        raise HTTPException(400, result["reason"])

    return result


@app.delete("/faces/{name}")
def delete_face(name: str):
    result = face_engine.remove_face(name)
    if not result["success"]:
        raise HTTPException(404, result["reason"])
    return result


@app.post("/recognize")
def recognize_photo():
    """
    Reconoce una cara usando la cámara en vivo durante un máximo de 5 segundos.
    """
    timeout = 5.0
    deadline = time.time() + timeout
    last_result = None

    while time.time() < deadline:
        try:
            frame = camera.capture_rgb()
        except Exception as e:
            logger.error(f"Error capturando imagen para reconocimiento: {e}")
            raise HTTPException(500, "No se pudo capturar la imagen desde la cámara.")

        with recognition_lock:
            result = face_engine.recognize(frame)

        last_result = result
        if result["face_detected"]:
            return result

        time.sleep(0.1)

    return last_result or {
        "authorized": False,
        "name": None,
        "confidence": None,
        "face_detected": False,
        "reason": "No se detectó ninguna cara durante el tiempo de espera.",
    }


@app.post("/unlock/manual")
def manual_unlock():
    """Abre la cerradura manualmente desde la UI. El cierre es automático a los 5s."""
    result = lock.open_lock()
    if result["success"]:
        db.log_access(name="Manual (UI)", authorized=True, confidence=None, action="manual_open")
    return result


@app.get("/logs")
def get_logs(limit: int = 50):
    return {"logs": db.get_recent_logs(limit)}


@app.get("/logs/stats")
def get_stats():
    return db.get_stats()


@app.get("/stream")
def video_stream():
    """
    MJPEG stream de la cámara en tiempo real.
    Abrir en browser: http://IP_RASP:8000/stream
    """
    streaming_stop.clear()
    _increment_stream_count()

    def generate():
        import cv2
        try:
            while not streaming_stop.is_set():
                try:
                    frame_rgb = camera.capture_rgb()
                    with _state_lock:
                        recog = dict(last_recognition)

                    # Overlay con resultado del reconocimiento
                    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

                    if recog["face_detected"]:
                        color = (0, 255, 0) if recog["authorized"] else (0, 0, 255)
                        label = recog["name"] or "Desconocido"
                        conf_str = f" ({recog['confidence']:.0%})" if recog["confidence"] else ""
                        cv2.putText(
                            frame_bgr, f"{label}{conf_str}",
                            (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2
                        )

                    _, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    frame_bytes = buffer.tobytes()

                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                        + frame_bytes
                        + b"\r\n"
                    )
                    time.sleep(0.05)  # ~20 FPS para el stream

                except Exception as e:
                    logger.error(f"Error en stream: {e}")
                    time.sleep(0.5)
        except GeneratorExit:
            pass
        finally:
            _decrement_stream_count()
            logger.info("Stream cerrado")

    return StreamingResponse(
        generate(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


@app.post("/stream/stop")
def stop_stream():
    """Detiene la transmisión en vivo de la cámara (solo afecta a /stream)."""
    streaming_stop.set()
    return {"success": True, "message": "Las nuevas conexiones se cerrarán progresivamente."}


@app.get("/stream/preview")
def preview_stream(duration: int = 10):
    """Activa la cámara y transmite por 10 segundos con reconocimiento de rostro.
    Accesible en: http://localhost:8000/stream/preview
    """
    if duration <= 0 or duration > 30:
        raise HTTPException(400, "La duración debe estar entre 1 y 30 segundos.")

    def generate():
        import cv2
        deadline = time.time() + duration
        frame_count = 0
        try:
            while time.time() < deadline:
                try:
                    frame_rgb = camera.capture_rgb()
                    with recognition_lock:
                        result = face_engine.recognize(frame_rgb)

                    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                    
                    # Determinar color y etiqueta según resultado
                    if result["face_detected"] and result["authorized"]:
                        color = (0, 255, 0)  # Verde: reconocido
                        label = result["name"] or "Reconocido"
                        conf_str = f" ({result['confidence']:.0%})" if result["confidence"] else ""
                    elif result["face_detected"]:
                        color = (0, 0, 255)  # Rojo: desconocido
                        label = "Desconocido"
                        conf_str = f" ({result['confidence']:.0%})" if result["confidence"] else ""
                    else:
                        color = (0, 0, 255)  # Rojo: sin cara
                        label = "Sin cara"
                        conf_str = ""

                    # Dibujar texto en frame
                    cv2.putText(
                        frame_bgr,
                        f"{label}{conf_str}",
                        (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1.2,
                        color,
                        2,
                    )

                    # Codificar a JPEG
                    _, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    frame_bytes = buffer.tobytes()

                    # Enviar frame en formato MJPEG
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(frame_bytes)).encode() + b"\r\n"
                        b"\r\n" + frame_bytes + b"\r\n"
                    )
                    frame_count += 1
                    time.sleep(0.033)  # ~30 FPS

                except Exception as e:
                    logger.error(f"Error capturando frame en preview: {e}")
                    time.sleep(0.1)
        finally:
            logger.info(f"Preview stream finalizado: {frame_count} frames enviados")

    return StreamingResponse(
        generate(), media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
