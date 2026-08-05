// =====================================================================
//  Módulo de campo — ESP32
//
//  Coleta temperatura e vibração (ADXL345) e publica telemetria em JSON
//  via MQTT para o painel (Orange Pi + Node-RED).
//
//  Configuração: copie include/config.example.h para include/config.h
//  e ajuste os valores.
// =====================================================================
#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <math.h>

#include "config.h"

// --- Seleção do sensor de temperatura em tempo de compilação ----------
#if TEMP_SENSOR_TYPE == 1
  #include <OneWire.h>
  #include <DallasTemperature.h>
  static OneWire oneWire(PIN_TEMP);
  static DallasTemperature ds18b20(&oneWire);
#elif TEMP_SENSOR_TYPE == 2
  #include <DHT.h>
  static DHT dht(PIN_TEMP, DHT22);
#else
  #error "TEMP_SENSOR_TYPE invalido (use 1=DS18B20 ou 2=DHT22)"
#endif

// --- Objetos globais --------------------------------------------------
static WiFiClient          wifiClient;
static PubSubClient        mqtt(wifiClient);
static Adafruit_ADXL345_Unified adxl(12345);

// --- Tópicos MQTT montados a partir do DEVICE_ID ----------------------
static String topicTelemetria;
static String topicStatus;

static unsigned long ultimaPublicacao = 0;

// =====================================================================
//  Wi-Fi
// =====================================================================
static void conectarWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.printf("[WiFi] Conectando a \"%s\" ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long inicio = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - inicio < 20000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WiFi] Conectado. IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("[WiFi] Falha ao conectar (nova tentativa no loop).");
  }
}

// =====================================================================
//  MQTT
// =====================================================================
static void conectarMQTT() {
  if (mqtt.connected()) return;

  mqtt.setServer(MQTT_HOST, MQTT_PORT);

  String clientId = String("esp32-") + DEVICE_ID;
  Serial.printf("[MQTT] Conectando a %s:%d ...\n", MQTT_HOST, MQTT_PORT);

  // Conecta com LWT: broker publica "offline" (retido) se o ESP32 cair.
  bool ok;
  if (strlen(MQTT_USER) > 0) {
    ok = mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASSWORD,
                      topicStatus.c_str(), 1, true, "offline");
  } else {
    ok = mqtt.connect(clientId.c_str(), nullptr, nullptr,
                      topicStatus.c_str(), 1, true, "offline");
  }

  if (ok) {
    Serial.println("[MQTT] Conectado.");
    mqtt.publish(topicStatus.c_str(), "online", true);  // retido
  } else {
    Serial.printf("[MQTT] Falha (rc=%d). Nova tentativa no loop.\n", mqtt.state());
  }
}

// =====================================================================
//  Sensores
// =====================================================================
static void iniciarSensorTemperatura() {
#if TEMP_SENSOR_TYPE == 1
  ds18b20.begin();
#elif TEMP_SENSOR_TYPE == 2
  dht.begin();
#endif
}

// Retorna a temperatura em °C, ou NAN em caso de falha de leitura.
static float lerTemperatura() {
#if TEMP_SENSOR_TYPE == 1
  ds18b20.requestTemperatures();
  float t = ds18b20.getTempCByIndex(0);
  if (t <= DEVICE_DISCONNECTED_C) return NAN;
  return t;
#elif TEMP_SENSOR_TYPE == 2
  return dht.readTemperature();   // já retorna NAN em caso de falha
#endif
}

static bool iniciarADXL() {
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  if (!adxl.begin(ADXL345_ADDR)) {
    Serial.println("[ADXL] Sensor nao encontrado! Verifique a ligacao I2C.");
    return false;
  }
  adxl.setRange(ADXL345_RANGE_16_G);
  adxl.setDataRate(ADXL345_DATARATE_800_HZ);
  Serial.println("[ADXL] Inicializado.");
  return true;
}

