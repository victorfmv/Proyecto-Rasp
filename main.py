# main.py
"""
Smart Lock — Servidor Principal
Arquitectura basada en eventos pasivos; sin polling de CPU en reposo.

Endpoints:
  GET  /                      → estado del sistema
  GET  /status                → estado de cerradura + cámara + serial
  GET  /recognize             → interfaz web: stream en vivo + resultado JSON
  POST /unlock/manual         → abrir manualmente desde la UI
  POST /faces/register        → registrar nueva cara (sube foto)
  POST /faces/register/camera → registrar cara usando la cámara en vivo
  DELETE /faces/{name}        → eliminar cara registrada
  GET  /faces                 → listar caras registradas
  GET  /stream                → MJPEG stream de la cámara en vivo
  POST /stream/stop           → detener el stream activo
  GET  /stream/preview        → preview de N segundos con reconocimiento y overlay
  GET  /logs                  → últimos registros de acceso
  GET  /logs/stats            → estadísticas
"""

import time
import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import cv2
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse

from app.face_engine import FaceEngine
from app.camera import Camera
from app.lock_controller import LockController
from app import database as db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/app.log"),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Estado de la Aplicación
# ---------------------------------------------------------------------------
@dataclass
class AppState:
    """Agrupa todos los recursos compartidos del sistema."""

    face_engine: FaceEngine
    camera: Camera
    lock: LockController

    # Mutex para dlib (no es thread-safe)
    recognition_lock: threading.Lock = field(default_factory=threading.Lock)

    # Se activa en el lifespan shutdown para que generadores de stream terminen
    shutdown_event: threading.Event = field(default_factory=threading.Event)

    # Se activa con POST /stream/stop; se limpia cuando /stream recibe conexión nueva
    streaming_stop: threading.Event = field(default_factory=threading.Event)

    # Último resultado de reconocimiento (leído por GET /recognize/result)
    _recog_ready: bool = field(default=False)
    _recog_result: dict = field(default_factory=dict)
    _recog_result_lock: threading.Lock = field(default_factory=threading.Lock)

    # Contador de streams activos (para /status)
    _stream_count: int = field(default=0, init=False)
    _stream_count_lock: threading.Lock = field(default_factory=threading.Lock)

    # ------------------------------------------------------------------ #
    # Resultado del reconocimiento                                          #
    # ------------------------------------------------------------------ #

    def recog_begin(self) -> None:
        """Marca el inicio de un ciclo de reconocimiento (limpia resultado anterior)."""
        with self._recog_result_lock:
            self._recog_ready = False
            self._recog_result = {}

    def recog_end(self, result: dict) -> None:
        """Almacena el resultado final y lo marca como disponible."""
        with self._recog_result_lock:
            self._recog_result = result
            self._recog_ready = True

    def recog_get(self) -> dict:
        """Retorna {"ready": false} o {"ready": true, ...resultado...}."""
        with self._recog_result_lock:
            if self._recog_ready:
                return {"ready": True, **self._recog_result}
            return {"ready": False}

    # ------------------------------------------------------------------ #
    # Contador de streams                                                   #
    # ------------------------------------------------------------------ #

    def increment_streams(self) -> None:
        with self._stream_count_lock:
            self._stream_count += 1

    def decrement_streams(self) -> None:
        with self._stream_count_lock:
            if self._stream_count > 0:
                self._stream_count -= 1

    @property
    def active_streams(self) -> int:
        with self._stream_count_lock:
            return self._stream_count

    # ------------------------------------------------------------------ #
    # Helpers de cámara                                                    #
    # ------------------------------------------------------------------ #

    def warmup_camera(self, frames: int = 5) -> None:
        """Drena frames residuales del buffer para estabilizar AEC/AGC."""
        try:
            for _ in range(frames):
                self.camera.capture_rgb()
                time.sleep(0.05)
        except Exception as exc:
            logger.warning(f"[WARMUP] Error: {exc}")


# ---------------------------------------------------------------------------
# Hilos de soporte
# ---------------------------------------------------------------------------

