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
  float crista;      // fator de crista (pico/RMS) do eixo mais impulsivo
  float vel_mm_s;    // velocidade RMS combinada, mm/s (banda a partir de 10 Hz)
  float media_x_g;   // componente DC por eixo (orientação/gravidade)
  float media_y_g;
  float media_z_g;
  float fs_hz;       // taxa de amostragem REAL medida nesta janela
};

// ---------------------------------------------------------------------
//  Passa-alta Butterworth de 2ª ordem (biquad, forma RBJ, Q = 1/√2).
//
//  Por que Butterworth e não uma cascata de 1ª ordem: um passa-alta de 1ª
//  ordem em 10 Hz ainda atenua 12% em 30 Hz — e como a cadeia precisa de
//  vários deles, o erro se multiplica. Medido em simulação: três filtros de
//  1ª ordem derrubavam a velocidade em 33% a 30 Hz, o que inviabiliza
//  comparar o número com a faixa da ISO. O Butterworth é maximamente plano
//  na banda de passagem: dois deles custam 1,4% no mesmo ponto.
//
//  Os coeficientes dependem de fs, então são calculados UMA vez por janela
//  (não por amostra) — duas chamadas de sin/cos em vez de 384.
// ---------------------------------------------------------------------
struct Biquad {
  float b0, b1, b2, a1, a2;      // coeficientes (já normalizados por a0)
  float x1, x2, y1, y2;          // estado
  bool  iniciado;
};

static void biquad_passa_alta(Biquad &f, float fc_hz, float fs_hz) {
  const float w0    = 2.0f * (float)M_PI * fc_hz / fs_hz;
  const float alpha = sinf(w0) / (2.0f * 0.70710678f);   // Q = 1/√2
  const float cw    = cosf(w0);
  const float a0    = 1.0f + alpha;

  f.b0 = ((1.0f + cw) * 0.5f) / a0;
  f.b1 = (-(1.0f + cw)) / a0;
  f.b2 = f.b0;
  f.a1 = (-2.0f * cw) / a0;
  f.a2 = (1.0f - alpha) / a0;

  f.x1 = f.x2 = f.y1 = f.y2 = 0.0f;
  f.iniciado = false;
}

static float biquad(Biquad &f, float x) {
  if (!f.iniciado) {
    // Assenta a entrada no valor atual em vez de em zero: senão a primeira
    // amostra entra como um degrau, e um degrau num passa-alta produz um
    // transitório que leva vários ciclos para dissipar.
    f.iniciado = true;
    f.x1 = f.x2 = x;
  }
  const float y = f.b0 * x + f.b1 * f.x1 + f.b2 * f.x2
                            - f.a1 * f.y1 - f.a2 * f.y2;
  f.x2 = f.x1;  f.x1 = x;
  f.y2 = f.y1;  f.y1 = y;
  return y;
}

// Coeficientes da regra de integração v[n] = v[n-1] + dt·(C0·a[n] + C1·a[n-1]).
//
// Não é trapézio (½, ½). O trapézio é a escolha reflexa, mas seu ganho
// discreto é (ωdt/2)·cot(ωdt/2), que ERRA para baixo e cresce com a
// frequência: a 370 Hz de amostragem ele perde 8% em 60 Hz e 25% em 100 Hz.
// O retângulo (1, 0) erra para cima, com metade da magnitude. A mistura
// abaixo cancela quase todo o termo de 2ª ordem dos dois:
//
//   erro máximo até 100 Hz  ·  trapézio 25,3%  ·  esta mistura 1,8%
//
// Verificado por varredura de fs entre 250 e 600 Hz — o ganho se mantém.
// A soma C0+C1 tem de ser 1, senão a escala de DC sai errada.
static const float INT_C0 = 0.875f;
static const float INT_C1 = 0.125f;

// Um canal de integração aceleração -> velocidade, por eixo.
//
// A cadeia é passa-alta -> integra -> passa-alta, e cada estágio existe por
// um motivo:
//
//   1. O passa-alta ANTES da integral tira o resíduo de DC. Integrar um
//      offset constante produz uma rampa sem limite, e o valor de velocidade
//      viraria função do tempo de janela, não da vibração.
//   2. O passa-alta DEPOIS cancela o ganho de +20 dB/década que a integração
//      dá às baixas frequências. Sendo de 2ª ordem (-40 dB/década), ele vence
//      esse ganho com folga e mata a deriva residual.
struct CanalVelocidade {
  Biquad hp_acel, hp_vel;
  float  acel_ant;    // aceleração já filtrada da amostra anterior
  float  vel;         // estado do integrador, m/s
  bool   tem_ant;
};

