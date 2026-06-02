# Proyecto con Raspberry Pi 4 y arduino

Integración de una cerradura magnética controlada por el arduino y una cámara con reconocimiento facial gestionada por la Raspberry.

## Código del arduino
```cpp
// ------------------------------------------------------------------
// Smart Lock - Controlador de Hardware (Arduino)
// ------------------------------------------------------------------

const int PIN_RELE = 7; // Pin digital conectado al módulo de relé

void setup() {
  // Inicializar comunicación serial a 9600 baudios (debe coincidir con la Raspberry)
  Serial.begin(9600);
  
  // Configurar el pin del relé como salida
  pinMode(PIN_RELE, OUTPUT);
  
  // Asegurar que inicie apagado (cerradura bloqueada)
  // Nota: Si tu módulo de relé se activa con LOW, cambia esto a HIGH.
  digitalWrite(PIN_RELE, LOW); 
  
  // Enviar un mensaje inicial para saber que el Arduino reinició correctamente
  Serial.println("ARDUINO_LISTO");
}

void loop() {
  // Verificar si hay datos disponibles en el puerto serial desde la Raspberry
  if (Serial.available() > 0) {
    
    // Leer la cadena de texto hasta el salto de línea (\n)
    String comando = Serial.readStringUntil('\n');
    
    // Eliminar espacios en blanco o caracteres ocultos (como \r)
    comando.trim(); 

    // Procesar el comando recibido
    if (comando == "OPEN") {
      // 1. Abrir la cerradura
      digitalWrite(PIN_RELE, HIGH);   
      Serial.println("OK_ABIERTO");   
      
      // 2. Mantener abierto por 5 segundos (5000 milisegundos)
      delay(5000);                    
      
      // 3. Volver a bloquear la cerradura
      digitalWrite(PIN_RELE, LOW);    
      Serial.println("OK_CERRADO");  
      
    } else if (comando.length() > 0) {
      // Si llega un comando distinto a "OPEN" y no está vacío
      Serial.print("ERROR_COMANDO_DESCONOCIDO:");
      Serial.println(comando);
    }
  }
}
```
