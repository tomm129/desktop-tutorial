// =====================================================================
//  vibracao.h — RMS, fator de crista e velocidade ISO a partir de um lote
//               de amostras de aceleracao.
//
//  REGRA DESTE ARQUIVO: so <math.h> e <stdbool.h>. Nada de esp_*.h, nada
//  de FreeRTOS, nada de driver. E o que permite compilar esta matematica
//  no PC (ou em qualquer host) e testa-la contra a referencia em Python,
//  em vez de so conferir por leitura. Se precisar logar, devolva o valor
//  e deixe quem chamou logar.
// =====================================================================
#pragma once

#include <stdbool.h>

// Uma amostra ja convertida para g (a conversao de LSB e do driver).
typedef struct {
    float x, y, z;
} vib_amostra_t;

typedef struct {
    float rms_g;       // RMS AC combinado dos 3 eixos
    float pico_g;      // maior desvio AC absoluto (eixo mais excitado)
    float crista;      // fator de crista (pico/RMS) do eixo mais impulsivo
    float vel_mm_s;    // velocidade RMS combinada, mm/s (banda a partir de hp_hz)
    float eixo_x_g;    // componente DC por eixo = vetor da gravidade visto
    float eixo_y_g;    //   pelo sensor. Nao e vibracao, e ORIENTACAO: se
    float eixo_z_g;    //   mudar com a maquina parada, o sensor se soltou.
    int   n_validas;   // amostras que entraram na estatistica
} vib_resultado_t;

// Calcula tudo a partir de um lote ja amostrado.
//
// fs_hz e a taxa REAL do lote. Com o FIFO do ADXL345 ela e a ODR do
// sensor, cravada pelo oscilador dele -- nao uma media de micros(), que
// e o que a versao anterior tinha de usar e que trazia jitter de Wi-Fi
// para dentro do integrador.
//
// aquecimento = amostras iniciais que sao filtradas (o passa-alta precisa
// delas para assentar) mas nao entram nas estatisticas.
//
// Devolve false se o lote for pequeno demais para significar alguma coisa;
// nesse caso *out fica zerado.
bool vib_calcular(const vib_amostra_t *am, int n, int aquecimento,
                  float fs_hz, float hp_hz, vib_resultado_t *out);

// ---------------------------------------------------------------------
//  Auto-teste
//
//  Gera uma senoide de amplitude e frequencia conhecidas, passa pela
//  MESMA vib_calcular() do firmware e confere contra o valor analitico.
//  Existe porque nao ha compilador de host nesta maquina: sem isto, um
//  erro de digitacao no port da matematica so apareceria como numero
//  errado no painel, meses depois, indistinguivel de maquina ruim.
//
//  Devolve true se passou. Preenche erro_pct[] (3 posicoes: rms, crista,
//  velocidade) com o erro relativo de cada grandeza, para quem chamou
//  poder logar.
// ---------------------------------------------------------------------
// hp_hz e parametro, e nao constante interna, de proposito: o auto-teste
// tem de exercitar o MESMO corte que embarca. Fixo em 10 Hz, ele validava
// uma configuracao que o firmware nao usa mais (a producao esta em 5 Hz) --
// um teste verde sobre codigo que ninguem roda.
bool vib_autoteste(float fs_hz, float hp_hz, float erro_pct[3]);
