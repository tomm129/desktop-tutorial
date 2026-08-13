// =====================================================================
//  led_ident.c — ver led_ident.h.
// =====================================================================
#include "led_ident.h"

#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#if IDENT_TIPO == 2
#include "led_strip.h"
#else
#include "driver/gpio.h"
#endif

static const char *TAG = "ident";

#define PERIODO_MS   250        // 2 piscadas por segundo: visivel de longe
                                // sem parecer defeito de contato.

// O prazo e guardado em MILISSEGUNDOS num int32, nao em microssegundos num
// int64. Motivo: este e um RISC-V de 32 bits, onde ler ou escrever 64 bits
// sao DUAS instrucoes -- `volatile` impede o compilador de guardar o valor
// em registrador, mas nao torna o acesso atomico. Com a task lendo enquanto
// a task do MQTT escreve, dava para ler a palavra baixa nova junto com a
// alta velha e obter um prazo lixo: ou o LED parava na hora, ou ficava
// aceso por horas. Em ms num int32 o acesso e uma instrucao so.
static volatile int32_t s_ate_ms = 0;
static volatile bool s_rodando = false;

// Protege a decisao "ainda preciso piscar?" contra a decisao "posso
// desistir?" -- ver a corrida documentada em led_ident_piscar().
static portMUX_TYPE s_mux = portMUX_INITIALIZER_UNLOCKED;

#if IDENT_TIPO == 2
static led_strip_handle_t s_tira = NULL;
#endif

static inline int32_t agora_ms(void)
{
    return (int32_t)(esp_timer_get_time() / 1000);
}

static void acender(bool ligado)
{
#if IDENT_TIPO == 2
    if (s_tira == NULL) { return; }
    if (ligado) {
        // Ciano: nenhum dos estados do painel usa essa cor (normal/atencao/
        // critico sao verde/ambar/vermelho), entao piscada de identificacao
        // nunca e confundida com alarme por quem esta na maquina.
        led_strip_set_pixel(s_tira, 0, 0, 40, 40);
    } else {
        led_strip_clear(s_tira);
    }
    led_strip_refresh(s_tira);
#else
    gpio_set_level(IDENT_PINO, ligado ? 1 : 0);
#endif
}

static void tarefa(void *arg)
{
    (void)arg;
    bool ligado = false;

    while (1) {
        bool sair = false;

        // A decisao de desistir e a baixa de s_rodando acontecem JUNTAS,
        // dentro da secao critica. E isso que fecha a corrida: quem chama
        // piscar() so ve s_rodando=false depois que esta task ja desistiu
        // de verdade -- nunca no meio do caminho.
        //
        // Subtracao com sinal, e nao comparacao direta: sobrevive a volta
        // do contador de 32 bits (a cada ~24 dias de uptime).
        portENTER_CRITICAL(&s_mux);
        if ((int32_t)(agora_ms() - s_ate_ms) >= 0) {
            s_rodando = false;
            sair = true;
        }
        portEXIT_CRITICAL(&s_mux);

        if (sair) { break; }

        ligado = !ligado;
        acender(ligado);
        vTaskDelay(pdMS_TO_TICKS(PERIODO_MS));
    }

    acender(false);
    ESP_LOGI(TAG, "identificacao encerrada");
    vTaskDelete(NULL);
}

esp_err_t led_ident_iniciar(void)
{
#if IDENT_TIPO == 2
    led_strip_config_t cfg = {
        .strip_gpio_num = IDENT_PINO,
        .max_leds = 1,
    };
    led_strip_rmt_config_t rmt = {
        .resolution_hz = 10 * 1000 * 1000,
    };
    esp_err_t e = led_strip_new_rmt_device(&cfg, &rmt, &s_tira);
    if (e != ESP_OK) {
        ESP_LOGW(TAG, "LED WS2812 indisponivel (%s)", esp_err_to_name(e));
        return e;
    }
    led_strip_clear(s_tira);
#else
    gpio_config_t c = {
        .pin_bit_mask = 1ULL << IDENT_PINO,
        .mode = GPIO_MODE_OUTPUT,
    };
    esp_err_t e = gpio_config(&c);
    if (e != ESP_OK) { return e; }
    gpio_set_level(IDENT_PINO, 0);
#endif
    ESP_LOGI(TAG, "LED de identificacao no GPIO%d", IDENT_PINO);
    return ESP_OK;
}

void led_ident_piscar(int segundos)
{
    if (segundos <= 0)   { segundos = 10; }
    if (segundos > 120)  { segundos = 120; }   // nao deixar piscando para
                                               // sempre por comando perdido

    // A versao anterior tinha uma corrida silenciosa aqui: escrevia o prazo
    // novo, via a task ainda viva e voltava achando que tinha estendido --
    // mas se a task JA tinha avaliado o prazo antigo e estava a caminho de
    // morrer, ela morria mesmo assim. O comando de identificar sumia sem
    // deixar rastro, e o LED nao piscava. Prazo e decisao agora saem da
    // mesma secao critica, entao "vi a task viva" passa a significar "a
    // task ainda vai ler o prazo novo".
    bool criar;
    portENTER_CRITICAL(&s_mux);
    s_ate_ms = agora_ms() + segundos * 1000;
    criar = !s_rodando;
    if (criar) { s_rodando = true; }
    portEXIT_CRITICAL(&s_mux);

    if (!criar) {
        ESP_LOGI(TAG, "identificacao estendida para %ds", segundos);
        return;
    }

    ESP_LOGI(TAG, "identificando por %ds", segundos);
    if (xTaskCreate(tarefa, "ident", 2560, NULL, 4, NULL) != pdPASS) {
        ESP_LOGW(TAG, "sem memoria para a task de identificacao");
        portENTER_CRITICAL(&s_mux);
        s_rodando = false;
        portEXIT_CRITICAL(&s_mux);
    }
}