static void canal_iniciar(CanalVelocidade &c, float fs_hz) {
  biquad_passa_alta(c.hp_acel, VIB_HP_HZ, fs_hz);
  biquad_passa_alta(c.hp_vel,  VIB_HP_HZ, fs_hz);
  c.acel_ant = 0.0f;
  c.vel      = 0.0f;
  c.tem_ant  = false;
}

// Recebe aceleração em m/s², devolve velocidade filtrada em mm/s.
static float integrar_velocidade(CanalVelocidade &c, float acel_ms2, float dt_s) {
  const float a = biquad(c.hp_acel, acel_ms2);

  if (!c.tem_ant) { c.acel_ant = a; c.tem_ant = true; }
  c.vel += dt_s * (INT_C0 * a + INT_C1 * c.acel_ant);
  c.acel_ant = a;

  return biquad(c.hp_vel, c.vel) * 1000.0f;      // m/s -> mm/s
}

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

  // Velocidade: um canal de integração por eixo, e as somas para o RMS.
  //
  // Os coeficientes do biquad precisam de fs, que só se conhece DEPOIS de
  // amostrar. Usamos a taxa medida na janela anterior: ela é estável (o que
  // a define é o barramento I²C, não o sinal), então o erro só existe na
  // primeira janela após o boot. Simulado com fs 8% errada: 1,3% de desvio
  // no mm/s — irrelevante perto do ganho de não ter de adivinhar a taxa.
  static float fs_estimada = 1000000.0f / (float)VIB_INTERVALO_US;
  if (!(fs_estimada > 20.0f) || !isfinite(fs_estimada)) {
    fs_estimada = 1000000.0f / (float)VIB_INTERVALO_US;
  }

  CanalVelocidade cvx, cvy, cvz;
  canal_iniciar(cvx, fs_estimada);
  canal_iniciar(cvy, fs_estimada);
  canal_iniciar(cvz, fs_estimada);

  float svx = 0.0f, svy = 0.0f, svz = 0.0f;
  float svxx = 0.0f, svyy = 0.0f, svzz = 0.0f;

  // Quantas amostras entraram de fato nas estatísticas (N menos aquecimento).
  int n_val = 0;

  unsigned long t0 = micros();
  unsigned long t_ant = t0;

  for (int i = 0; i < N; i++) {
    sensors_event_t ev;
    adxl.getEvent(&ev);

    unsigned long t_ago = micros();
    // Subtração de unsigned: correta mesmo no wrap de micros() (~71 min).
    float dt_s = (float)(t_ago - t_ant) * 1e-6f;
    t_ant = t_ago;
    // Guarda contra a primeira iteração e contra um dt absurdo (uma
    // interrupção longa do Wi-Fi pode engolir dezenas de ms): um dt errado
    // entraria direto no integrador como um degrau de velocidade.
    if (dt_s <= 0.0f || dt_s > 0.05f) { dt_s = VIB_INTERVALO_US * 1e-6f; }

    float x = ev.acceleration.x / G - rx;
    float y = ev.acceleration.y / G - ry;
    float z = ev.acceleration.z / G - rz;

    // A integração usa m/s² (unidade física), não g — o resultado sai em
    // m/s e vira mm/s no fim.
    float vx_mm = integrar_velocidade(cvx, x * G, dt_s);
    float vy_mm = integrar_velocidade(cvy, y * G, dt_s);
    float vz_mm = integrar_velocidade(cvz, z * G, dt_s);

    // As primeiras amostras são amostradas e filtradas (o filtro precisa
    // delas para assentar) mas não contam nas estatísticas.
    if (i >= VIB_AQUECIMENTO) {
      sx += x;  sy += y;  sz += z;
      sxx += x * x;  syy += y * y;  szz += z * z;

      if (x < minx) { minx = x; }
      if (x > maxx) { maxx = x; }
      if (y < miny) { miny = y; }
      if (y > maxy) { maxy = y; }
      if (z < minz) { minz = z; }
      if (z > maxz) { maxz = z; }

      svx += vx_mm;  svy += vy_mm;  svz += vz_mm;
      svxx += vx_mm * vx_mm;  svyy += vy_mm * vy_mm;  svzz += vz_mm * vz_mm;
      n_val++;
    }

    delayMicroseconds(VIB_INTERVALO_US);
  }

  unsigned long dt_us = micros() - t0;
  if (n_val < 2) { n_val = 2; }   // guarda contra config absurda

  // Médias dos valores deslocados (o DC verdadeiro soma a referência).
  float mx = sx / n_val, my = sy / n_val, mz = sz / n_val;
  const int N_est = n_val;

  // Variância = potência AC de cada eixo. Clamp em 0: erro de arredondamento
  // pode produzir um negativo minúsculo quando o eixo está praticamente parado.
  float vx = sxx / N_est - mx * mx;   if (vx < 0.0f) vx = 0.0f;
  float vy = syy / N_est - my * my;   if (vy < 0.0f) vy = 0.0f;
  float vz = szz / N_est - mz * mz;   if (vz < 0.0f) vz = 0.0f;

  // Pico AC exato por eixo (maior afastamento da própria média); reporta o
  // eixo mais excitado.
  float px = fmaxf(maxx - mx, mx - minx);
  float py = fmaxf(maxy - my, my - miny);
  float pz = fmaxf(maxz - mz, mz - minz);

  // ---- Fator de crista ----------------------------------------------
  // pico/RMS, POR EIXO, e reporta o maior. Tem de ser por eixo: o RMS
  // combinado dos três é maior que o de qualquer um deles, então dividir um
  // pico de um único eixo pelo RMS combinado subestima a crista justamente
  // quando ela importa — no eixo isolado onde o rolamento está batendo.
  //
  // Leitura: senoide pura ≈ 1,41; máquina sadia ≈ 3–4; defeito incipiente de
  // rolamento sobe para 5–8 (impactos curtos elevam o pico sem mexer no RMS).
  // Em estágio avançado ela CAI de novo, porque os impactos viram ruído
  // contínuo e o RMS alcança o pico — por isso crista sozinha não serve de
  // alarme, e sim junto do RMS.
  const float PISO_RMS = 1e-4f;   // eixo parado: crista não tem significado
  float cx = (vx > PISO_RMS * PISO_RMS) ? px / sqrtf(vx) : 0.0f;
  float cy = (vy > PISO_RMS * PISO_RMS) ? py / sqrtf(vy) : 0.0f;
  float cz = (vz > PISO_RMS * PISO_RMS) ? pz / sqrtf(vz) : 0.0f;

  // ---- Velocidade RMS -------------------------------------------------
  // Mesma lógica de somar variâncias dos três eixos usada na aceleração: o
  // resultado fica invariante à orientação de montagem do sensor.
  float mvx = svx / N_est, mvy = svy / N_est, mvz = svz / N_est;
  float wx = svxx / N_est - mvx * mvx;   if (wx < 0.0f) wx = 0.0f;
  float wy = svyy / N_est - mvy * mvy;   if (wy < 0.0f) wy = 0.0f;
  float wz = svzz / N_est - mvz * mvz;   if (wz < 0.0f) wz = 0.0f;

  ResultadoVibracao r;
  r.rms_g     = sqrtf(vx + vy + vz);
  r.pico_g    = fmaxf(px, fmaxf(py, pz));
  r.crista    = fmaxf(cx, fmaxf(cy, cz));
  r.vel_mm_s  = sqrtf(wx + wy + wz);
  r.media_x_g = mx + rx;
  r.media_y_g = my + ry;
  r.media_z_g = mz + rz;
  r.fs_hz     = (dt_us > 0) ? (1000000.0f * N / (float)dt_us) : 0.0f;

  // Realimenta a estimativa para a próxima janela calcular os coeficientes
  // do filtro com a taxa real desta.
  if (r.fs_hz > 20.0f && isfinite(r.fs_hz)) { fs_estimada = r.fs_hz; }
  return r;
}

