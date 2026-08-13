// =====================================================================
//  iX Node — provisionamento
//
//  Firmware MINIMO, para validar em bancada o que tem mais risco de
//  surpresa: portal cativo, gravacao em NVS, identidade por MAC e
//  reconexao. A medicao (ADXL345 + MLX90614) e o buffer offline sao
//  portados depois, do firmware Arduino que ja existe e ja foi testado.
//
//  Fluxo:
//    1. id = "ixn-" + 3 ultimos bytes do MAC        (sem configuracao)
//    2. NVS tem Wi-Fi?  nao -> sobe portal cativo, grava, reinicia
//    3. conecta; falhou N vezes -> volta ao portal
//    4. conecta no MQTT e publica um batimento
//
//  Alvo de teste: ESP32-C6. O codigo nao tem nada especifico de chip --
//  roda igual em S3/C3 trocando o target.
// =====================================================================
#include <stdio.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "mqtt_client.h"
#include "nvs_flash.h"

#include "adxl345.h"
#include "config_nvs.h"
#include "identidade.h"
#include "portal.h"
#include "vibracao.h"

static const char *TAG = "ixnode";

// ---------------------------------------------------------------------
//  Vibracao
// ---------------------------------------------------------------------
// Pinos do I2C. Valores de devkit C6; a placa de producao pode diferir.
#define PIN_SDA          6
#define PIN_SCL          7
#define ADXL_ENDERECO    0x53      // 0x53 (SDO=GND) ou 0x1D (SDO=VCC)

// 1600 Hz e o teto PRATICO, nao o do sensor (que vai a 3200).
//
// O limite e o barramento: o datasheet exige ler os 6 bytes de cada
// amostra numa transacao propria, com >=5 us entre elas. A 400 kHz isso
// da ~205 us por amostra, ou seja ~4800 amostras/s de teto absoluto do
// I2C. A 1600 Hz gastamos 1/3 desse tempo e sobra folga para o Wi-Fi;
// a 3200 Hz gastariamos 2/3 e o FIFO passaria a transbordar sempre que
// uma interrupcao de radio atrasasse a drenagem.
//
// Custo honesto da escolha: banda util ate 800 Hz, nao os 1000 Hz do topo
// da ISO 20816. Ainda assim sao 4x os ~185 Hz da versao anterior, e os
// 120 Hz (2x a frequencia de linha) passam a caber com folga -- que era o
// objetivo declarado.
#define VIB_ODR_HZ       1600
#define VIB_AMOSTRAS     1600      // 1,0 s de janela
// O passa-alta de 10 Hz precisa de alguns ciclos de 10 Hz para assentar.
// 400 amostras = 0,25 s = 2,5 ciclos.
#define VIB_AQUECIMENTO  400

// 5 Hz, e NAO os 10 Hz do piso da banda da ISO 20816.
//
// Parece errado por um segundo -- a norma julga de 10 a 1000 Hz, entao o
// reflexo e cortar em 10. Mas a cadeia tem DOIS passa-altas (um antes da
// integracao, um depois), e no proprio corte cada um ja tira 3 dB: os
// dois juntos tiram 6 dB, ou seja METADE. Medido no emulador
// (tools/testes/autoteste-vibracao):
//
//   f (Hz)    corte 10 Hz    corte 5 Hz
//   10          -50,0%         -6,0%
//   15          -17,0%         -0,6%
//   20           -5,9%         -0,4%
//   25           -2,2%         +0,2%
//
// Com corte em 10 Hz, um motor de 600 rpm (1x em 10 Hz) tem a velocidade
// reportada pela METADE, e um de 900 rpm (15 Hz) a 83%. Como a severidade
// ISO se julga justamente em mm/s, isso vira falso negativo em maquina
// lenta: zona C aparecendo como zona A.
//
// O custo esperado de baixar o corte -- assentamento mais lento -- foi
// medido e NAO existe: a 30 Hz o erro com corte de 5 Hz fica em -0,1%
// contra -1,2% do corte de 10, com qualquer aquecimento testado. E a
// rejeicao de DC continua exata (0,000000 g com so gravidade na entrada).
//
// O que continua sem verificacao: ruido real de baixa frequencia de
// maquina de verdade, que sinal sintetico nao reproduz. Se em campo
// aparecer mm/s inflado com maquina parada, este e o primeiro suspeito.
#define VIB_HP_HZ        5.0f

// 19 KB. Static de proposito: nao cabe na pilha de uma task do IDF.
static vib_amostra_t s_amostras[VIB_AMOSTRAS];
static bool s_adxl_ok = false;

// Tentativas antes de desistir da rede e voltar ao portal. Cinco cobre o
// caso comum de roteador reiniciando junto com o no; mais que isso seria
// deixar o dispositivo mudo por minutos numa rede que mudou de senha.
#define MAX_TENTATIVAS   5
#define INTERVALO_MS     5000

static EventGroupHandle_t s_rede;
#define BIT_CONECTADO BIT0
#define BIT_FALHOU    BIT1

