// =====================================================================
//  vibracao.c — ver vibracao.h para a regra de dependencia deste arquivo.
//
//  Portado do firmware Arduino (firmware/esp32-campo/src/main.cpp), que
//  ja foi validado em bancada. As decisoes de algoritmo abaixo NAO sao
//  reabertas aqui: cada uma custou uma rodada de teste numerico e esta
//  documentada com o numero que a justifica.
//
//  A diferenca de fundo em relacao a versao Arduino nao e a velocidade de
//  amostragem -- e a REGULARIDADE. La, o dt de cada amostra vinha de
//  micros(), e uma interrupcao de Wi-Fi no meio da janela alargava um dt
//  arbitrariamente. Um dt errado entra no integrador como um degrau de
//  velocidade, e nenhum filtro depois disso desfaz. Com o FIFO, quem
//  cronometra e o oscilador do ADXL345: as amostras saem espacadas de
//  1/ODR exatos, e o dt vira constante conhecida.
// =====================================================================
#include "vibracao.h"

#include <math.h>
#include <string.h>

#define G_MS2   9.80665f

// ---------------------------------------------------------------------
//  Passa-alta Butterworth de 2a ordem (biquad, forma RBJ, Q = 1/raiz(2)).
//
//  Por que Butterworth e nao cascata de 1a ordem: um passa-alta de 1a
//  ordem em 10 Hz ainda atenua 12% em 30 Hz, e a cadeia precisa de
//  varios. Medido em simulacao: tres de 1a ordem derrubavam a velocidade
//  em 33% a 30 Hz -- o suficiente para o numero nao poder mais ser
//  comparado com a faixa da ISO. Dois Butterworth custam 1,4% no mesmo
//  ponto.
// ---------------------------------------------------------------------
typedef struct {
    float b0, b1, b2, a1, a2;
    float x1, x2, y1, y2;
    bool  iniciado;
} biquad_t;

static void biquad_hp(biquad_t *f, float fc_hz, float fs_hz)
{
    const float w0    = 2.0f * (float)M_PI * fc_hz / fs_hz;
    const float alpha = sinf(w0) / (2.0f * 0.70710678f);   // Q = 1/raiz(2)
    const float cw    = cosf(w0);
    const float a0    = 1.0f + alpha;

    f->b0 = ((1.0f + cw) * 0.5f) / a0;
    f->b1 = (-(1.0f + cw)) / a0;
    f->b2 = f->b0;
    f->a1 = (-2.0f * cw) / a0;
    f->a2 = (1.0f - alpha) / a0;

    f->x1 = f->x2 = f->y1 = f->y2 = 0.0f;
    f->iniciado = false;
}

static float biquad(biquad_t *f, float x)
{
    if (!f->iniciado) {
        // Assenta a entrada no valor atual em vez de em zero: senao a
        // primeira amostra entra como degrau, e degrau em passa-alta
        // produz transitorio que leva varios ciclos para dissipar.
        f->iniciado = true;
        f->x1 = f->x2 = x;
    }
    const float y = f->b0 * x + f->b1 * f->x1 + f->b2 * f->x2
                              - f->a1 * f->y1 - f->a2 * f->y2;
    f->x2 = f->x1;  f->x1 = x;
    f->y2 = f->y1;  f->y1 = y;
    return y;
}

// Regra de integracao v[n] = v[n-1] + dt*(C0*a[n] + C1*a[n-1]).
//
// Nao e trapezio (1/2, 1/2). O trapezio e a escolha reflexa, mas seu
// ganho discreto ERRA para baixo e cresce com a frequencia: a 370 Hz de
// amostragem perdia 8% em 60 Hz e 25% em 100 Hz. O retangulo (1, 0) erra
// para cima, com metade da magnitude. A mistura abaixo cancela quase
// todo o termo de 2a ordem dos dois:
//
//   erro maximo ate 100 Hz  .  trapezio 25,3%  .  esta mistura 1,8%
//
// Verificado por varredura de fs entre 250 e 600 Hz. A 1600 Hz (a taxa
// do FIFO) a razao f/fs cai por um fator ~4, e o erro cai com o
// quadrado dela -- ou seja, aqui a mistura fica ainda melhor do que era.
// A soma C0+C1 tem de ser 1, senao a escala de DC sai errada.
static const float INT_C0 = 0.875f;
static const float INT_C1 = 0.125f;

// Canal de integracao aceleracao -> velocidade, por eixo.
//
// A cadeia e passa-alta -> integra -> passa-alta, e cada estagio existe
// por um motivo:
//   1. O passa-alta ANTES tira o residuo de DC. Integrar um offset
//      constante produz rampa sem limite, e a velocidade viraria funcao
//      do tempo de janela, nao da vibracao.
//   2. O passa-alta DEPOIS cancela o ganho de +20 dB/decada que a
//      integracao da as baixas frequencias. Sendo de 2a ordem
//      (-40 dB/decada), vence esse ganho com folga e mata a deriva.
typedef struct {
    biquad_t hp_acel, hp_vel;
    float    acel_ant;   // aceleracao ja filtrada da amostra anterior
    float    vel;        // estado do integrador, m/s
    bool     tem_ant;
} canal_t;

