# app/lock_controller.py

import serial
import threading
import time
import logging

logger = logging.getLogger(__name__)

_RECONNECT_INTERVAL = 5  # segundos entre intentos de reconexión


class LockController:
    def __init__(self, port='/dev/ttyACM0', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.connected = False
        self.ser = None
        self.listen_active = True
        self.on_recognition_request = None

        self._lock = threading.Lock()

        self._try_connect()

        threading.Thread(target=self._reconnect_loop, daemon=True, name="serial-reconnect").start()

    # ------------------------------------------------------------------
    # Conexión / reconexión
    # ------------------------------------------------------------------

    def _try_connect(self) -> bool:
        """Intenta abrir el puerto serie. Devuelve True si tuvo éxito."""
        try:
            ser = serial.Serial(self.port, self.baudrate, timeout=1)
            with self._lock:
                self.ser = ser
                self.connected = True
            logger.info(f"Conectado al Arduino en {self.port}")
            threading.Thread(target=self._listen_serial, daemon=True, name="serial-listen").start()
            return True
        except serial.SerialException as e:
            logger.warning(f"Arduino no disponible en {self.port}: {e}")
            return False

    def _reconnect_loop(self):
        """Intenta reconectar cada _RECONNECT_INTERVAL segundos cuando no hay conexión."""
        while self.listen_active:
            time.sleep(_RECONNECT_INTERVAL)
            if not self.listen_active:
                break
            with self._lock:
                already_connected = self.connected
            if not already_connected:
                logger.info("Intentando reconectar con el Arduino…")
                self._try_connect()

    # ------------------------------------------------------------------
    # Escucha de mensajes entrantes
    # ------------------------------------------------------------------

    def _listen_serial(self):
        """Escucha eventos del Arduino. Sale y marca desconectado ante cualquier error de I/O."""
        while self.listen_active:
            with self._lock:
                ser = self.ser
                active = self.connected

            if not active or ser is None or not ser.is_open:
                break

            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        logger.debug(f"[ARDUINO] --> {line}")
                        if line == "REQ_RECOGNITION" and self.on_recognition_request:
                            logger.info("Botón externo presionado. Iniciando reconocimiento…")
                            threading.Thread(target=self.on_recognition_request, daemon=True).start()
                time.sleep(0.05)

            except Exception as e:
                logger.error(f"Error leyendo puerto serial: {e} — marcando desconectado.")
                self._mark_disconnected()
                break

    def _mark_disconnected(self):
        with self._lock:
            self.connected = False
            if self.ser:
                try:
                    self.ser.close()
                except Exception:
                    pass
                self.ser = None

    # ------------------------------------------------------------------
    # Comandos hacia el Arduino
    # ------------------------------------------------------------------

    def open_lock(self):
        with self._lock:
            ser, ok = self.ser, self.connected
        if ok and ser:
            try:
                ser.write(b"OPEN\n")
                return {"success": True, "action": "manual_open", "message": "Comando enviado"}
            except Exception as e:
                logger.error(f"Error enviando OPEN: {e}")
                self._mark_disconnected()
        return {"success": False, "reason": "Hardware no disponible"}

    def trigger_blink(self):
        with self._lock:
            ser, ok = self.ser, self.connected
        if ok and ser:
            try:
                ser.write(b"BLINK_RED\n")
            except Exception as e:
                logger.error(f"Error enviando BLINK_RED: {e}")
                self._mark_disconnected()

    def send_recognition_start(self):
        with self._lock:
            ser, ok = self.ser, self.connected
        if ok and ser:
            try:
                ser.write(b"REQ_RECOGNITION\n")
            except Exception as e:
                logger.error(f"Error enviando REQ_RECOGNITION: {e}")
                self._mark_disconnected()

    # ------------------------------------------------------------------
    # Estado / cierre
    # ------------------------------------------------------------------

    def get_status(self):
        return "conectado" if self.connected else "desconectado"

    def close_serial(self):
        self.listen_active = False
        self._mark_disconnected()