// Amostra a aceleração por uma janela e calcula RMS e pico do componente
// AC (magnitude com a gravidade removida pela média da janela). Resultado
// em unidades de g.
struct ResultadoVibracao {
  float rms_g;
  float pico_g;
  float media_x_g;
  float media_y_g;
  float media_z_g;
};

static ResultadoVibracao medirVibracao() {
  static const float G = 9.80665f;   // m/s² por g
  const int N = VIB_AMOSTRAS;

  float somaMag = 0.0f;
  float somaX = 0.0f, somaY = 0.0f, somaZ = 0.0f;
  float mags[N];

  for (int i = 0; i < N; i++) {
    sensors_event_t ev;
    adxl.getEvent(&ev);

    float x = ev.acceleration.x / G;
    float y = ev.acceleration.y / G;
    float z = ev.acceleration.z / G;

    float mag = sqrtf(x * x + y * y + z * z);
    mags[i] = mag;

    somaMag += mag;
    somaX += x;
    somaY += y;
    somaZ += z;

    delayMicroseconds(VIB_INTERVALO_US);
  }

  float mediaMag = somaMag / N;

  // RMS do componente AC (magnitude - média) e pico absoluto do AC.
  float somaQuad = 0.0f;
  float pico = 0.0f;
  for (int i = 0; i < N; i++) {
    float ac = mags[i] - mediaMag;
    somaQuad += ac * ac;
    if (fabsf(ac) > pico) pico = fabsf(ac);
  }

  ResultadoVibracao r;
  r.rms_g     = sqrtf(somaQuad / N);
  r.pico_g    = pico;
  r.media_x_g = somaX / N;
  r.media_y_g = somaY / N;
  r.media_z_g = somaZ / N;
  return r;
}

// =====================================================================
//  Publicação
// =====================================================================
static void publicarTelemetria() {
  ResultadoVibracao vib = medirVibracao();
  float temp = lerTemperatura();

  JsonDocument doc;
  doc["device_id"]     = DEVICE_ID;
  doc["ts"]            = millis();

  if (isnan(temp)) {
    doc["temperatura_c"] = nullptr;   // sinaliza falha de leitura
  } else {
    doc["temperatura_c"] = round(temp * 10) / 10.0;
  }

  JsonObject v = doc["vibracao"].to<JsonObject>();
  v["rms_g"]    = round(vib.rms_g * 1000) / 1000.0;
  v["pico_g"]   = round(vib.pico_g * 1000) / 1000.0;
  v["eixo_x_g"] = round(vib.media_x_g * 100) / 100.0;
  v["eixo_y_g"] = round(vib.media_y_g * 100) / 100.0;
  v["eixo_z_g"] = round(vib.media_z_g * 100) / 100.0;

  JsonObject rede = doc["rede"].to<JsonObject>();
  rede["rssi_dbm"] = WiFi.RSSI();
  rede["uptime_s"] = millis() / 1000;

  char buffer[384];
  size_t n = serializeJson(doc, buffer);
  mqtt.publish(topicTelemetria.c_str(), buffer, n);

  Serial.printf("[PUB] %s\n", buffer);
}

// =====================================================================
//  setup / loop
// =====================================================================
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== Modulo de campo ESP32 — monitoramento ===");

  topicTelemetria = String(MQTT_BASE_TOPIC) + "/" + DEVICE_ID + "/telemetria";
  topicStatus     = String(MQTT_BASE_TOPIC) + "/" + DEVICE_ID + "/status";

  iniciarSensorTemperatura();
  iniciarADXL();

  conectarWiFi();
  conectarMQTT();
}

void loop() {
  conectarWiFi();
  conectarMQTT();
  mqtt.loop();

  unsigned long agora = millis();
  if (agora - ultimaPublicacao >= INTERVALO_PUBLICACAO_MS) {
    ultimaPublicacao = agora;
    if (mqtt.connected()) {
      publicarTelemetria();
    }
  }
}