static void canal_iniciar(canal_t *c, float hp_hz, float fs_hz)
{
    biquad_hp(&c->hp_acel, hp_hz, fs_hz);
    biquad_hp(&c->hp_vel,  hp_hz, fs_hz);
    c->acel_ant = 0.0f;
    c->vel      = 0.0f;
    c->tem_ant  = false;
}

// Recebe aceleracao em m/s2, devolve velocidade filtrada em mm/s.
static float canal_integrar(canal_t *c, float acel_ms2, float dt_s)
{
    const float a = biquad(&c->hp_acel, acel_ms2);

    if (!c->tem_ant) { c->acel_ant = a; c->tem_ant = true; }
    c->vel += dt_s * (INT_C0 * a + INT_C1 * c->acel_ant);
    c->acel_ant = a;

    return biquad(&c->hp_vel, c->vel) * 1000.0f;   // m/s -> mm/s
}

// ---------------------------------------------------------------------
bool vib_calcular(const vib_amostra_t *am, int n, int aquecimento,
                  float fs_hz, float hp_hz, vib_resultado_t *out)
{
    if (out == NULL) { return false; }
    memset(out, 0, sizeof(*out));

    if (am == NULL || n < 2 || !(fs_hz > 1.0f) || !isfinite(fs_hz)) {
        return false;
    }
    if (aquecimento < 0)        { aquecimento = 0; }
    if (aquecimento > n - 2)    { aquecimento = n - 2; }

    const float dt_s = 1.0f / fs_hz;

    // Referencia para "variancia deslocada": as somas ficam perto de zero
    // e evitam o cancelamento catastrofico de E[x2]-E[x]2 em float -- o
    // sinal AC e tipicamente 100 a 1000x menor que o 1 g estatico. A
    // variancia nao muda ao subtrair uma constante; so a media precisa
    // soma-la de volta no fim.
    const float rx = am[0].x, ry = am[0].y, rz = am[0].z;

    float sx = 0.0f, sy = 0.0f, sz = 0.0f;
    float sxx = 0.0f, syy = 0.0f, szz = 0.0f;
    // Inicia em +-infinito para que o primeiro valor real vença a
    // comparacao -- iniciar em 0 embutiria um zero que pode nao
    // pertencer a janela.
    float minx = INFINITY, maxx = -INFINITY;
    float miny = INFINITY, maxy = -INFINITY;
    float minz = INFINITY, maxz = -INFINITY;

    canal_t cvx, cvy, cvz;
    canal_iniciar(&cvx, hp_hz, fs_hz);
    canal_iniciar(&cvy, hp_hz, fs_hz);
    canal_iniciar(&cvz, hp_hz, fs_hz);

    float svx = 0.0f, svy = 0.0f, svz = 0.0f;
    float svxx = 0.0f, svyy = 0.0f, svzz = 0.0f;

    int n_val = 0;

    for (int i = 0; i < n; i++) {
        const float x = am[i].x - rx;
        const float y = am[i].y - ry;
        const float z = am[i].z - rz;

        // A integracao usa m/s2 (unidade fisica), nao g -- o resultado
        // sai em m/s e vira mm/s dentro de canal_integrar().
        const float vx_mm = canal_integrar(&cvx, x * G_MS2, dt_s);
        const float vy_mm = canal_integrar(&cvy, y * G_MS2, dt_s);
        const float vz_mm = canal_integrar(&cvz, z * G_MS2, dt_s);

        // As primeiras amostras sao filtradas (o filtro precisa delas
        // para assentar) mas nao contam nas estatisticas.
        if (i < aquecimento) { continue; }

        sx += x;  sy += y;  sz += z;
        sxx += x * x;  syy += y * y;  szz += z * z;

        if (x < minx) { minx = x; }
        if (x > maxx) { maxx = x; }
        if (y < miny) { miny = y; }
        if (y > maxy) { maxy = y; }
        if (z < minz) { minz = z; }
        if (z > maxz) { maxz = z; }

        svx += vx_mm;  svy += vy_mm;  svz += vz_mm;
        svxx += vx_mm * vx_mm;  svyy += vy_mm * vy_mm;  svzz += vz_mm * vz_mm;
        n_val++;
    }

    if (n_val < 2) { return false; }
    const float N = (float)n_val;

    const float mx = sx / N, my = sy / N, mz = sz / N;

    // Variancia = potencia AC de cada eixo. Clamp em 0: arredondamento
    // pode produzir um negativo minusculo com o eixo praticamente parado.
    float vx = sxx / N - mx * mx;   if (vx < 0.0f) { vx = 0.0f; }
    float vy = syy / N - my * my;   if (vy < 0.0f) { vy = 0.0f; }
    float vz = szz / N - mz * mz;   if (vz < 0.0f) { vz = 0.0f; }

    // Pico AC exato por eixo (maior afastamento da propria media).
    const float px = fmaxf(maxx - mx, mx - minx);
    const float py = fmaxf(maxy - my, my - miny);
    const float pz = fmaxf(maxz - mz, mz - minz);

    // ---- Fator de crista ------------------------------------------
    // pico/RMS, POR EIXO, reportando o maior. Tem de ser por eixo: o RMS
    // combinado dos tres e maior que o de qualquer um deles, entao
    // dividir o pico de um unico eixo pelo RMS combinado subestima a
    // crista justamente quando ela importa -- no eixo isolado onde o
    // rolamento esta batendo.
    //
    // Leitura: senoide pura = 1,41; maquina sadia = 3 a 4; defeito
    // incipiente de rolamento sobe para 5 a 8. Em estagio avancado ela
    // CAI de novo, porque os impactos viram ruido continuo e o RMS
    // alcanca o pico -- por isso crista sozinha nao serve de alarme, e
    // sim junto do RMS.
    const float PISO = 1e-4f;
    const float cx = (vx > PISO * PISO) ? px / sqrtf(vx) : 0.0f;
    const float cy = (vy > PISO * PISO) ? py / sqrtf(vy) : 0.0f;
    const float cz = (vz > PISO * PISO) ? pz / sqrtf(vz) : 0.0f;

    // ---- Velocidade RMS -------------------------------------------
    // Mesma logica de somar variancias dos tres eixos usada na
    // aceleracao: o resultado fica invariante a orientacao de montagem.
    const float mvx = svx / N, mvy = svy / N, mvz = svz / N;
    float wx = svxx / N - mvx * mvx;   if (wx < 0.0f) { wx = 0.0f; }
    float wy = svyy / N - mvy * mvy;   if (wy < 0.0f) { wy = 0.0f; }
    float wz = svzz / N - mvz * mvz;   if (wz < 0.0f) { wz = 0.0f; }

    out->rms_g    = sqrtf(vx + vy + vz);
    out->pico_g   = fmaxf(px, fmaxf(py, pz));
    out->crista   = fmaxf(cx, fmaxf(cy, cz));
    out->vel_mm_s = sqrtf(wx + wy + wz);
    out->eixo_x_g = mx + rx;
    out->eixo_y_g = my + ry;
    out->eixo_z_g = mz + rz;
    out->n_validas = n_val;
    return true;
}