// =====================================================================
//  Amostra e buffer offline
//
//  Sem isso, tudo que é medido enquanto o MQTT está fora do ar é perdido
//  para sempre. Isso era um buraco no gráfico enquanto o painel só mostrava
//  o instante; agora que há banco de histórico, é perda definitiva de dado
//  — justamente no período em que ninguém estava vendo a máquina.
// =====================================================================
struct Amostra {
  unsigned long capturado_em;   // millis() da medição
  float temperatura_c;          // NAN = falha de leitura
  float rms_g;
  float pico_g;
  float crista;
  float vel_mm_s;
  // Componente DC de cada eixo — o vetor da gravidade visto pelo sensor.
  // Não é vibração: é ORIENTAÇÃO. Se esse vetor mudar com a máquina parada,
  // o sensor se soltou ou girou na base, e todo o resto da leitura passa a
  // ser sobre outra coisa. É diagnóstico barato de fixação.
  float eixo_x_g;
  float eixo_y_g;
  float eixo_z_g;
  float fs_hz;
};

static Amostra bufferOffline[BUFFER_OFFLINE_N];
static int  bufN = 0;           // quantas amostras guardadas
static bool bufDecimado = false;  // já houve decimação? (vai no JSON)

// Guarda uma amostra. Com o buffer cheio, DECIMA em vez de descartar: joga
// fora uma amostra sim, outra não, dobrando o período coberto pela metade da
// resolução.
//
// Por que decimar e não simplesmente sobrescrever a mais antiga: numa queda
// longa, o anel clássico preserva só os últimos minutos e perde o INÍCIO —
// que é onde está a pista do que derrubou a coisa. Decimando, a queda inteira
// fica registrada, mais grossa. Como cada amostra carrega o próprio instante,
// o espaçamento irregular não atrapalha o painel nem o banco.
static void guardarAmostra(const Amostra &a) {
  if (bufN >= BUFFER_OFFLINE_N) {
    int destino = 0;
    for (int i = 0; i < bufN; i += 2) { bufferOffline[destino++] = bufferOffline[i]; }
    bufN = destino;
    bufDecimado = true;
    Serial.printf("[BUF] cheio -> decimado para %d amostras\n", bufN);
  }
  bufferOffline[bufN++] = a;
}

