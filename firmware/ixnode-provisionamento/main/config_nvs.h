#pragma once

#include <stdbool.h>
#include <stddef.h>

// Configuração persistida na NVS.
//
// Wi-Fi e broker NÃO ficam em config.h de propósito. Trocar de rede ou de IP
// do gateway não pode exigir recompilar: numa planta com vinte nós isso
// significaria vinte regravações, e em campo raramente há um PC por perto.

typedef struct {
    char ssid[33];        // 32 + terminador (limite do 802.11)
    char senha[65];       // 64 + terminador (WPA2-PSK)
    char mqtt_host[64];   // IP ou nome do gateway
    int  mqtt_porta;
} ixnode_config_t;

// Carrega da NVS. Devolve false se ainda não há nada gravado — que é o sinal
// de "nó virgem, entra em modo portal".
bool ixnode_config_carregar(ixnode_config_t *cfg);

// Grava e devolve false em qualquer erro de NVS. O chamador NÃO deve
// reiniciar se isto falhar: reiniciar sem ter gravado joga o usuário de volta
// ao portal sem explicação, e ele repete tudo achando que digitou errado.
bool ixnode_config_gravar(const ixnode_config_t *cfg);

// Apaga a configuração — o nó volta a subir em modo portal no próximo boot.
bool ixnode_config_apagar(void);