// ---------------------------------------------------------------------
//  Auto-teste
// ---------------------------------------------------------------------
#define AT_N       1600      // 1 s a 1600 Hz
#define AT_AQUEC    400      // 0,25 s para o passa-alta assentar
#define AT_FREQ    50.0f     // bem dentro da banda; longe do corte de 10 Hz
#define AT_AMP      0.1f     // g de pico

bool vib_autoteste(float fs_hz, float hp_hz, float erro_pct[3])
{
    static vib_amostra_t buf[AT_N];   // 19 KB: static de proposito, a pilha
                                      // de uma task do IDF nao aguenta isso.
    if (!(fs_hz > 4.0f * AT_FREQ)) { return false; }

    for (int i = 0; i < AT_N; i++) {
        const float t = (float)i / fs_hz;
        const float s = AT_AMP * sinf(2.0f * (float)M_PI * AT_FREQ * t);
        // Senoide so no X, com 1 g de gravidade no Z. Isso tambem checa
        // que o DC nao vaza para o AC: se vazasse, o RMS viria ~1 g.
        buf[i].x = s;
        buf[i].y = 0.0f;
        buf[i].z = 1.0f;
    }

    vib_resultado_t r;
    if (!vib_calcular(buf, AT_N, AT_AQUEC, fs_hz, hp_hz, &r)) { return false; }

    // Valores analiticos para senoide pura de amplitude de pico A:
    //   rms   = A/raiz(2)
    //   crista= raiz(2)
    //   v_rms = (A*g)/(2*pi*f) / raiz(2)  , em m/s -> x1000 para mm/s
    const float esp_rms  = AT_AMP / 1.41421356f;
    const float esp_cr   = 1.41421356f;
    const float esp_vel  = (AT_AMP * G_MS2) / (2.0f * (float)M_PI * AT_FREQ)
                           / 1.41421356f * 1000.0f;

    const float e_rms = (r.rms_g    - esp_rms) / esp_rms * 100.0f;
    const float e_cr  = (r.crista   - esp_cr)  / esp_cr  * 100.0f;
    const float e_vel = (r.vel_mm_s - esp_vel) / esp_vel * 100.0f;

    if (erro_pct != NULL) {
        erro_pct[0] = e_rms;
        erro_pct[1] = e_cr;
        erro_pct[2] = e_vel;
    }

    // 2% e folgado para o que o algoritmo promete (1,4% no pior ponto da
    // banda, e a 50 Hz com fs 1600 o erro previsto e bem menor). Um port
    // com coeficiente trocado erra MUITO mais que isso -- que e o tipo de
    // falha que este teste existe para pegar.
    return fabsf(e_rms) < 2.0f && fabsf(e_cr) < 2.0f && fabsf(e_vel) < 2.0f;
}
