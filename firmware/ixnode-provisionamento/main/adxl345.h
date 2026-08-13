// =====================================================================
//  adxl345.h — leitura em RAJADA pelo FIFO do ADXL345.
//
//  A versao Arduino lia uma amostra por vez com getEvent() e uma pausa de
//  2 ms entre elas: ~370 amostras/s reais. Isso limitava a banda honesta a
//  ~185 Hz, abaixo dos 1000 Hz da ISO 20816 e -- pior -- abaixo dos 120 Hz
//  (2x a frequencia de linha), que e onde falha eletrica aparece como
//  vibracao mecanica.
//
//  Aqui o sensor amostra sozinho na ODR dele e empilha num FIFO de 32
//  amostras; o firmware so drena. Dois ganhos, e o segundo importa mais:
//
//   1. TAXA. ~1600 amostras/s, contra 370. Banda util ate 800 Hz.
//   2. REGULARIDADE. Quem cronometra passa a ser o oscilador do ADXL345,
//      nao o loop. Antes, o dt de cada amostra vinha de micros(), e uma
//      interrupcao de Wi-Fi alargava um dt no meio da janela -- o que
//      entra no integrador como degrau de velocidade e nao tem filtro
//      que desfaca. Agora dt = 1/ODR, exato.
// =====================================================================
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "esp_err.h"
#include "vibracao.h"

// Inicializa o barramento I2C e o sensor.
//
// odr_hz aceita 100, 200, 400, 800, 1600 ou 3200. Ver a nota sobre o teto
// pratico em adxl345.c antes de subir para 3200.
esp_err_t adxl345_iniciar(int pino_sda, int pino_scl, uint8_t endereco,
                          int odr_hz);

// Taxa efetivamente programada no sensor (Hz). E a que deve ir para
// vib_calcular() como fs_hz, e para o JSON como fs_hz.
float adxl345_odr(void);

// Drena o FIFO ate juntar n amostras, ja convertidas para g.
//
// *overrun vira true se o FIFO transbordou em algum momento do lote -- ou
// seja, se amostras foram perdidas e o espacamento uniforme QUEBROU. Nesse
// caso o resultado do calculo nao e confiavel e quem chamou deve descartar
// ou marcar. Deixar isso silencioso seria o pior dos mundos: o numero sai
// plausivel e errado.
//
// Devolve ESP_OK, ou ESP_ERR_TIMEOUT se o sensor parou de produzir.
esp_err_t adxl345_ler_lote(vib_amostra_t *dest, int n, bool *overrun);
