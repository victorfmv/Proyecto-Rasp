# app/lock_controller.py

import serial
import threading
import time
import logging

logger = logging.getLogger(__name__)

class LockController:
    def __init__(self, port='/dev/ttyACM0', baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self.connected = False
        self.ser = None
        self.listen_active = False
        self.on_recognition_request = None  # Función callback externa (se asignará en main.py)
        
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.connected = True
            self.listen_active = True
            logger.info(f"Conectado al Arduino en {self.port}")
            
            self.listen_thread = threading.Thread(target=self._listen_serial, daemon=True)
            self.listen_thread.start()
            
        except serial.SerialException as e:
            logger.error(f"Error conectando al Arduino: ({e})")

    def _listen_serial(self):
        """Escucha eventos del Arduino."""
        while self.listen_active and self.connected and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"[ARDUINO] --> {line}")
                        
                        # NUEVO: Si el botón externo fue presionado, disparamos el flujo
                        if line == "REQ_RECOGNITION" and self.on_recognition_request:
                            logger.info("Botón externo presionado. Iniciando reconocimiento...")
                            # Ejecutamos el flujo en un hilo rápido dedicado para no bloquear el puerto serial
                            threading.Thread(target=self.on_recognition_request, daemon=True).start()
                            
            except Exception as e:
                logger.error(f"Error leyendo puerto serial: {e}")
            
            time.sleep(0.05)

    def open_lock(self):
        if self.connected and self.ser:
            try:
                self.ser.write(b"OPEN\n")
                return {"success": True, "action": "manual_open", "message": "Comando enviado"}
            except Exception as e:
                logger.error(f"Error enviando OPEN: {e}")
        return {"success": False, "reason": "Hardware no disponible"}

    def trigger_blink(self):
        """Envía la orden al Arduino para parpadear el LED rojo."""
        if self.connected and self.ser:
            try:
                self.ser.write(b"BLINK_RED\n")
            except Exception as e:
                logger.error(f"Error enviando BLINK_RED: {e}")

    def send_recognition_start(self):
        """Notifica al Arduino que se inicia un ciclo de reconocimiento facial."""
        if self.connected and self.ser:
            try:
                self.ser.write(b"REQ_RECOGNITION\n")
            except Exception as e:
                logger.error(f"Error enviando REQ_RECOGNITION: {e}")

    def get_status(self):
        return "conectado" if self.connected else "desconectado"

    def close_serial(self):
        self.listen_active = False
        if self.connected and self.ser and self.ser.is_open:
            self.ser.close()
            self.connected = False