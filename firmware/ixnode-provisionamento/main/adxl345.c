// =====================================================================
//  adxl345.c — ver adxl345.h para o porque do FIFO.
// =====================================================================
#include "adxl345.h"

#include <string.h>

#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "adxl345";

// --- Registradores ---------------------------------------------------
#define REG_DEVID        0x00
#define REG_INT_SOURCE   0x30
#define REG_DATA_FORMAT  0x31
#define REG_DATAX0       0x32
#define REG_BW_RATE      0x2C
#define REG_POWER_CTL    0x2D
#define REG_FIFO_CTL     0x38
#define REG_FIFO_STATUS  0x39

#define DEVID_ESPERADO   0xE5

#define POWER_MEASURE    0x08
// FULL_RES + faixa +-16 g. Com FULL_RES a escala e sempre 3,9 mg/LSB
// (256 LSB/g), independente da faixa -- muda so o quanto cabe antes de
// saturar. +-16 g da folga para impacto de rolamento sem cortar o pico,
// que e justamente o que o fator de crista mede.
#define FMT_FULLRES_16G  0x0B
#define LSB_POR_G        256.0f

// Stream: quando enche, descarta a MAIS ANTIGA e marca overrun. E o modo
// certo para amostragem continua -- o modo "FIFO" simples para de coletar
// quando enche, o que criaria um buraco silencioso na janela.
#define FIFO_STREAM      0x80

#define I2C_HZ           400000
#define TIMEOUT_MS       100

static i2c_master_bus_handle_t s_bus = NULL;
static i2c_master_dev_handle_t s_dev = NULL;
static float s_odr = 0.0f;

// ---------------------------------------------------------------------
static esp_err_t escrever(uint8_t reg, uint8_t valor)
{
    uint8_t b[2] = { reg, valor };
    return i2c_master_transmit(s_dev, b, sizeof(b), TIMEOUT_MS);
}

static esp_err_t ler(uint8_t reg, uint8_t *dest, size_t n)
{
    return i2c_master_transmit_receive(s_dev, &reg, 1, dest, n, TIMEOUT_MS);
}

// Codigo de taxa do registrador BW_RATE. A banda interna do anti-alias do
// proprio sensor e ODR/2 -- por isso a ODR nao e "quanto mais melhor": ela
// tem de ficar abaixo do dobro da taxa com que conseguimos DRENAR, senao
// sinal acima da metade rebate para dentro da banda util e vira pico
// fantasma, indistinguivel de defeito real.
static bool codigo_odr(int hz, uint8_t *cod, float *real)
{
    switch (hz) {
    case 3200: *cod = 0x0F; *real = 3200.0f; return true;
    case 1600: *cod = 0x0E; *real = 1600.0f; return true;
    case  800: *cod = 0x0D; *real =  800.0f; return true;
    case  400: *cod = 0x0C; *real =  400.0f; return true;
    case  200: *cod = 0x0B; *real =  200.0f; return true;
    case  100: *cod = 0x0A; *real =  100.0f; return true;
    default: return false;
    }
}

esp_err_t adxl345_iniciar(int pino_sda, int pino_scl, uint8_t endereco,
                          int odr_hz)
{
    uint8_t cod;
    float real;
    if (!codigo_odr(odr_hz, &cod, &real)) {
        ESP_LOGE(TAG, "ODR %d nao suportada", odr_hz);
        return ESP_ERR_INVALID_ARG;
    }

    i2c_master_bus_config_t bc = {
        .i2c_port = -1,                    // -1 = primeira porta livre
        .sda_io_num = pino_sda,
        .scl_io_num = pino_scl,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    esp_err_t e = i2c_new_master_bus(&bc, &s_bus);
    if (e != ESP_OK) { return e; }

    i2c_device_config_t dc = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = endereco,
        .scl_speed_hz = I2C_HZ,
    };
    e = i2c_master_bus_add_device(s_bus, &dc, &s_dev);
    if (e != ESP_OK) { return e; }

    uint8_t id = 0;
    e = ler(REG_DEVID, &id, 1);
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "sem resposta no endereco 0x%02X", endereco);
        return e;
    }
    if (id != DEVID_ESPERADO) {
        // Responde no endereco mas nao e um ADXL345. Falhar aqui e melhor
        // que publicar numero de um chip desconhecido.
        ESP_LOGE(TAG, "DEVID 0x%02X, esperado 0x%02X", id, DEVID_ESPERADO);
        return ESP_ERR_INVALID_RESPONSE;
    }

    // Ordem importa: parar a medicao antes de reconfigurar evita amostra
    // meio-velha meio-nova no FIFO.
    if ((e = escrever(REG_POWER_CTL, 0x00)) != ESP_OK) { return e; }
    if ((e = escrever(REG_DATA_FORMAT, FMT_FULLRES_16G)) != ESP_OK) { return e; }
    if ((e = escrever(REG_BW_RATE, cod)) != ESP_OK) { return e; }
    // Stream com watermark em 16: metade do FIFO. Nao usamos a interrupcao
    // de watermark (drenamos por polling), mas o campo tem de ser coerente.
    if ((e = escrever(REG_FIFO_CTL, FIFO_STREAM | 16)) != ESP_OK) { return e; }
    if ((e = escrever(REG_POWER_CTL, POWER_MEASURE)) != ESP_OK) { return e; }

    s_odr = real;
    ESP_LOGI(TAG, "ok — ODR %.0f Hz, banda util ate %.0f Hz, FIFO stream",
             s_odr, s_odr / 2.0f);
    return ESP_OK;
}

