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
#elif TEMP_SENSOR_TYPE == 3
  #include <Adafruit_MLX90614.h>
  static Adafruit_MLX90614 mlx = Adafruit_MLX90614();
#else
  #error "TEMP_SENSOR_TYPE invalido (use 1=DS18B20, 2=DHT22 ou 3=MLX90614)"
#endif

// --- Objetos globais --------------------------------------------------
static WiFiClient          wifiClient;
static PubSubClient        mqtt(wifiClient);
static Adafruit_ADXL345_Unified adxl(12345);

// --- Tópicos MQTT montados a partir do DEVICE_ID ----------------------
static String topicTelemetria;
static String topicStatus;
static String topicCmd;

static unsigned long ultimaPublicacao = 0;

// Intervalo de publicação (ms). Inicia com o valor do config.h, mas pode ser
// alterado em tempo de execução por um comando vindo do Node-RED.
static unsigned long intervaloPublicacao = INTERVALO_PUBLICACAO_MS;

// Marcado por um comando "publicar" para forçar uma leitura imediata.
static volatile bool solicitarPublicacao = false;

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

// Recebe comandos do Node-RED em monitoramento/<DEVICE_ID>/cmd.
// Payload em JSON. Exemplos:
//   {"comando":"publicar"}       -> força uma publicação imediata
//   {"intervalo_ms":2000}        -> altera o intervalo de publicação
static void mqttCallback(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload, length);
  if (err) {
    Serial.printf("[CMD] JSON invalido: %s\n", err.c_str());
    return;
  }

  if (doc["intervalo_ms"].is<unsigned long>()) {
    unsigned long novo = doc["intervalo_ms"].as<unsigned long>();
    if (novo >= 500UL && novo <= 3600000UL) {
      intervaloPublicacao = novo;
      Serial.printf("[CMD] Intervalo de publicacao = %lu ms\n", intervaloPublicacao);
    }
  }

  const char* comando = doc["comando"] | "";
  if (strcmp(comando, "publicar") == 0) {
    solicitarPublicacao = true;
    Serial.println("[CMD] Publicacao imediata solicitada.");
  }
}

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
    mqtt.subscribe(topicCmd.c_str(), 1);                 // recebe comandos
    Serial.printf("[MQTT] Inscrito em %s\n", topicCmd.c_str());
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
#elif TEMP_SENSOR_TYPE == 3
  if (!mlx.begin(MLX90614_ADDR)) {
    Serial.println("[MLX90614] Sensor nao encontrado! Verifique a ligacao I2C.");
  } else {
    Serial.println("[MLX90614] Inicializado.");
  }
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
#elif TEMP_SENSOR_TYPE == 3
  // Temperatura do objeto (superfície do equipamento), sem contato.
  return mlx.readObjectTempC();
#endif
}

static bool iniciarADXL() {
  if (!adxl.begin(ADXL345_ADDR)) {
    Serial.println("[ADXL] Sensor nao encontrado! Verifique a ligacao I2C.");
    return false;
  }
  adxl.setRange(ADXL345_RANGE_16_G);

  // ANTI-ALIASING: o ODR do ADXL define a banda interna (BW = ODR/2). Ele
  // precisa ficar abaixo de metade da taxa com que ESTE loop consegue ler o
  // sensor — não da taxa que gostaríamos. Com VIB_INTERVALO_US=2000 mais o
  // tempo do getEvent() por I²C (~0,7 ms a 100 kHz), a taxa real fica em
  // ~370 Hz, então o teto honesto é ~185 Hz. Com 800 Hz (BW 400 Hz), tudo
  // entre 185 e 400 Hz voltava rebatido para dentro da banda útil,
  // indistinguível de sinal real.
  //   200 Hz -> BW 100 Hz, com folga confortável para ~370 Hz de amostragem.
  // A taxa real medida vai no JSON como vibracao.fs_hz — confira lá se
  // mexer em VIB_INTERVALO_US ou na velocidade do barramento I²C.
  adxl.setDataRate(ADXL345_DATARATE_200_HZ);
  Serial.println("[ADXL] Inicializado.");
  return true;
}

// Amostra a aceleração por uma janela e calcula RMS e pico do componente AC
// (gravidade removida pela média da janela, EIXO A EIXO). Resultado em g.
//
// Por que eixo a eixo, e não pela magnitude do vetor: com a = g + v, temos
//   |a| = sqrt(g² + 2·g·v + |v|²) ≈ g + v_paralelo_à_gravidade
// ou seja, a vibração transversal à gravidade só aparece no termo de 2ª
// ordem (|v_perp|²/2g) — atenuada ~1/2g e retificada. Medir pela magnitude
// faz o resultado depender da orientação de montagem do sensor: um motor
// com vibração radial horizontal reportaria RMS quase zero. Somando a
// variância dos três eixos, o RMS fica invariante à orientação.
struct ResultadoVibracao {
  float rms_g;       // RMS AC combinado dos 3 eixos
  float pico_g;      // maior desvio AC absoluto (eixo mais excitado)
  float media_x_g;   // componente DC por eixo (orientação/gravidade)
  float media_y_g;
  float media_z_g;
  float fs_hz;       // taxa de amostragem REAL medida nesta janela
};

