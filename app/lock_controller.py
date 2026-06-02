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
            # Inicializa la conexión con el Arduino
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.connected = True
            self.listen_active = True
            logger.info(f"Conectado al Arduino en {self.port}")
            
            # Iniciar el hilo que escucha al Arduino y lo imprime en la terminal
            self.listen_thread = threading.Thread(target=self._listen_serial, daemon=True)
            self.listen_thread.start()
            
        except serial.SerialException as e:
            logger.error(f"Error conectando al Arduino: Verifica el cable o el puerto ({e})")

    def _listen_serial(self):
        """Escucha permanentemente lo que el Arduino envía y lo imprime en la terminal de la Pi."""
        while self.listen_active and self.connected and self.ser and self.ser.is_open:
            try:
                if self.ser.in_waiting > 0:
                    # Leer línea, decodificar y limpiar
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"\n[ARDUINO] --> {line}")
            except Exception as e:
                logger.error(f"Error leyendo puerto serial: {e}")
            
            time.sleep(0.05) # Evita sobrecargar el CPU de la Raspberry

    def open_lock(self):
        """Envía el comando de apertura al Arduino."""
        if self.connected and self.ser:
            try:
                self.ser.write(b"OPEN\n")
                return {"success": True, "action": "manual_open", "message": "Comando enviado"}
            except Exception as e:
                logger.error(f"Error enviando comando: {e}")
                return {"success": False, "action": "error", "reason": str(e)}
        return {"success": False, "action": "error", "reason": "Arduino desconectado"}

    def close_lock(self):
        """Simula el comando de cierre (el Arduino actual cierra automáticamente a los 5s)."""
        if self.connected:
            return {"success": True, "action": "manual_close", "message": "Cierre gestionado por Arduino"}
        return {"success": False, "action": "error", "reason": "Arduino desconectado"}

    def get_status(self):
        """Devuelve el estado de la conexión para el endpoint /status."""
        return "conectado" if self.connected else "desconectado"

    def close_serial(self):
        """Cierra la comunicación de forma limpia al apagar el servidor FastAPI."""
        self.listen_active = False
        if self.connected and self.ser and self.ser.is_open:
            self.ser.close()
            self.connected = False
            logger.info("Conexión serial con Arduino cerrada correctamente.")
