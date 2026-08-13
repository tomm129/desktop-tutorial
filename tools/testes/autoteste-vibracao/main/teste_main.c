// =====================================================================
//  Testa a vibracao.c REAL do firmware, executando-a.
//
//  Por que existe: tools/testes/testa_vibracao.py reimplementa a
//  matematica em Python. Isso valida o ALGORITMO, nao o codigo C que vai
//  para o campo -- um coeficiente trocado no port passaria pelos 12/12 do
//  Python e sairia como numero errado no painel.
//
//  Nao ha compilador de host nesta maquina (o esp-clang do Espressif so
//  tem alvo riscv32), entao a saida e rodar no emulador:
//
//      idf.py set-target esp32c3
//      idf.py build
//      idf.py qemu monitor
//
//  O alvo e esp32c3 porque e o que o QEMU do IDF emula. A matematica nao
//  tem nada de especifico de chip -- e o mesmo objeto que roda no C6.
// =====================================================================
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "vibracao.h"

#define FS        1600.0f
#define N         1600          // 1,0 s
#define AQUEC      400          // 0,25 s
#define G_MS2     9.80665f

static vib_amostra_t buf[N];
static int falhas = 0;

static void chk(const char *nome, float obtido, float esperado, float tol_pct)
{
    const float err = (esperado != 0.0f)
                      ? (obtido - esperado) / esperado * 100.0f
                      : (obtido - esperado);
    const bool ok = fabsf(err) <= tol_pct;
    if (!ok) { falhas++; }
    printf("  %-42s %10.4f  esp %10.4f  %+7.2f%%  %s\n",
           nome, obtido, esperado, err, ok ? "ok" : "FALHOU");
}

// Preenche o buffer com uma senoide de amplitude de pico amp_g na
// frequencia f, distribuida pelos eixos conforme os pesos, mais 1 g de
// gravidade no Z.
static void gerar(float amp_g, float f, float wx, float wy, float wz)
{
    for (int i = 0; i < N; i++) {
        const float t = (float)i / FS;
        const float s = amp_g * sinf(2.0f * (float)M_PI * f * t);
        buf[i].x = s * wx;
        buf[i].y = s * wy;
        buf[i].z = s * wz + 1.0f;      // 1 g estatico
    }
}

static float vel_analitica(float amp_g, float f)
{
    // v_rms = (a_pico / omega) / raiz(2), em m/s -> mm/s
    return (amp_g * G_MS2) / (2.0f * (float)M_PI * f) / 1.41421356f * 1000.0f;
}

