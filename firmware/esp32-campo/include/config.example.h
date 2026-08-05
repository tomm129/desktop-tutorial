// =====================================================================
//  config.example.h  —  Módulo de campo ESP32
//
//  Copie este arquivo para "config.h" e ajuste os valores.
//  O arquivo config.h NÃO é versionado (veja .gitignore) para não expor
//  credenciais de Wi-Fi / MQTT.
// =====================================================================
#pragma once

// ---------------------------------------------------------------------
//  Identificação do dispositivo
// ---------------------------------------------------------------------
#define DEVICE_ID              "motor-01"

// ---------------------------------------------------------------------
//  Wi-Fi
// ---------------------------------------------------------------------
#define WIFI_SSID              "SUA_REDE_WIFI"
#define WIFI_PASSWORD          "SUA_SENHA_WIFI"

// ---------------------------------------------------------------------
//  MQTT (broker rodando no Orange Pi)
// ---------------------------------------------------------------------
#define MQTT_HOST              "192.168.0.10"   // IP do Orange Pi
#define MQTT_PORT              1883
#define MQTT_USER              ""               // vazio = sem autenticação
#define MQTT_PASSWORD          ""

// Tópicos (montados a partir do DEVICE_ID em main.cpp)
#define MQTT_BASE_TOPIC        "monitoramento"

// ---------------------------------------------------------------------
//  Sensor de temperatura  —  escolha UM
//     1 = DS18B20 (1-Wire, padrão)
//     2 = DHT22   (temperatura + umidade)
// ---------------------------------------------------------------------
#define TEMP_SENSOR_TYPE       1

#define PIN_TEMP               4       // DATA do DS18B20 ou DHT22

// ---------------------------------------------------------------------
//  ADXL345 (vibração) — I²C
// ---------------------------------------------------------------------
#define PIN_I2C_SDA            21
#define PIN_I2C_SCL            22
#define ADXL345_ADDR           0x53    // 0x53 (SDO=GND) ou 0x1D (SDO=VCC)

// Amostragem de vibração
#define VIB_AMOSTRAS           256     // amostras por janela de cálculo
#define VIB_INTERVALO_US       2000    // ~500 Hz de amostragem

// ---------------------------------------------------------------------
//  Publicação
// ---------------------------------------------------------------------
#define INTERVALO_PUBLICACAO_MS  5000  // envia telemetria a cada 5 s
