// =====================================================================
//  led_ident.h — "qual desses nos e o que estou vendo na tela?"
//
//  Numa planta com dezenas de nos identicos parafusados em motores
//  identicos, casar a linha do painel com o modulo fisico e um problema
//  real: hoje se faz conferindo o MAC com lanterna, deitado embaixo da
//  maquina. O painel manda {"comando":"identificar"} e o no pisca por
//  alguns segundos.
//
//  Dois tipos de LED, escolhidos em tempo de compilacao:
//    IDENT_TIPO 1 = GPIO comum (placa de producao)
//    IDENT_TIPO 2 = WS2812 endereçavel (C6-DevKitC-1, GPIO8) [padrao]
// =====================================================================
#pragma once

#include <stdbool.h>

#include "esp_err.h"

#define IDENT_TIPO   2
#define IDENT_PINO   8      // GPIO8 no C6-DevKitC-1

esp_err_t led_ident_iniciar(void);

// Pisca por 'segundos'. Nao bloqueia: sobe uma task que pisca e sai, para
// o comando nao segurar o laco de telemetria. Chamar de novo enquanto ja
// pisca apenas reinicia a contagem.
void led_ident_piscar(int segundos);