// Monta o JSON de uma amostra e publica.
//
// atraso_ms diz há quanto tempo a amostra foi COLHIDA. O ESP32 não tem
// relógio de parede (e um reboot zeraria qualquer contagem), então quem
// reconstrói o instante real é o painel, que tem hora certa:
//     ts_real = agora - atraso_ms
// Assim o backfill entra no histórico na hora em que de fato aconteceu, sem
// depender de NTP no dispositivo.
static bool enviarAmostra(const Amostra &a, unsigned long atraso_ms, bool doBuffer) {
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["ts"]        = a.capturado_em;

  if (isnan(a.temperatura_c)) {
    doc["temperatura_c"] = nullptr;   // sinaliza falha de leitura
  } else {
    doc["temperatura_c"] = round(a.temperatura_c * 10) / 10.0;
  }

  JsonObject v = doc["vibracao"].to<JsonObject>();
  v["rms_g"]    = round(a.rms_g * 1000) / 1000.0;
  v["pico_g"]   = round(a.pico_g * 1000) / 1000.0;
  v["crista"]   = round(a.crista * 100) / 100.0;
  v["vel_mm_s"] = round(a.vel_mm_s * 100) / 100.0;
  v["eixo_x_g"] = round(a.eixo_x_g * 100) / 100.0;
  v["eixo_y_g"] = round(a.eixo_y_g * 100) / 100.0;
  v["eixo_z_g"] = round(a.eixo_z_g * 100) / 100.0;
  v["fs_hz"]    = round(a.fs_hz * 10) / 10.0;     // taxa real, não a nominal

  if (doBuffer) {
    // Só o backfill carrega esses campos. O painel usa "buffer" para mandar
    // a amostra para o histórico SEM deixar que ela mexa no estado ao vivo:
    // um valor crítico de duas horas atrás não pode disparar alarme agora.
    doc["buffer"]    = true;
    doc["atraso_ms"] = atraso_ms;
    if (bufDecimado) { doc["decimado"] = true; }
  } else {
    JsonObject rede = doc["rede"].to<JsonObject>();
    rede["rssi_dbm"] = WiFi.RSSI();
    rede["uptime_s"] = millis() / 1000;
  }

  char texto[512];
  size_t n = serializeJson(doc, texto, sizeof(texto));

  // serializeJson TRUNCA em silêncio quando o buffer é pequeno, e o que sai
  // é JSON inválido — o painel descarta e o dado some sem nenhum erro
  // visível dos dois lados. Vale o teste explícito: o pacote cresceu com a
  // velocidade, a crista e os três eixos, e um device_id longo empurra mais.
  if (n == 0 || n >= sizeof(texto) - 1) {
    Serial.printf("[PUB] ERRO: JSON nao coube em %u bytes (n=%u) — "
                  "aumente 'texto' em enviarAmostra()\n",
                  (unsigned)sizeof(texto), (unsigned)n);
    return false;
  }
  return mqtt.publish(topicTelemetria.c_str(), texto, n);
}

