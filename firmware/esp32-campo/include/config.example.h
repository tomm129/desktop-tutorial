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
//     1 = DS18B20  (1-Wire, contato)
//     2 = DHT22    (temperatura + umidade, contato)
//     3 = MLX90614 (infravermelho sem contato, I²C)  ← padrão do projeto
// ---------------------------------------------------------------------
#define TEMP_SENSOR_TYPE       3

#define PIN_TEMP               4       // DATA do DS18B20/DHT22 (não usado no MLX90614)
#define MLX90614_ADDR          0x5A    // endereço I²C padrão do MLX90614

// ---------------------------------------------------------------------
//  ADXL345 (vibração) — I²C
// ---------------------------------------------------------------------
#define PIN_I2C_SDA            21
#define PIN_I2C_SCL            22
#define ADXL345_ADDR           0x53    // 0x53 (SDO=GND) ou 0x1D (SDO=VCC)

// Amostragem de vibração
//
// 384 amostras a ~370 Hz dão ~1,04 s de janela. O tamanho é ditado pela
// VELOCIDADE, não pelo RMS de aceleração: a integração usa um passa-alta de
// 10 Hz, e medir bem uma componente de 10 Hz exige alguns ciclos dela dentro
// da janela. Com 256 amostras sobrava pouco mais de meio segundo depois do
// aquecimento do filtro — pouco para os 10 Hz da base da banda ISO.
#define VIB_AMOSTRAS           384     // amostras por janela de cálculo

// Amostras iniciais descartadas do cálculo (o filtro passa-alta precisa
// assentar; enquanto ele assenta a saída é transitório, não sinal). Elas são
// AMOSTRADAS normalmente — só não entram nas estatísticas.
#define VIB_AQUECIMENTO        96

// Pausa ENTRE leituras. A taxa real é menor que 1/VIB_INTERVALO_US, porque
// cada getEvent() gasta ~0,7 ms no barramento I²C a 100 kHz: com 2000 us dá
// ~370 Hz, não 500 Hz. O firmware mede e publica a taxa real em
// "vibracao.fs_hz". Se mudar este valor, reveja o ODR do ADXL em
// iniciarADXL() — ele precisa ficar abaixo de metade da taxa real, senão há
// aliasing (sinal alto rebate para dentro da banda e vira pico fantasma).
#define VIB_INTERVALO_US       2000

// Corte do passa-alta usado na integração aceleração -> velocidade, em Hz.
// 10 Hz é o piso da banda da ISO 20816/10816, que é a norma pela qual a
// manutenção julga severidade em mm/s. Não baixar sem necessidade: abaixo de
// 10 Hz a integração amplifica ruído e deriva de offset muito mais que sinal.
#define VIB_HP_HZ              10.0f

// ---------------------------------------------------------------------
//  Publicação
// ---------------------------------------------------------------------
#define INTERVALO_PUBLICACAO_MS  5000  // envia telemetria a cada 5 s

// Amostras guardadas na RAM quando o MQTT está fora do ar, para serem
// enviadas quando a conexão voltar. A 5 s por amostra, 240 cobrem 20 min de
// queda em resolução cheia — e mais que isso por decimação (ver buffer.cpp
// na descrição em main.cpp). Cada entrada ocupa 32 bytes: 240 = 7,7 KB.
#define BUFFER_OFFLINE_N       240