static int s_tentativas = 0;
static esp_mqtt_client_handle_t s_mqtt = NULL;
static bool s_mqtt_ok = false;
static char s_topico[64];
static char s_topico_status[64];

// ---------------------------------------------------------------------
//  Wi-Fi
// ---------------------------------------------------------------------
static void ao_evento(void *arg, esp_event_base_t base, int32_t id, void *dados)
{
    (void)arg; (void)dados;

    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        if (++s_tentativas <= MAX_TENTATIVAS) {
            ESP_LOGW(TAG, "desconectado, tentativa %d/%d", s_tentativas, MAX_TENTATIVAS);
            vTaskDelay(pdMS_TO_TICKS(1000));
            esp_wifi_connect();
        } else {
            xEventGroupSetBits(s_rede, BIT_FALHOU);
        }
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = (ip_event_got_ip_t *)dados;
        ESP_LOGI(TAG, "conectado, IP " IPSTR, IP2STR(&ev->ip_info.ip));
        s_tentativas = 0;
        xEventGroupSetBits(s_rede, BIT_CONECTADO);
    }
}

static bool conectar_wifi(const ixnode_config_t *cfg)
{
    s_rede = xEventGroupCreate();

    esp_netif_create_default_wifi_sta();
    wifi_init_config_t ic = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&ic));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &ao_evento, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &ao_evento, NULL, NULL));

    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, cfg->ssid, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, cfg->senha, sizeof(wc.sta.password));

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wc));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "conectando em '%s'...", cfg->ssid);
    EventBits_t b = xEventGroupWaitBits(s_rede, BIT_CONECTADO | BIT_FALHOU,
                                        pdFALSE, pdFALSE, portMAX_DELAY);
    return (b & BIT_CONECTADO) != 0;
}

// ---------------------------------------------------------------------
//  MQTT
// ---------------------------------------------------------------------
static void ao_mqtt(void *arg, esp_event_base_t base, int32_t id, void *dados)
{
    (void)arg; (void)base;
    esp_mqtt_event_handle_t ev = (esp_mqtt_event_handle_t)dados;

    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT conectado");
        s_mqtt_ok = true;
        // Retido: quem abrir o painel depois ve o estado atual sem precisar
        // esperar o proximo batimento.
        esp_mqtt_client_publish(s_mqtt, s_topico_status, "online", 0, 1, 1);
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT desconectado");
        s_mqtt_ok = false;
        break;
    case MQTT_EVENT_ERROR:
        ESP_LOGW(TAG, "MQTT erro (tipo %d)", ev->error_handle->error_type);
        break;
    default:
        break;
    }
}

static void iniciar_mqtt(const ixnode_config_t *cfg)
{
    char uri[96];
    snprintf(uri, sizeof(uri), "mqtt://%s:%d", cfg->mqtt_host, cfg->mqtt_porta);

    snprintf(s_topico, sizeof(s_topico), "monitoramento/%s/telemetria", ixnode_id());
    snprintf(s_topico_status, sizeof(s_topico_status),
             "monitoramento/%s/status", ixnode_id());

    esp_mqtt_client_config_t mc = {
        .broker.address.uri = uri,
        .credentials.client_id = ixnode_id(),
        // LWT: se o no cair, o broker marca offline sozinho. Sem isto o
        // painel so descobre pelo silencio, com o atraso do timeout.
        .session.last_will.topic = s_topico_status,
        .session.last_will.msg = "offline",
        .session.last_will.qos = 1,
        .session.last_will.retain = 1,
    };

    s_mqtt = esp_mqtt_client_init(&mc);
    esp_mqtt_client_register_event(s_mqtt, ESP_EVENT_ANY_ID, ao_mqtt, NULL);
    esp_mqtt_client_start(s_mqtt);
    ESP_LOGI(TAG, "MQTT em %s, publicando em %s", uri, s_topico);
}