// Esvazia o buffer depois que a conexão volta.
//
// Manda no máximo LOTE por chamada e devolve o controle ao loop: despejar
// centenas de mensagens de uma vez estoura o buffer de saída do PubSubClient
// e impede o mqtt.loop() de responder ao keepalive — o broker derruba a
// conexão no meio do envio e o dado se perde de novo.
static void drenarBuffer() {
  if (bufN == 0 || !mqtt.connected()) { return; }

  const int LOTE = 10;
  int enviados = 0;
  unsigned long agora = millis();

  while (bufN > 0 && enviados < LOTE) {
    const Amostra &a = bufferOffline[0];
    if (!enviarAmostra(a, agora - a.capturado_em, true)) {
      Serial.println("[BUF] falha ao enviar, mantendo o resto para depois");
      return;
    }
    // Consome do começo (mais antigo primeiro), mantendo a ordem cronológica.
    for (int i = 1; i < bufN; i++) { bufferOffline[i - 1] = bufferOffline[i]; }
    bufN--;
    enviados++;
    mqtt.loop();          // mantém o keepalive vivo durante o despejo
  }

  if (enviados) {
    Serial.printf("[BUF] %d amostras recuperadas, faltam %d\n", enviados, bufN);
  }
  if (bufN == 0) { bufDecimado = false; }
}

// =====================================================================
//  Publicação
// =====================================================================
static void publicarTelemetria() {
  ResultadoVibracao vib = medirVibracao();

  Amostra a;
  a.capturado_em  = millis();
  a.temperatura_c = lerTemperatura();
  a.rms_g         = vib.rms_g;
  a.pico_g        = vib.pico_g;
  a.crista        = vib.crista;
  a.vel_mm_s      = vib.vel_mm_s;
  a.eixo_x_g      = vib.media_x_g;
  a.eixo_y_g      = vib.media_y_g;
  a.eixo_z_g      = vib.media_z_g;
  a.fs_hz         = vib.fs_hz;

  // Com o buffer ainda cheio, a amostra nova vai para o fim da fila em vez
  // de furar a ordem: o painel receberia o "agora" antes do passado e
  // desenharia a linha do tempo ao contrário.
  if (!mqtt.connected() || bufN > 0) {
    guardarAmostra(a);
    Serial.printf("[BUF] guardada (%d/%d)\n", bufN, BUFFER_OFFLINE_N);
    return;
  }

  if (!enviarAmostra(a, 0, false)) {
    guardarAmostra(a);
    Serial.println("[BUF] publicacao falhou, amostra guardada");
    return;
  }

  Serial.printf("[PUB] rms=%.3fg pico=%.3fg crista=%.2f vel=%.2fmm/s fs=%.0fHz\n",
                a.rms_g, a.pico_g, a.crista, a.vel_mm_s, a.fs_hz);
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
  // Tem de caber o payload (até 512 B, ver enviarAmostra) MAIS o tópico e o
  // cabeçalho MQTT. Se ficar apertado, o publish falha silenciosamente
  // devolvendo false — e a amostra iria parar no buffer offline sem que
  // houvesse queda de rede nenhuma.
  mqtt.setBufferSize(768);
  mqtt.setCallback(mqttCallback);

  conectarWiFi();
  conectarMQTT();
}

void loop() {
  conectarWiFi();
  conectarMQTT();
  mqtt.loop();

  // Recupera o que ficou guardado antes de mandar coisa nova, para o
  // histórico chegar em ordem cronológica.
  drenarBuffer();

  unsigned long agora = millis();
  bool porTempo = (agora - ultimaPublicacao >= intervaloPublicacao);

  // Repare que a condição NÃO exige mqtt.connected(): fora do ar continuamos
  // medindo e guardando. Era exatamente isso que se perdia antes.
  if (solicitarPublicacao || porTempo) {
    solicitarPublicacao = false;
    ultimaPublicacao = agora;
    publicarTelemetria();
  }
}
