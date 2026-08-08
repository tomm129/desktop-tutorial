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

#include "config_nvs.h"
#include "identidade.h"
#include "portal.h"

static const char *TAG = "ixnode";

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

    // Batimento. Ainda sem sensor: o que se valida aqui e a cadeia
    // identidade -> rede -> broker -> painel. O ESP32 aparece na tela de
    // cadastro como dispositivo pendente, que e o teste de ponta a ponta.
    int n = 0;
    while (1) {
        vTaskDelay(pdMS_TO_TICKS(5000));
        if (!s_mqtt_ok) {
            continue;
        }
        char json[256];
        int64_t up = esp_timer_get_time() / 1000000;
        snprintf(json, sizeof(json),
                 "{\"device_id\":\"%s\",\"ts\":%lld,\"temperatura_c\":null,"
                 "\"rede\":{\"rssi_dbm\":%d,\"uptime_s\":%lld}}",
                 ixnode_id(), (long long)(up * 1000),
                 0, (long long)up);
        esp_mqtt_client_publish(s_mqtt, s_topico, json, 0, 0, 0);
        if (++n % 12 == 0) {
            ESP_LOGI(TAG, "%d batimentos publicados", n);
        }
    }
}
