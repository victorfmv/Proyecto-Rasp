"""
app/lock_controller.py
Comunicación serial con el ATmega328P.
Implementa el protocolo propio: [0xAA][CMD][CHECKSUM]

Protocolo definido:
  Header:    0xAA  (fijo, indica inicio de trama)
  Comandos:  0x01 = OPEN  (activa electroimán → abre chapa)
             0x02 = CLOSE (desactiva electroimán → cierra chapa)
             0x03 = STATUS (pide estado actual)
  Checksum:  XOR entre CMD y 0xFF  →  checksum = cmd ^ 0xFF

Respuestas del ATmega (1 byte):
  0x01 = ACK_OPEN
  0x02 = ACK_CLOSE
  0x03 = ACK_STATUS_OPEN
  0x04 = ACK_STATUS_CLOSED
  0xFF = ERROR
"""

import time
import logging
import threading
import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)

# Comandos (los mismos que vas a definir en el C del ATmega)
CMD_OPEN   = 0x01
CMD_CLOSE  = 0x02
CMD_STATUS = 0x03

# Respuestas esperadas del micro
ACK_OPEN          = 0x01
ACK_CLOSE         = 0x02
ACK_STATUS_OPEN   = 0x03
ACK_STATUS_CLOSED = 0x04
ACK_ERROR         = 0xFF

BAUD_RATE = 9600
TIMEOUT   = 2.0  # segundos esperando respuesta del micro
AUTO_CLOSE_DELAY = 5.0  # segundos antes de cerrar automáticamente


def _checksum(cmd: int) -> int:
    """Checksum simple: XOR del comando con 0xFF."""
    return cmd ^ 0xFF


class LockController:
    """
    Controla la chapa electromagnética a través del ATmega vía UART.
    Tiene reconexión automática si se desconecta el cable serial.
    """

    def __init__(self, port: str = None, auto_close: bool = True):
        self.port = port or self._detect_port()
        self.auto_close = auto_close
        self._serial: serial.Serial | None = None
        self._lock_open = False
        self._serial_lock = threading.Lock()  # thread-safe
        self._auto_close_timer: threading.Timer | None = None
        self._connect()

    # ------------------------------------------------------------------
    # Conexión y reconexión
    # ------------------------------------------------------------------

    def _detect_port(self) -> str:
        """
        Detecta automáticamente el puerto serial del ATmega.
        En Raspberry Pi suele ser /dev/ttyUSB0 o /dev/ttyACM0.
        """
        common_ports = ["/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyS0"]
        for port in common_ports:
            try:
                s = serial.Serial(port, BAUD_RATE, timeout=0.5)
                s.close()
                logger.info(f"Puerto serial detectado: {port}")
                return port
            except serial.SerialException:
                continue

        # Listar puertos disponibles para debug
        available = [p.device for p in serial.tools.list_ports.comports()]
        logger.warning(f"No se detectó ATmega. Puertos disponibles: {available}")
        return "/dev/ttyUSB0"  # default

    def _connect(self):
        """Abre conexión serial. Llamado en init y en reconexión."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=BAUD_RATE,
                timeout=TIMEOUT,
                write_timeout=TIMEOUT,
            )
            # El ATmega necesita ~2s para reiniciar tras abrir el puerto
            time.sleep(2)
            logger.info(f"Conectado al ATmega en {self.port} @ {BAUD_RATE} baud")
        except serial.SerialException as e:
            logger.error(f"No se pudo conectar al ATmega: {e}")
            self._serial = None

    def _reconnect(self):
        """Intenta reconectar si se perdió la conexión serial."""
        logger.warning("Intentando reconectar al ATmega...")
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
        time.sleep(1)
        self._connect()

    @property
    def connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    # ------------------------------------------------------------------
    # Envío de comandos
    # ------------------------------------------------------------------

    def _send_command(self, cmd: int) -> int | None:
        """
        Envía una trama [0xAA][CMD][CHECKSUM] y espera respuesta de 1 byte.
        Retorna el byte de respuesta o None si falló.
        """
        if not self.connected:
            self._reconnect()
            if not self.connected:
                logger.error("Sin conexión serial. Comando descartado.")
                return None

        frame = bytes([0xAA, cmd, _checksum(cmd)])

        with self._serial_lock:
            try:
                self._serial.reset_input_buffer()
                self._serial.write(frame)
                response = self._serial.read(1)

                if not response:
                    logger.warning("Sin respuesta del ATmega (timeout).")
                    return None

                return response[0]

            except serial.SerialException as e:
                logger.error(f"Error serial: {e}")
                self._serial = None  # marca como desconectado
                return None

    # ------------------------------------------------------------------
    # Comandos públicos
    # ------------------------------------------------------------------

    def open_lock(self) -> dict:
        """
        Abre la chapa electromagnética.
        Si auto_close está activo, la cierra después de AUTO_CLOSE_DELAY segundos.
        """
        response = self._send_command(CMD_OPEN)

        if response == ACK_OPEN:
            self._lock_open = True
            logger.info("Cerradura ABIERTA.")

            if self.auto_close:
                self._schedule_auto_close()

            return {"success": True, "action": "open", "auto_close_in": AUTO_CLOSE_DELAY}

        elif response == ACK_ERROR:
            return {"success": False, "reason": "ATmega reportó error."}
        else:
            return {"success": False, "reason": f"Respuesta inesperada: {response}"}

    def close_lock(self) -> dict:
        """Cierra la chapa electromagnética."""
        if self._auto_close_timer:
            self._auto_close_timer.cancel()

        response = self._send_command(CMD_CLOSE)

        if response == ACK_CLOSE:
            self._lock_open = False
            logger.info("Cerradura CERRADA.")
            return {"success": True, "action": "close"}
        else:
            return {"success": False, "reason": f"Respuesta inesperada: {response}"}

    def get_status(self) -> dict:
        """Pide el estado actual al ATmega."""
        response = self._send_command(CMD_STATUS)

        if response == ACK_STATUS_OPEN:
            return {"connected": True, "lock_open": True}
        elif response == ACK_STATUS_CLOSED:
            return {"connected": True, "lock_open": False}
        elif response is None:
            return {"connected": False, "lock_open": False}
        else:
            return {"connected": True, "lock_open": self._lock_open}

    def _schedule_auto_close(self):
        """Programa cierre automático después de AUTO_CLOSE_DELAY segundos."""
        if self._auto_close_timer:
            self._auto_close_timer.cancel()

        self._auto_close_timer = threading.Timer(AUTO_CLOSE_DELAY, self._auto_close)
        self._auto_close_timer.daemon = True
        self._auto_close_timer.start()

    def _auto_close(self):
        logger.info(f"Auto-cierre tras {AUTO_CLOSE_DELAY}s.")
        self.close_lock()

    def close_serial(self):
        """Cierra el puerto serial limpiamente."""
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Puerto serial cerrado.")