static ResultadoVibracao medirVibracao() {
  static const float G = 9.80665f;   // m/s² por g
  const int N = VIB_AMOSTRAS;

  // Referência para "variância deslocada": as somas ficam perto de zero e
  // evitam o cancelamento catastrófico de E[x²]-E[x]² em float — o sinal AC
  // é tipicamente 100–1000x menor que o 1 g estático. A variância não muda
  // ao subtrair uma constante; só a média precisa somá-la de volta.
  sensors_event_t ref;
  adxl.getEvent(&ref);
  const float rx = ref.acceleration.x / G;
  const float ry = ref.acceleration.y / G;
  const float rz = ref.acceleration.z / G;

  float sx = 0.0f, sy = 0.0f, sz = 0.0f;         // somas (já deslocadas)
  float sxx = 0.0f, syy = 0.0f, szz = 0.0f;      // somas dos quadrados
  // Inicia em ±infinito para que o primeiro valor real vença a comparação —
  // iniciar em 0 embutiria um zero que pode não pertencer à janela.
  float minx = INFINITY, maxx = -INFINITY;
  float miny = INFINITY, maxy = -INFINITY;
  float minz = INFINITY, maxz = -INFINITY;

  unsigned long t0 = micros();

  for (int i = 0; i < N; i++) {
    sensors_event_t ev;
    adxl.getEvent(&ev);

    float x = ev.acceleration.x / G - rx;
    float y = ev.acceleration.y / G - ry;
    float z = ev.acceleration.z / G - rz;

    sx += x;  sy += y;  sz += z;
    sxx += x * x;  syy += y * y;  szz += z * z;

    if (x < minx) minx = x;  if (x > maxx) maxx = x;
    if (y < miny) miny = y;  if (y > maxy) maxy = y;
    if (z < minz) minz = z;  if (z > maxz) maxz = z;

    delayMicroseconds(VIB_INTERVALO_US);
  }

  unsigned long dt_us = micros() - t0;

  // Médias dos valores deslocados (o DC verdadeiro soma a referência).
  float mx = sx / N, my = sy / N, mz = sz / N;

  // Variância = potência AC de cada eixo. Clamp em 0: erro de arredondamento
  // pode produzir um negativo minúsculo quando o eixo está praticamente parado.
  float vx = sxx / N - mx * mx;   if (vx < 0.0f) vx = 0.0f;
  float vy = syy / N - my * my;   if (vy < 0.0f) vy = 0.0f;
  float vz = szz / N - mz * mz;   if (vz < 0.0f) vz = 0.0f;

  // Pico AC exato por eixo (maior afastamento da própria média); reporta o
  // eixo mais excitado.
  float px = fmaxf(maxx - mx, mx - minx);
  float py = fmaxf(maxy - my, my - miny);
  float pz = fmaxf(maxz - mz, mz - minz);

  ResultadoVibracao r;
  r.rms_g     = sqrtf(vx + vy + vz);
  r.pico_g    = fmaxf(px, fmaxf(py, pz));
  r.media_x_g = mx + rx;
  r.media_y_g = my + ry;
  r.media_z_g = mz + rz;
  r.fs_hz     = (dt_us > 0) ? (1000000.0f * N / (float)dt_us) : 0.0f;
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
  v["fs_hz"]    = round(vib.fs_hz * 10) / 10.0;   // taxa real, não a nominal

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
  topicCmd        = String(MQTT_BASE_TOPIC) + "/" + DEVICE_ID + "/cmd";

  // Barramento I²C compartilhado (ADXL345 + MLX90614).
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);

  iniciarSensorTemperatura();
  iniciarADXL();

  // Recebe comandos do Node-RED.
  mqtt.setBufferSize(512);
  mqtt.setCallback(mqttCallback);

  conectarWiFi();
  conectarMQTT();
}

void loop() {
  conectarWiFi();
  conectarMQTT();
  mqtt.loop();

  unsigned long agora = millis();
  bool porTempo = (agora - ultimaPublicacao >= intervaloPublicacao);
  if (mqtt.connected() && (solicitarPublicacao || porTempo)) {
    solicitarPublicacao = false;
    ultimaPublicacao = agora;
    publicarTelemetria();
  }
}