def _camera_keepalive_loop(ctx: AppState) -> None:
    """
    Captura un frame cada 3 segundos para mantener AEC/AGC estabilizado.
    Consumo de CPU mínimo: solo lectura del buffer, sin reconocimiento facial.
    """
    while not ctx.shutdown_event.wait(timeout=3.0):
        try:
            ctx.camera.capture_rgb()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Ciclo de vida
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Iniciando Smart Lock ===")

    db.init_db()

    face_engine = FaceEngine()
    camera = Camera(width=640, height=480)
    lock = LockController()

    ctx = AppState(face_engine=face_engine, camera=camera, lock=lock)

    threading.Thread(
        target=_camera_keepalive_loop,
        args=(ctx,),
        daemon=True,
        name="camera-keepalive",
    ).start()

    app.state.ctx = ctx
    logger.info("Sistema listo y en espera de eventos.")

    yield

    logger.info("=== Apagando Smart Lock ===")
    ctx.shutdown_event.set()
    lock.close_serial()
    camera.release()


# ---------------------------------------------------------------------------
# Aplicación
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Smart Lock — Reconocimiento Facial",
    description="API de cerradura inteligente con reconocimiento facial local.",
    version="2.5.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ctx(request: Request) -> AppState:
    return request.app.state.ctx


# ---------------------------------------------------------------------------
# Endpoints — Información general
# ---------------------------------------------------------------------------

@app.get("/")
def root(request: Request):
    ctx = _get_ctx(request)
    return {
        "project": "Smart Lock",
        "status": "ready",
        "registered_faces": len(ctx.face_engine.list_faces()),
        "lock_connected": ctx.lock.connected,
    }


@app.get("/status")
def get_status(request: Request):
    ctx = _get_ctx(request)
    return {
        "lock": ctx.lock.get_status(),
        "camera": {
            "active": True,
            "streams_active": ctx.active_streams,
        },
        "registered_faces": ctx.face_engine.list_faces(),
    }


# ---------------------------------------------------------------------------
# Endpoints — Reconocimiento (interfaz web + sub-recursos ocultos)
# ---------------------------------------------------------------------------

