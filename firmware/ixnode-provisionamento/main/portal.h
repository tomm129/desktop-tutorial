#pragma once

#include "config_nvs.h"

// Portal cativo de provisionamento.
//
// Sobe o nó como ponto de acesso "iX-Node-a1b2c3", serve uma página com a
// lista de redes ao alcance e grava o que o usuário escolher.
//
// Bloqueia até o usuário salvar. Quem chama deve reiniciar em seguida — a
// pilha de Wi-Fi vai de AP para STA de forma muito mais previsível por um
// reboot do que por reconfiguração em tempo de execução, e o custo é 1 s.
//
// Devolve true se a configuração foi gravada.
bool ixnode_portal_executar(void);
