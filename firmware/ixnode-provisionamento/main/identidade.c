#include "identidade.h"

#include <stdio.h>
#include <string.h>

#include "esp_mac.h"

static char s_id[IXNODE_ID_MAX];
static char s_ssid[32];

// Lê o MAC uma vez e monta as duas strings. Chamada sob demanda em vez de
// num init explícito: assim nenhuma ordem de inicialização precisa ser
// lembrada, e ixnode_id() pode ser usado já no primeiro log.
static void montar(void)
{
    if (s_id[0] != '\0') {
        return;
    }

    uint8_t mac[6] = {0};
    // ESP_MAC_WIFI_STA e não o MAC "base": é o que aparece no roteador e no
    // que a etiqueta do invólucro vai citar. Usar outro faria o id impresso
    // divergir do que o administrador de rede vê.
    esp_read_mac(mac, ESP_MAC_WIFI_STA);

    snprintf(s_id, sizeof(s_id), "ixn-%02x%02x%02x", mac[3], mac[4], mac[5]);
    snprintf(s_ssid, sizeof(s_ssid), "iX-Node-%02x%02x%02x", mac[3], mac[4], mac[5]);
}

const char *ixnode_id(void)
{
    montar();
    return s_id;
}

const char *ixnode_ap_ssid(void)
{
    montar();
    return s_ssid;
}
