#include "config_nvs.h"

#include <string.h>

#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "config";

// Namespace próprio: separa a nossa configuração da que o driver de Wi-Fi do
// IDF guarda por conta dele, e permite apagar só a nossa.
#define NS "ixnode"

bool ixnode_config_carregar(ixnode_config_t *cfg)
{
    memset(cfg, 0, sizeof(*cfg));
    cfg->mqtt_porta = 1883;

    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READONLY, &h);
    if (err != ESP_OK) {
        // ESP_ERR_NVS_NOT_FOUND aqui é o caso NORMAL do nó virgem, não uma
        // falha: o namespace só passa a existir na primeira gravação.
        ESP_LOGI(TAG, "sem configuracao gravada (%s)", esp_err_to_name(err));
        return false;
    }

    size_t n = sizeof(cfg->ssid);
    err = nvs_get_str(h, "ssid", cfg->ssid, &n);
    if (err != ESP_OK || cfg->ssid[0] == '\0') {
        ESP_LOGI(TAG, "sem SSID gravado");
        nvs_close(h);
        return false;
    }

    n = sizeof(cfg->senha);
    // Rede aberta é legítima: senha ausente não invalida a configuração.
    if (nvs_get_str(h, "senha", cfg->senha, &n) != ESP_OK) {
        cfg->senha[0] = '\0';
    }

    n = sizeof(cfg->mqtt_host);
    if (nvs_get_str(h, "mqtt_host", cfg->mqtt_host, &n) != ESP_OK) {
        cfg->mqtt_host[0] = '\0';
    }

    int32_t porta = 0;
    if (nvs_get_i32(h, "mqtt_porta", &porta) == ESP_OK && porta > 0 && porta < 65536) {
        cfg->mqtt_porta = (int)porta;
    }

    nvs_close(h);
    ESP_LOGI(TAG, "configuracao carregada: SSID '%s', broker %s:%d",
             cfg->ssid, cfg->mqtt_host, cfg->mqtt_porta);
    return true;
}

bool ixnode_config_gravar(const ixnode_config_t *cfg)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open falhou: %s", esp_err_to_name(err));
        return false;
    }

    bool ok = true;
    ok = ok && nvs_set_str(h, "ssid", cfg->ssid) == ESP_OK;
    ok = ok && nvs_set_str(h, "senha", cfg->senha) == ESP_OK;
    ok = ok && nvs_set_str(h, "mqtt_host", cfg->mqtt_host) == ESP_OK;
    ok = ok && nvs_set_i32(h, "mqtt_porta", cfg->mqtt_porta) == ESP_OK;

    // O commit é o que realmente escreve na flash. Sem ele os set_* ficam só
    // no cache e um reboot perde tudo -- com a agravante de que o portal já
    // teria dito "salvo" ao usuário.
    if (ok) {
        err = nvs_commit(h);
        ok = (err == ESP_OK);
        if (!ok) {
            ESP_LOGE(TAG, "nvs_commit falhou: %s", esp_err_to_name(err));
        }
    }

    nvs_close(h);
    if (ok) {
        ESP_LOGI(TAG, "configuracao gravada: SSID '%s', broker %s:%d",
                 cfg->ssid, cfg->mqtt_host, cfg->mqtt_porta);
    }
    return ok;
}

bool ixnode_config_apagar(void)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READWRITE, &h) != ESP_OK) {
        return false;
    }
    esp_err_t err = nvs_erase_all(h);
    if (err == ESP_OK) {
        err = nvs_commit(h);
    }
    nvs_close(h);
    ESP_LOGW(TAG, "configuracao apagada (%s)", esp_err_to_name(err));
    return err == ESP_OK;
}
