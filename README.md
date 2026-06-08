# Proyecto con Raspberry Pi 4 y arduino

Integración de una cerradura magnética controlada por el arduino y una cámara con reconocimiento facial gestionada por la Raspberry.

## Código del arduino
```cpp
// ------------------------------------------------------------------
// Smart Lock - Controlador de Hardware No Bloqueante (Definitivo)
// ------------------------------------------------------------------

// Definición de Pines
const uint8_t PIN_RELE = 7; 
const uint8_t LED_RED = 8;
const uint8_t LED_GREEN = 9;
const uint8_t BUTTON_INSIDE = 10;

// Variables de Control de Tiempo
unsigned long tiempoApertura = 0;
const unsigned long COOLDOWN_ABIERTO = 5000; // 5 segundos de apertura
bool lockAbierto = false;

// Variable para el control del botón físico
bool botonPresionadoAntes = false;

void setup() {
  // Inicializar comunicación serial a 9600 baudios (coincide con la Raspberry Pi)
  Serial.begin(9600);
  
  // Configuración de Pines
  pinMode(PIN_RELE, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  
  // INPUT_PULLUP activa la resistencia interna de 20k, el botón debe ir a GND
  pinMode(BUTTON_INSIDE, INPUT_PULLUP);
  
  // Estado inicial del sistema por defecto (Puerta Bloqueada)
  // Nota: Como tu relé se activa con LOW, HIGH significa "apagado / sin energía"
  digitalWrite(PIN_RELE, HIGH);
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_GREEN, LOW);
  
  // Enviar señal de sincronización inicial al backend en Python
  Serial.println("ARDUINO_LISTO");
}

// Función inline para abrir la cerradura
inline void open_lock() {
  digitalWrite(PIN_RELE, LOW);     // Activa el relé (deja pasar corriente a la cerradura)
  digitalWrite(LED_RED, LOW);      // Apaga LED rojo
  digitalWrite(LED_GREEN, HIGH);   // Enciende LED verde
  lockAbierto = true;
  tiempoApertura = millis();       // Guarda el tiempo exacto en que se abrió
}

// Función inline para cerrar la cerradura
inline void close_lock() {
  digitalWrite(PIN_RELE, HIGH);    // Desactiva el relé (bloquea la cerradura)
  digitalWrite(LED_RED, HIGH);     // Enciende LED rojo
  digitalWrite(LED_GREEN, LOW);    // Apaga LED verde
  lockAbierto = false;
}

void loop() {
  // 1. TEMPORIZADOR ASÍNCRONO (Maneja el cierre automático sin congelar el programa)
  if (lockAbierto && (millis() - tiempoApertura >= COOLDOWN_ABIERTO)) {
    close_lock();
    Serial.println("OK_CERRADO");
  }

  // 2. LECTURA SERIAL (Escucha peticiones de apertura de la Raspberry Pi)
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim(); // Limpia saltos de línea (\r\n) y espacios externos

    if (comando == "OPEN") {
      open_lock();
      Serial.println("OK_ABIERTO");   
      
    } else if (comando.length() > 0) {
      // Envío de errores en caso de recibir bytes basura o comandos no válidos
      Serial.print("ERROR_COMANDO_DESCONOCIDO:");
      Serial.println(comando);
    }
  }

  // 3. BOTÓN FÍSICO DE SALIDA (Control por flanco de bajada / Pulsación única)
  // Al usar INPUT_PULLUP, digitalRead devuelve LOW (false) cuando el botón se presiona
  bool botonActual = !digitalRead(BUTTON_INSIDE); 

  if (botonActual && !botonPresionadoAntes) {
    open_lock();
    botonPresionadoAntes = true;        // Bloquea repeticiones consecutivas en el bucle
    delay(50);                          // Pequeño antirrebote de hardware (debounce)
  } 
  else if (!botonActual) {
    botonPresionadoAntes = false;       // Libera el seguro cuando la persona suelta el botón
  }
}
```
## Script de pruebas con picamera2 (fotos)
```python
from picamera2 import Picamera2

# Inicializa la cámara usando la arquitectura libcamera
picam = Picamera2()

# Configura los parámetros básicos
picam.configure(picam.create_preview_configuration(main={"size": (1920, 1080)}))

# Inicia la captura
picam.start()
print("Capturando foto...")

# Toma la foto y la guarda en el disco
picam.capture_file("foto_libcamera.jpg")

# Cierra la cámara limpiamente
picam.stop()
print("¡Foto guardada con éxito como foto_libcamera.jpg!")
```
## Script de pruebas con picamera2 (videos)
```python
import time
from picamera2 import Picamera2

# Inicializa la cámara
picam = Picamera2()

# Configura la resolución del video (Full HD)
config = picam.create_video_configuration(main={"size": (1920, 1080)})
picam.configure(config)

# Inicia la cámara de fondo
picam.start()
print("Grabando video de 10 segundos con libcamera...")

# Graba directo indicando el archivo y la duración en segundos (10 segundos)
picam.start_and_record_video("video_libcamera.h264", duration=10)

# Cierra la cámara limpiamente al terminar
picam.stop()
print("¡Grabación finalizada! Archivo guardado como video_libcamera.h264")
```