_RECOGNIZE_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Smart Lock — Reconocimiento</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;
         display:flex;flex-direction:column;align-items:center;padding:32px 16px}
    h1{font-size:1.3rem;font-weight:600;margin-bottom:16px;color:#58a6ff}
    img{width:640px;max-width:100%;border:2px solid #30363d;border-radius:6px;display:block}
    #status{margin-top:10px;font-size:14px;color:#8b949e}
    pre{margin-top:12px;background:#161b22;border:1px solid #30363d;border-radius:6px;
        padding:16px;font-size:13px;min-height:56px;width:640px;max-width:100%;white-space:pre-wrap}
    .ok{color:#3fb950}.deny{color:#f85149}
  </style>
</head>
<body>
  <h1>Smart Lock — Reconocimiento Facial</h1>
  <img src="/recognize/stream" alt="Cámara en vivo" id="cam">
  <p id="status">Reconociendo&hellip;</p>
  <pre id="json">—</pre>
  <script>
    const poll = setInterval(async () => {
      try {
        const r = await fetch('/recognize/result');
        const d = await r.json();
        if (!d.ready) return;
        clearInterval(poll);
        const { ready, ...result } = d;
        document.getElementById('json').textContent = JSON.stringify(result, null, 2);
        if (result.authorized) {
          document.getElementById('json').className = 'ok';
          document.getElementById('status').textContent = '✓ Acceso concedido: ' + result.name;
        } else {
          document.getElementById('json').className = 'deny';
          document.getElementById('status').textContent = result.face_detected
            ? '✗ Acceso denegado'
            : '— Tiempo agotado sin cara detectada';
        }
      } catch(e) {}
    }, 500);
  </script>
</body>
</html>"""


@app.get(
    "/recognize",
    response_class=HTMLResponse,
    summary="Reconocimiento facial (interfaz web + stream)",
    description=(
        "Abre la interfaz en el navegador: muestra el stream en vivo con overlays "
        "de reconocimiento y el resultado JSON al finalizar. "
        "Envía REQ_RECOGNITION al Arduino al iniciar."
    ),
)
def recognize_page():
    return HTMLResponse(_RECOGNIZE_HTML)


@app.get("/recognize/stream", include_in_schema=False)
def recognize_stream(request: Request, timeout: int = 10):
    """Stream MJPEG de reconocimiento. Usado internamente por la página /recognize."""
    ctx = _get_ctx(request)

    if not 1 <= timeout <= 30:
        raise HTTPException(400, "El timeout debe estar entre 1 y 30 segundos.")

    def generate():
        ctx.recog_begin()
        ctx.lock.send_recognition_start()

        final_result: dict = {
            "authorized": False,
            "name": None,
            "confidence": None,
            "face_detected": False,
            "reason": "No se detectó ningún rostro en el tiempo límite.",
        }

        try:
            deadline = time.time() + timeout
            denied_logged = False
            logger.info(f"[RECOGNIZE] Stream iniciado ({timeout}s).")

            while time.time() < deadline and not ctx.shutdown_event.is_set():
                try:
                    frame_rgb = ctx.camera.capture_rgb()

                    with ctx.recognition_lock:
                        result = ctx.face_engine.recognize(frame_rgb)

                    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                    conf_str = (
                        f" ({result['confidence']:.0%})" if result.get("confidence") else ""
                    )

                    if result["face_detected"] and result["authorized"]:
                        lock_result = ctx.lock.open_lock()
                        db.log_access(
                            name=result["name"],
                            authorized=True,
                            confidence=result["confidence"],
                            action=lock_result.get("action", "face_open"),
                        )
                        logger.info(f"[RECOGNIZE] Acceso concedido: {result['name']}")
                        final_result = result

                        label = f"ACCESO CONCEDIDO: {result['name']}{conf_str}"
                        cv2.putText(
                            frame_bgr, label, (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2,
                        )
                        _, buf = cv2.imencode(
                            ".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85]
                        )
                        success_frame = (
                            b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                            + buf.tobytes() + b"\r\n"
                        )
                        end_display = time.time() + 1.5
                        while time.time() < end_display:
                            yield success_frame
                            time.sleep(0.1)
                        return

                    elif result["face_detected"] and not result["authorized"]:
                        if not denied_logged:
                            db.log_access(
                                name="Desconocido",
                                authorized=False,
                                confidence=result.get("confidence"),
                                action="denied",
                            )
                            logger.warning("[RECOGNIZE] Acceso denegado.")
                            denied_logged = True
                        final_result = result
                        cv2.putText(
                            frame_bgr, f"ACCESO DENEGADO{conf_str}", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2,
                        )

                    else:
                        denied_logged = False
                        cv2.putText(
                            frame_bgr, "Buscando rostro...", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 165, 255), 2,
                        )

                    _, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    yield (
                        b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                        + buf.tobytes() + b"\r\n"
                    )
                    time.sleep(0.04)

                except Exception as exc:
                    logger.error(f"[RECOGNIZE] Error en frame: {exc}")
                    time.sleep(0.1)

            logger.info("[RECOGNIZE] Stream finalizado.")

        finally:
            ctx.recog_end(final_result)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/recognize/result", include_in_schema=False)
def recognize_result(request: Request):
    """Retorna el último resultado de reconocimiento. Usado internamente por /recognize."""
    ctx = _get_ctx(request)
    return ctx.recog_get()


# ---------------------------------------------------------------------------
# Endpoints — Control de chapa
# ---------------------------------------------------------------------------

@app.post("/unlock/manual")
def manual_unlock(request: Request):
    ctx = _get_ctx(request)
    result = ctx.lock.open_lock()
    if result["success"]:
        db.log_access(
            name="Manual (UI)",
            authorized=True,
            confidence=None,
            action="manual_open",
        )
    return result


# ---------------------------------------------------------------------------
# Endpoints — Gestión de caras
# ---------------------------------------------------------------------------

@app.get("/faces")
def list_faces(request: Request):
    ctx = _get_ctx(request)
    return {"faces": ctx.face_engine.list_faces()}


@app.post("/faces/register")
async def register_face(request: Request, name: str, file: UploadFile = File(...)):
    ctx = _get_ctx(request)

    if not name or len(name.strip()) < 2:
        raise HTTPException(400, "El nombre debe tener al menos 2 caracteres.")

    image_bytes = await file.read()

    with ctx.recognition_lock:
        result = ctx.face_engine.register_face(name.strip(), image_bytes)

    if not result["success"]:
        raise HTTPException(400, result["reason"])
    return result


@app.post("/faces/register/camera")
def register_face_from_camera(request: Request, name: str):
    """Registra una cara capturando directamente desde la Pi Camera."""
    ctx = _get_ctx(request)

    if not name or len(name.strip()) < 2:
        raise HTTPException(400, "El nombre debe tener al menos 2 caracteres.")

    try:
        ctx.warmup_camera(frames=10)
        frame_rgb = ctx.camera.capture_rgb()
    except Exception as exc:
        logger.error(f"Error en captura de registro: {exc}")
        raise HTTPException(500, "No se pudo capturar una imagen estable de la cámara.")

    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    _, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
    image_bytes = buffer.tobytes()

    with ctx.recognition_lock:
        result = ctx.face_engine.register_face(name.strip(), image_bytes)

    if not result["success"]:
        raise HTTPException(400, result["reason"])
    return result


@app.delete("/faces/{name}")
def delete_face(request: Request, name: str):
    ctx = _get_ctx(request)
    result = ctx.face_engine.remove_face(name)
    if not result["success"]:
        raise HTTPException(404, result["reason"])
    return result


# ---------------------------------------------------------------------------
# Endpoints — Logs
# ---------------------------------------------------------------------------

@app.get("/logs")
def get_logs(request: Request, limit: int = 50):
    return {"logs": db.get_recent_logs(limit)}


@app.get("/logs/stats")
def get_stats():
    return db.get_stats()


# ---------------------------------------------------------------------------
# Endpoints — Streaming simple (sin reconocimiento)
# ---------------------------------------------------------------------------

@app.get("/stream")
def video_stream(request: Request):
    """MJPEG stream simple sin anotaciones. Detener con POST /stream/stop."""
    ctx = _get_ctx(request)
    ctx.streaming_stop.clear()

    def generate():
        ctx.increment_streams()
        try:
            while not ctx.streaming_stop.is_set() and not ctx.shutdown_event.is_set():
                try:
                    frame_rgb = ctx.camera.capture_rgb()
                    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                    _, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + buf.tobytes() + b"\r\n"
                    )
                    time.sleep(0.05)
                except Exception as exc:
                    logger.error(f"Error en stream: {exc}")
                    time.sleep(0.5)
        except GeneratorExit:
            pass
        finally:
            ctx.decrement_streams()
            logger.info("Stream cerrado.")

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/stream/stop")
def stop_stream(request: Request):
    """Detiene el stream MJPEG activo."""
    ctx = _get_ctx(request)
    ctx.streaming_stop.set()
    return {"success": True, "message": "Stream detenido."}


@app.get("/stream/preview")
def preview_stream(request: Request, duration: int = 10):
    """
    Stream MJPEG con reconocimiento facial superpuesto.
    NO abre la chapa. Duración máxima: 30 segundos.
    """
    ctx = _get_ctx(request)

    if not 1 <= duration <= 30:
        raise HTTPException(400, "La duración debe estar entre 1 y 30 segundos.")

    def generate():
        deadline = time.time() + duration
        logger.info(f"[PREVIEW] Iniciando stream de {duration}s.")

        while time.time() < deadline and not ctx.shutdown_event.is_set():
            try:
                frame_rgb = ctx.camera.capture_rgb()

                with ctx.recognition_lock:
                    result = ctx.face_engine.recognize(frame_rgb)

                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

                if result["face_detected"]:
                    color = (0, 255, 0) if result["authorized"] else (0, 0, 255)
                    conf = f" ({result['confidence']:.0%})" if result["confidence"] else ""
                    label = (result["name"] if result["authorized"] else "Desconocido") + conf
                else:
                    color = (0, 0, 255)
                    label = "Buscando rostro..."

                cv2.putText(
                    frame_bgr, label,
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2,
                )

                _, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(buf)).encode() + b"\r\n"
                    b"\r\n" + buf.tobytes() + b"\r\n"
                )
                time.sleep(0.04)

            except Exception as exc:
                logger.error(f"Error en preview: {exc}")
                time.sleep(0.1)

        logger.info("[PREVIEW] Stream finalizado.")

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)