float adxl345_odr(void) { return s_odr; }

// Le UMA amostra do FIFO.
//
// O datasheet exige leitura multipla dos 6 bytes de uma vez (e o que faz o
// FIFO avancar) e um intervalo minimo de 5 us entre o fim de uma leitura e
// o inicio da proxima. Sem essa pausa o sensor devolve a mesma amostra
// repetida -- que nao parece erro nenhum: parece sinal de baixa frequencia.
static esp_err_t ler_amostra(vib_amostra_t *dest)
{
    uint8_t b[6];
    esp_err_t e = ler(REG_DATAX0, b, sizeof(b));
    if (e != ESP_OK) { return e; }

    const int16_t bx = (int16_t)((uint16_t)b[0] | ((uint16_t)b[1] << 8));
    const int16_t by = (int16_t)((uint16_t)b[2] | ((uint16_t)b[3] << 8));
    const int16_t bz = (int16_t)((uint16_t)b[4] | ((uint16_t)b[5] << 8));

    dest->x = (float)bx / LSB_POR_G;
    dest->y = (float)by / LSB_POR_G;
    dest->z = (float)bz / LSB_POR_G;

    esp_rom_delay_us(5);
    return ESP_OK;
}

esp_err_t adxl345_ler_lote(vib_amostra_t *dest, int n, bool *overrun)
{
    if (s_dev == NULL || dest == NULL || n <= 0) { return ESP_ERR_INVALID_ARG; }
    if (overrun != NULL) { *overrun = false; }

    // Limpa overrun pendente de antes deste lote: ler INT_SOURCE zera os
    // bits, entao o que sobrar dali para a frente e desta janela.
    uint8_t lixo;
    (void)ler(REG_INT_SOURCE, &lixo, 1);

    int obtidas = 0;
    int vazios = 0;

    while (obtidas < n) {
        uint8_t st = 0;
        esp_err_t e = ler(REG_FIFO_STATUS, &st, 1);
        if (e != ESP_OK) { return e; }

        int disponiveis = st & 0x3F;      // bits [5:0] = entradas no FIFO
        if (disponiveis > 32) { disponiveis = 32; }

        if (disponiveis == 0) {
            // Espera cerca de meio FIFO. Dormir menos so gasta barramento
            // perguntando; dormir muito mais arrisca o transbordo.
            if (++vazios > 200) {
                ESP_LOGE(TAG, "FIFO parado (%d/%d amostras)", obtidas, n);
                return ESP_ERR_TIMEOUT;
            }
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }
        vazios = 0;

        int levar = disponiveis;
        if (levar > n - obtidas) { levar = n - obtidas; }

        for (int i = 0; i < levar; i++) {
            e = ler_amostra(&dest[obtidas]);
            if (e != ESP_OK) { return e; }
            obtidas++;
        }

        // Overrun DEPOIS de drenar: se transbordou, o espacamento uniforme
        // quebrou e o lote inteiro perde a garantia que justifica o FIFO.
        uint8_t src = 0;
        if (ler(REG_INT_SOURCE, &src, 1) == ESP_OK) {
            if ((src & 0x01) && overrun != NULL) { *overrun = true; }
        }
    }

    return ESP_OK;
}
