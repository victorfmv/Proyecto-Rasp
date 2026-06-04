"""
app/lock_controller.py
Módulo de control de cerradura.
Gestiona comunicación serial con Arduino para abrir/cerrar cerradura magnética.
"""

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
        """Escucha permanentemente lo que el Arduino envía (cierres automáticos o logs)."""
        while self.listen_active and self.connected and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"\n[ARDUINO] --> {line}")
                        # Aquí puedes agregar lógica si quieres reaccionar a "OK_CERRADO" en la Pi
            except Exception as e:
                logger.error(f"Error leyendo puerto serial: {e}")
            
            time.sleep(0.05)

    def open_lock(self):
        """Envía el comando de apertura al Arduino."""
        if self.connected and self.ser:
            try:
                self.ser.write(b"OPEN\n")
                return {"success": True, "action": "manual_open", "message": "Comando de apertura enviado"}
            except Exception as e:
                logger.error(f"Error enviando comando: {e}")
                return {"success": False, "action": "error", "reason": str(e)}
        return {"success": False, "action": "error", "reason": "Arduino desconectado"}

    def get_status(self):
        return "conectado" if self.connected else "desconectado"

    def close_serial(self):
        self.listen_active = False
        if self.connected and self.ser and self.ser.is_open:
            self.ser.close()
            self.connected = False
            logger.info("Conexión serial con Arduino cerrada correctamente.")
