#pragma once

#include <stdint.h>

#include "config_nvs.h"

// Portal cativo de provisionamento.
//
// Sobe o nó como ponto de acesso "iX-Node-a1b2c3", serve uma página com a
// lista de redes ao alcance e grava o que o usuário escolher.
//
// Quem chama deve reiniciar em seguida, qualquer que seja o resultado — a
// pilha de Wi-Fi vai de AP para STA de forma muito mais previsível por um
// reboot do que por reconfiguração em tempo de execução, e o custo é 1 s.

typedef enum {
    PORTAL_SALVO,            // configuração nova gravada
    PORTAL_TEMPO_ESGOTADO,   // ninguém configurou dentro de tempo_ms
    PORTAL_FALHOU,           // infraestrutura (o HTTP não subiu)
} ixnode_portal_res_t;

// atual:    configuração já gravada, ou NULL no nó virgem. Com ela o
//           formulário vem preenchido e avisa que a rede gravada não
//           respondeu; ela NUNCA é apagada por aqui.
// tempo_ms: 0 = espera indefinidamente (nó virgem).
ixnode_portal_res_t ixnode_portal_executar(const ixnode_config_t *atual, uint32_t tempo_ms);