void app_main(void)
{
    vib_resultado_t r;

    printf("\n===== auto-teste da vibracao.c (fs = %.0f Hz) =====\n\n", FS);

    // -- 1. O auto-teste embutido no proprio firmware ------------------
    printf("[1] vib_autoteste() embutido\n");
    {
        float e[3];
        const bool ok = vib_autoteste(FS, 5.0f, e);
        if (!ok) { falhas++; }
        printf("  rms %+.2f%%  crista %+.2f%%  vel %+.2f%%   %s\n\n",
               e[0], e[1], e[2], ok ? "ok" : "FALHOU");
    }

    // -- 2. Velocidade por frequencia ---------------------------------
    // O ponto sensivel do algoritmo. Foi aqui que a cascata de tres
    // passa-altas de 1a ordem errava 33%, e onde o trapezio errava 25%.
    printf("[2] velocidade vs analitico (senoide 0,1 g no X)\n");
    const float freqs[] = { 25.0f, 50.0f, 100.0f, 200.0f, 400.0f };
    for (unsigned k = 0; k < sizeof(freqs) / sizeof(freqs[0]); k++) {
        const float f = freqs[k];
        gerar(0.1f, f, 1.0f, 0.0f, 0.0f);
        vib_calcular(buf, N, AQUEC, FS, 10.0f, &r);
        char nome[48];
        snprintf(nome, sizeof(nome), "vel_mm_s @ %.0f Hz", f);
        chk(nome, r.vel_mm_s, vel_analitica(0.1f, f), 3.0f);
    }
    printf("\n");

    // -- 2b. Resposta na BASE da banda ISO ----------------------------
    // Nao e assercao, e medicao: quanto a cadeia de dois passa-altas
    // atenua perto do proprio corte. A ISO 20816-3 comeca em 10 Hz, e um
    // motor de 4 polos a 900 rpm tem o 1x justamente em 15 Hz -- ou seja,
    // a regiao mais atenuada da cadeia e uma regiao com maquina real
    // dentro. Medir os dois cortes deixa a escolha baseada em numero.
    printf("[2b] atenuacao na base da banda (informativo, sem assercao)\n");
    printf("     %-8s %12s %12s\n", "f (Hz)", "corte 10 Hz", "corte 5 Hz");
    const float baixas[] = { 10.0f, 12.0f, 15.0f, 20.0f, 25.0f, 30.0f };
    for (unsigned k = 0; k < sizeof(baixas) / sizeof(baixas[0]); k++) {
        const float f = baixas[k];
        const float esp = vel_analitica(0.1f, f);

        gerar(0.1f, f, 1.0f, 0.0f, 0.0f);
        vib_calcular(buf, N, AQUEC, FS, 10.0f, &r);
        const float e10 = (r.vel_mm_s - esp) / esp * 100.0f;

        gerar(0.1f, f, 1.0f, 0.0f, 0.0f);
        vib_calcular(buf, N, AQUEC, FS, 5.0f, &r);
        const float e5 = (r.vel_mm_s - esp) / esp * 100.0f;

        printf("     %-8.0f %11.1f%% %11.1f%%\n", f, e10, e5);
    }
    printf("\n");

    // -- 2c. Custo de baixar o corte: tempo de assentamento -----------
    // Um passa-alta de 5 Hz assenta na metade da velocidade de um de
    // 10 Hz. Se o aquecimento nao cobrir isso, o transitorio do filtro
    // entra nas estatisticas e o numero sai errado -- trocar-se-ia um
    // erro conhecido (-50% em 10 Hz) por outro pior e mais dificil de
    // ver. Aqui se mede quanto aquecimento cada corte exige.
    printf("[2c] assentamento vs aquecimento (senoide 30 Hz, 0,1 g)\n");
    printf("     %-12s %12s %12s\n", "aquec (amostras)", "corte 10 Hz", "corte 5 Hz");
    const int aquecs[] = { 200, 400, 800, 1200 };
    for (unsigned k = 0; k < sizeof(aquecs) / sizeof(aquecs[0]); k++) {
        const int aq = aquecs[k];
        const float esp = vel_analitica(0.1f, 30.0f);

        gerar(0.1f, 30.0f, 1.0f, 0.0f, 0.0f);
        vib_calcular(buf, N, aq, FS, 10.0f, &r);
        const float e10 = (r.vel_mm_s - esp) / esp * 100.0f;

        gerar(0.1f, 30.0f, 1.0f, 0.0f, 0.0f);
        vib_calcular(buf, N, aq, FS, 5.0f, &r);
        const float e5 = (r.vel_mm_s - esp) / esp * 100.0f;

        printf("     %-12d %11.1f%% %11.1f%%\n", aq, e10, e5);
    }
    // E a rejeicao de DC continua valendo com o corte mais baixo?
    for (int i = 0; i < N; i++) { buf[i].x = 0.0f; buf[i].y = 0.0f; buf[i].z = 1.0f; }
    vib_calcular(buf, N, AQUEC, FS, 5.0f, &r);
    printf("     DC com corte 5 Hz: rms %.6f g, vel %.6f mm/s\n\n",
           r.rms_g, r.vel_mm_s);

    // -- 3. RMS e crista de senoide pura ------------------------------
    printf("[3] RMS e fator de crista (senoide pura = raiz(2))\n");
    gerar(0.1f, 50.0f, 1.0f, 0.0f, 0.0f);
    vib_calcular(buf, N, AQUEC, FS, 10.0f, &r);
    chk("rms_g", r.rms_g, 0.1f / 1.41421356f, 1.0f);
    chk("crista", r.crista, 1.41421356f, 2.0f);
    printf("\n");

    // -- 4. Rejeicao de DC --------------------------------------------
    // So gravidade, maquina parada. Se o DC vazasse para o AC, o RMS
    // viria perto de 1 g e todo motor parado apareceria como critico.
    printf("[4] rejeicao de DC (so 1 g de gravidade, sem vibracao)\n");
    for (int i = 0; i < N; i++) { buf[i].x = 0.0f; buf[i].y = 0.0f; buf[i].z = 1.0f; }
    vib_calcular(buf, N, AQUEC, FS, 10.0f, &r);
    chk("rms_g (deve ser ~0)", r.rms_g, 0.0f, 1e-4f);
    chk("vel_mm_s (deve ser ~0)", r.vel_mm_s, 0.0f, 1e-3f);
    chk("eixo_z_g (orientacao preservada)", r.eixo_z_g, 1.0f, 0.1f);
    printf("\n");

    // -- 5. Invariancia a orientacao de montagem ----------------------
    // A justificativa de somar variancias dos tres eixos e que o
    // resultado nao pode depender de como o sensor foi parafusado. Mesma
    // energia, repartida de tres jeitos, tem de dar o mesmo numero.
    printf("[5] invariancia a orientacao (mesma energia, eixos diferentes)\n");
    gerar(0.1f, 50.0f, 1.0f, 0.0f, 0.0f);
    vib_calcular(buf, N, AQUEC, FS, 10.0f, &r);
    const float ref_rms = r.rms_g;
    const float ref_vel = r.vel_mm_s;

    gerar(0.1f, 50.0f, 0.0f, 1.0f, 0.0f);
    vib_calcular(buf, N, AQUEC, FS, 10.0f, &r);
    chk("rms so no Y == so no X", r.rms_g, ref_rms, 0.5f);

    const float w = 1.0f / 1.73205081f;     // 1/raiz(3) em cada eixo
    gerar(0.1f, 50.0f, w, w, w);
    vib_calcular(buf, N, AQUEC, FS, 10.0f, &r);
    chk("rms repartido nos 3 == so no X", r.rms_g, ref_rms, 0.5f);
    chk("vel repartida nos 3 == so no X", r.vel_mm_s, ref_vel, 0.5f);
    printf("\n");

    // -- 6. Guardas de entrada ----------------------------------------
    printf("[6] guardas de entrada\n");
    {
        bool ok = true;
        if (vib_calcular(NULL, N, AQUEC, FS, 10.0f, &r))  { ok = false; }
        if (vib_calcular(buf, 1, 0, FS, 10.0f, &r))       { ok = false; }
        if (vib_calcular(buf, N, AQUEC, 0.0f, 10.0f, &r)) { ok = false; }
        if (vib_calcular(buf, N, AQUEC, FS, 10.0f, NULL)) { ok = false; }
        if (!ok) { falhas++; }
        printf("  entradas invalidas rejeitadas: %s\n\n", ok ? "ok" : "FALHOU");
    }

    printf("=====================================================\n");
    if (falhas == 0) {
        printf("RESULTADO: PASSOU (0 falhas)\n");
    } else {
        printf("RESULTADO: FALHOU (%d)\n", falhas);
    }
    printf("=====================================================\n");

    // QEMU nao encerra sozinho; quem roda usa timeout e le a saida.
    // vTaskDelay e nao busy-loop: senao a task IDLE nunca roda e o
    // watchdog dispara, enchendo a saida de backtrace por cima do
    // resultado.
    while (1) { vTaskDelay(pdMS_TO_TICKS(1000)); }
}