// ---------------------------------------------------------------------
//  app_main
// ---------------------------------------------------------------------
void app_main(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        // Particao NVS incompativel ou cheia: apagar e recomecar e melhor que
        // travar o boot. Perde a configuracao, e o no volta ao portal --
        // recuperavel por quem estiver na frente dele.
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    ESP_LOGI(TAG, "===============================");
    ESP_LOGI(TAG, " iX Node  %s", ixnode_id());
    ESP_LOGI(TAG, "===============================");

    // Auto-teste da matematica de vibracao, ANTES de rede e de sensor.
    //
    // E computacao pura -- roda com ou sem ADXL ligado. Existe porque nao
    // ha compilador de host nesta maquina para testar o C fora do chip: a
    // referencia em Python (tools/testes/testa_vibracao.py) valida o
    // ALGORITMO, nao este codigo. Sem isto, um coeficiente trocado no port
    // sairia como numero plausivel e errado no painel, meses depois,
    // indistinguivel de maquina ruim.
    {
        float err[3];
        bool ok = vib_autoteste((float)VIB_ODR_HZ, err);
        ESP_LOGI(TAG, "auto-teste vibracao: %s "
                      "(erro rms %+.2f%%, crista %+.2f%%, vel %+.2f%%)",
                 ok ? "PASSOU" : "FALHOU", err[0], err[1], err[2]);
        if (!ok) {
            // Nao aborta o boot: o no ainda serve para temperatura e para
            // aparecer no painel. Mas o log tem de gritar, porque todo
            // numero de vibracao daqui para a frente e suspeito.
            ESP_LOGE(TAG, "MATEMATICA DE VIBRACAO INCORRETA — "
                          "nao confie no mm/s deste no");
        }
    }

    ixnode_config_t cfg;
    if (!ixnode_config_carregar(&cfg)) {
        ESP_LOGW(TAG, "no virgem — subindo portal de configuracao");
        if (ixnode_portal_executar()) {
            ESP_LOGI(TAG, "configurado; reiniciando");
            vTaskDelay(pdMS_TO_TICKS(500));
            esp_restart();
        }
        // Portal so retorna false em falha de infraestrutura (HTTP nao subiu).
        // Reiniciar e a unica saida sensata: continuar sem rede nem portal
        // deixaria o no inerte e mudo.
        ESP_LOGE(TAG, "portal falhou; reiniciando");
        vTaskDelay(pdMS_TO_TICKS(2000));
        esp_restart();
    }

    if (!conectar_wifi(&cfg)) {
        // Rede gravada que nao conecta: senha trocada, roteador substituido,
        // no mudado de lugar. Apaga e volta ao portal, para ser reconfigurado
        // sem precisar de cabo nem de PC.
        ESP_LOGE(TAG, "nao conectou apos %d tentativas — voltando ao portal",
                 MAX_TENTATIVAS);
        ixnode_config_apagar();
        vTaskDelay(pdMS_TO_TICKS(1000));
        esp_restart();
    }

    iniciar_mqtt(&cfg);

    // Sensor. Falhar aqui nao derruba o no: sem ADXL ele ainda publica
    // batimento e aparece no painel, que e melhor que sumir -- quem estiver
    // na frente da maquina precisa saber que o no vive mas o sensor nao
    // responde, e isso so aparece se ele continuar falando.
    if (adxl345_iniciar(PIN_SDA, PIN_SCL, ADXL_ENDERECO, VIB_ODR_HZ) == ESP_OK) {
        s_adxl_ok = true;
    } else {
        ESP_LOGE(TAG, "sem ADXL345 — publicando so batimento");
    }

    int n = 0;
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(INTERVALO_MS));
        if (!s_mqtt_ok) {
            continue;
        }

        int64_t up = esp_timer_get_time() / 1000000;
        char json[384];

        vib_resultado_t r;
        bool tem_vib = false;
        bool overrun = false;

        if (s_adxl_ok) {
            if (adxl345_ler_lote(s_amostras, VIB_AMOSTRAS, &overrun) == ESP_OK) {
                tem_vib = vib_calcular(s_amostras, VIB_AMOSTRAS, VIB_AQUECIMENTO,
                                       adxl345_odr(), VIB_HP_HZ, &r);
            } else {
                ESP_LOGW(TAG, "falha ao ler o lote do FIFO");
            }
        }

        if (tem_vib && !overrun) {
            snprintf(json, sizeof(json),
                     "{\"device_id\":\"%s\",\"ts\":%lld,\"temperatura_c\":null,"
                     "\"vibracao\":{\"rms_g\":%.3f,\"pico_g\":%.3f,"
                     "\"crista\":%.2f,\"vel_mm_s\":%.2f,"
                     "\"eixo_x_g\":%.2f,\"eixo_y_g\":%.2f,\"eixo_z_g\":%.2f,"
                     "\"fs_hz\":%.1f},"
                     "\"rede\":{\"rssi_dbm\":%d,\"uptime_s\":%lld}}",
                     ixnode_id(), (long long)(up * 1000),
                     r.rms_g, r.pico_g, r.crista, r.vel_mm_s,
                     r.eixo_x_g, r.eixo_y_g, r.eixo_z_g, adxl345_odr(),
                     0, (long long)up);
        } else {
            // Sem vibracao confiavel, o campo sai AUSENTE -- nao zero e nao
            // null. O painel trata ausente como "nao medido" (e a razao de
            // valida_vel/valida_crista devolverem undefined); um zero seria
            // lido como maquina parada e saudavel, que e a mentira errada.
            if (overrun) {
                ESP_LOGW(TAG, "FIFO transbordou — lote descartado");
            }
            snprintf(json, sizeof(json),
                     "{\"device_id\":\"%s\",\"ts\":%lld,\"temperatura_c\":null,"
                     "\"rede\":{\"rssi_dbm\":%d,\"uptime_s\":%lld}}",
                     ixnode_id(), (long long)(up * 1000), 0, (long long)up);
        }

        esp_mqtt_client_publish(s_mqtt, s_topico, json, 0, 0, 0);

        if (tem_vib && (++n % 12 == 0)) {
            ESP_LOGI(TAG, "rms=%.3fg crista=%.2f vel=%.2fmm/s fs=%.0fHz",
                     r.rms_g, r.crista, r.vel_mm_s, adxl345_odr());
        }
    }
}
