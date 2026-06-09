# Proyecto con Raspberry Pi 4 y arduino

Integración de una cerradura magnética controlada por el arduino y una cámara con reconocimiento facial gestionada por la Raspberry.

## Código del arduino
```cpp
// ------------------------------------------------------------------
// Smart Lock - Controlador de Hardware por Eventos (Sin Bloqueo)
// ------------------------------------------------------------------

// Definición de Pines
const uint8_t PIN_RELE = 7; 
const uint8_t LED_RED = 8;
const uint8_t LED_GREEN = 9;
const uint8_t BUTTON_INSIDE = 10;  // Botón para salir (abre directo)
const uint8_t BUTTON_OUTSIDE = 11; // NUEVO: Botón para pedir reconocimiento (activa cámara)

// Variables de Control de Tiempo
unsigned long tiempoApertura = 0;
const unsigned long COOLDOWN_ABIERTO = 5000; // 5 segundos de apertura
bool lockAbierto = false;

// Banderas para control de pulsaciones únicas (Debounce)
bool insidePresionadoAntes = false;
bool outsidePresionadoAntes = false;

void setup() {
  Serial.begin(9600);
  
  pinMode(PIN_RELE, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  
  // Ambos botones usan la resistencia pull-up interna del Arduino
  pinMode(BUTTON_INSIDE, INPUT_PULLUP);
  pinMode(BUTTON_OUTSIDE, INPUT_PULLUP);
  
  // Estado inicial: Seguro puesto
  digitalWrite(PIN_RELE, HIGH);
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_GREEN, LOW);
  
  Serial.println("ARDUINO_LISTO");
}

inline void open_lock() {
  digitalWrite(PIN_RELE, LOW);
  digitalWrite(LED_RED, LOW);
  digitalWrite(LED_GREEN, HIGH);
  lockAbierto = true;
  tiempoApertura = millis();
}

inline void close_lock() {
  digitalWrite(PIN_RELE, HIGH);
  digitalWrite(LED_RED, HIGH);
  digitalWrite(LED_GREEN, LOW);
  lockAbierto = false;
}

// NUEVO: Función no bloqueante para parpadear el LED rojo 2 veces
void blink_red_indicator() {
  for(int i = 0; i < 2; i++) {
    digitalWrite(LED_RED, LOW);
    delay(150);
    digitalWrite(LED_RED, HIGH);
    delay(150);
  }
}

void loop() {
  // 1. Temporizador asíncrono para el cierre automático
  if (lockAbierto && (millis() - tiempoApertura >= COOLDOWN_ABIERTO)) {
    close_lock();
    Serial.println("OK_CERRADO");
  }

  // 2. Lectura Serial (Comandos desde la Raspberry Pi)
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim(); 

    if (comando == "OPEN") {
      open_lock();
      Serial.println("OK_ABIERTO");   
    } else if (comando == "BLINK_RED") {
      blink_red_indicator(); // La Pi nos pide avisar que la cámara está encendida
    } else if (comando.length() > 0) {
      Serial.print("ERROR_COMANDO_DESCONOCIDO:");
      Serial.println(comando);
    }
  }

  // 3. Botón Interno (Flanco de bajada - Salida Directa Inmediata)
  bool botonInsideActual = !digitalRead(BUTTON_INSIDE);
  if (botonInsideActual && !insidePresionadoAntes) {
    open_lock();
    Serial.println("OK_BOTON_INTERNO");
    insidePresionadoAntes = true;
    delay(5);
  } else if (!botonInsideActual) {
    insidePresionadoAntes = false;
  }

  // 4. NUEVO: Botón Externo (Solicitud de Reconocimiento Facial)
  bool botonOutsideActual = !digitalRead(BUTTON_OUTSIDE);
  if (botonOutsideActual && !outsidePresionadoAntes) {
    // Le avisamos a la Raspberry Pi que alguien quiere entrar
    Serial.println("REQ_RECOGNITION"); 
    outsidePresionadoAntes = true;
    delay(5);
  } else if (!botonOutsideActual) {
    outsidePresionadoAntes = false;
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