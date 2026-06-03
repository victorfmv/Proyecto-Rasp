# Proyecto con Raspberry Pi 4 y arduino

Integración de una cerradura magnética controlada por el arduino y una cámara con reconocimiento facial gestionada por la Raspberry.

## Código del arduino
```cpp
// ------------------------------------------------------------------
// Smart Lock - Controlador de Hardware No Bloqueante
// ------------------------------------------------------------------

const int PIN_RELE = 7; 

unsigned long tiempoApertura = 0;
const unsigned long COOLDOWN_ABIERTO = 5000; // 5 segundos
bool lockAbierto = false;

void setup() {
  Serial.begin(9600);
  pinMode(PIN_RELE, OUTPUT);
  
  // Ajustar según si tu relé se activa con LOW o HIGH
  digitalWrite(PIN_RELE, LOW); 
  
  Serial.println("ARDUINO_LISTO");
}

void loop() {
  // 1. Manejo del temporizador asíncrono para el cierre automático
  if (lockAbierto && (millis() - tiempoApertura >= COOLDOWN_ABIERTO)) {
    digitalWrite(PIN_RELE, LOW);
    lockAbierto = false;
    Serial.println("OK_CERRADO");
  }

  // 2. Lectura no bloqueante del puerto serial
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim(); 

    if (comando == "OPEN") {
      digitalWrite(PIN_RELE, HIGH);   
      lockAbierto = true;
      tiempoApertura = millis(); // Registrar el tiempo actual
      Serial.println("OK_ABIERTO");   
      
    } else if (comando == "CLOSE") {
      // Permite forzar el cierre inmediato antes de los 5 segundos
      digitalWrite(PIN_RELE, LOW);
      lockAbierto = false;
      Serial.println("OK_CERRADO");
      
    } else if (comando.length() > 0) {
      Serial.print("ERROR_COMANDO_DESCONOCIDO:");
      Serial.println(comando);
    }
  }
}
```
