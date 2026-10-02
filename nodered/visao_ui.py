"""Tela principal (Visao Geral): faixa de resumo e cards dos ativos.

Mesmo idioma do Detalhe (ver detalhe_ui.py): tons de azul para o que esta
normal, cor forte so para atencao/critico, numeros grandes, variacao contra
a media da ultima hora. Os dados chegam prontos do no "montar painel".
"""

RESUMO = r"""
<template>
  <div class="rs" v-if="r">
    <img v-if="r.logo" :src="r.logo" alt="InsightX" class="rs-logo">

    <!-- anel: estado atual dos ativos, com a saude da ultima hora no centro -->
    <div class="rs-anel" :title="'% do tempo em OK, somando todos os ativos, na última hora'">
      <svg viewBox="0 0 120 120" width="104" height="104">
        <circle cx="60" cy="60" r="48" class="rs-trilha"/>
        <circle v-for="s in arcos" :key="s.k" cx="60" cy="60" r="48" fill="none"
                :stroke="s.cor" stroke-width="10" stroke-linecap="round"
                :stroke-dasharray="s.dash" :stroke-dashoffset="s.off" transform="rotate(-90 60 60)"/>
      </svg>
      <div class="rs-centro">
        <b>{{ r.saude === null ? '—' : r.saude + '%' }}</b>
        <span>em OK · 1 h</span>
      </div>
    </div>

    <div class="rs-cont">
      <div class="rs-c"><span class="rs-cr"><i style="background:#58a6ff"></i>Normais</span><b>{{ r.cnt.normal }}</b></div>
      <div class="rs-c"><span class="rs-cr"><i style="background:#f59e0b"></i>Atenção</span>
        <b :class="{ at: r.cnt.atencao }">{{ r.cnt.atencao }}</b></div>
      <div class="rs-c"><span class="rs-cr"><i style="background:#ef4444"></i>Críticos</span>
        <b :class="{ cr: r.cnt.critico }">{{ r.cnt.critico }}</b></div>
      <div class="rs-c"><span class="rs-cr"><i class="sd"></i>Sem dados</span><b>{{ r.cnt.sem_dados }}</b></div>
    </div>

    <div class="rs-sis">
      <div v-for="e in r.elos" :key="e.nome" class="rs-elo" :class="{ mal: !e.ok }">
        <i></i><span class="rs-en">{{ e.nome }}</span><span class="rs-ed">{{ e.det }}</span>
      </div>
    </div>
  </div>
  <div v-else class="rs-vazio">Aguardando o primeiro ativo publicar...</div>
</template>

<script>
export default {
  data () { return { r: null } },
  computed: {
    arcos () {
      if (!this.r) { return []; }
      const c = this.r.cnt, tot = this.r.total || 1, circ = 2 * Math.PI * 48;
      const ordem = [['normal', '#58a6ff'], ['atencao', '#f59e0b'], ['critico', '#ef4444'], ['sem_dados', '#5c6773']];
      let acum = 0; const out = [];
      for (const [k, cor] of ordem) {
        const n = c[k] || 0; if (!n) { continue; }
        // pequeno vao entre segmentos para cada estado se ler sozinho
        const len = Math.max(0, circ * n / tot - (tot > 1 ? 6 : 0));
        out.push({ k: k, cor: cor, dash: len + ' ' + circ, off: -acum });
        acum += circ * n / tot;
      }
      return out;
    }
  },
  watch: {
    msg: { immediate: true,
           handler (m) { const p = m && m.payload; if (p && p.cnt) { this.r = p; } } }
  }
}
</script>

<style scoped>
.rs { display: flex; align-items: center; gap: 28px; flex-wrap: wrap; padding: 4px 4px; }
.rs-logo { height: 44px; padding-right: 26px; border-right: 1px solid #2a323c; }
.rs-anel { position: relative; width: 104px; height: 104px; flex: none; }
.rs-trilha { fill: none; stroke: #1c232c; stroke-width: 10; }
.rs-centro { position: absolute; inset: 0; display: flex; flex-direction: column;
             align-items: center; justify-content: center; }
.rs-centro b { font-size: 22px; font-weight: 650; color: #e6edf3; letter-spacing: -.02em; }
.rs-centro span { font-size: 10px; color: #6e7a87; }
.rs-cont { display: flex; gap: 26px; }
.rs-c { display: flex; flex-direction: column; gap: 4px; min-width: 70px; }
.rs-cr { font-size: 11px; color: #6e7a87; text-transform: uppercase; letter-spacing: .07em;
         display: inline-flex; align-items: center; gap: 6px; }
.rs-cr i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.rs-cr i.sd { border: 1.5px solid #6e7a87; width: 6px; height: 6px; }
.rs-c b { font-size: 30px; font-weight: 650; color: #e6edf3; line-height: 1; letter-spacing: -.02em; }
.rs-c b.at { color: #f59e0b; } .rs-c b.cr { color: #ef4444; }
.rs-sis { margin-left: auto; display: flex; flex-direction: column; gap: 6px; }
.rs-elo { display: flex; align-items: center; gap: 8px; font-size: 12px; background: #1c232c;
          border: 1px solid #2a323c; border-radius: 999px; padding: 4px 12px; }
.rs-elo i { width: 7px; height: 7px; border-radius: 50%; background: #58a6ff; }
.rs-elo.mal { border-color: rgba(239,68,68,.5); } .rs-elo.mal i { background: #ef4444; }
.rs-en { color: #e6edf3; font-weight: 600; }
.rs-ed { color: #6e7a87; }
.rs-vazio { color: #6e7a87; font-size: 14px; padding: 8px; }
@media (max-width: 700px) {
  .rs { gap: 18px; }
  .rs-logo { border: 0; padding: 0; }
  .rs-sis { margin-left: 0; width: 100%; }
  .rs-cont { gap: 18px; flex-wrap: wrap; }
}
</style>
"""

CARDS = r"""
<template>
  <div class="pa">
    <div v-if="!cards.length" class="pa-vazio">Aguardando o primeiro ativo publicar...</div>
    <div v-for="c in cards" :key="c.chave" class="cd" :class="'e-' + c.estado"
         role="button" tabindex="0" @click="abrir(c)" @keyup.enter="abrir(c)">
      <div class="cd-topo">
        <div class="cd-nome">
          <div class="cd-tag">{{ c.tag }}</div>
          <div class="cd-desc">{{ c.descricao }}</div>
        </div>
        <span class="cd-chip">{{ c.simb }} {{ c.rotulo }}</span>
      </div>

      <div class="cd-med">
        <div v-for="(m, i) in c.medidas" :key="m.nome" class="cd-m">
          <div class="cd-mr">{{ m.nome }}</div>
          <div class="cd-mv" :class="{ vazio: m.vazio, alerta: m.alerta }"
               :style="m.alerta ? { color: m.cor } : {}">
            {{ m.texto }}<small v-if="m.un">{{ m.un }}</small>
          </div>
          <div class="cd-d">
            <span v-if="m.delta !== null && m.delta !== undefined" :class="m.delta >= 0 ? 'up' : 'down'">
              {{ m.delta >= 0 ? '▲' : '▼' }} {{ Math.abs(m.delta).toFixed(0) }}%
            </span>
            <span v-else class="nd">&nbsp;</span>
          </div>
          <svg v-if="m.spark && m.spark.length > 2" class="cd-sp" viewBox="0 0 100 26" preserveAspectRatio="none">
            <defs>
              <linearGradient :id="'sp' + c.chave.replace(/\W/g, '') + i" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" :stop-color="corSpark(m)" stop-opacity=".35"/>
                <stop offset="100%" :stop-color="corSpark(m)" stop-opacity="0"/>
              </linearGradient>
            </defs>
            <path :d="area(m.spark)" :fill="'url(#sp' + c.chave.replace(/\W/g, '') + i + ')'"/>
            <polyline :points="pontos(m.spark)" fill="none" :stroke="corSpark(m)" stroke-width="1.6"
                      vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
          </svg>
          <div v-else class="cd-sp-vazio"></div>
        </div>
      </div>

      <div class="cd-rod">
        <span>{{ c.n_partes }}<span v-if="c.marcha" class="cd-marcha" :class="c.marcha_cls"> · {{ c.marcha }}</span></span>
        <span>visto há {{ c.visto }}</span>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  data () { return { cards: [] } },
  methods: {
    abrir (c) { this.send({ payload: c.chave }) },
    corSpark (m) { return m.alerta ? m.cor : '#58a6ff'; },
    // Escala da PROPRIA serie: o minigrafico mostra forma (para onde vai);
    // nivel quem mostra e o numero e a cor.
    xy (arr) {
      const min = Math.min(...arr), max = Math.max(...arr), amp = (max - min) || 1, n = arr.length - 1;
      return arr.map((v, i) => [(i / n) * 100, 24 - ((v - min) / amp) * 20]);
    },
    pontos (arr) { return this.xy(arr).map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' '); },
    area (arr) {
      const p = this.xy(arr);
      return 'M' + p.map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' L') + ' L100,26 L0,26 Z';
    }
  },
  watch: {
    msg: { immediate: true,
           handler (m) { if (m && Array.isArray(m.payload)) { this.cards = m.payload } } }
  }
}
</script>

<style scoped>
.pa { display: grid; gap: 16px; align-content: start; align-items: stretch;
      grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); font-variant-numeric: tabular-nums; }
.pa-vazio { color: #6e7a87; padding: 12px; font-size: 14px; }

.cd { display: flex; flex-direction: column; background: #161b22; border: 1px solid #2a323c;
      border-top: 3px solid #2a3a52; border-radius: 12px; padding: 16px 18px; cursor: pointer;
      transition: border-color .2s, background .2s, transform .2s, box-shadow .2s; }
.cd:hover, .cd:focus-visible { background: #1c232c; border-color: #3b4a5c; transform: translateY(-2px);
      box-shadow: 0 8px 22px rgba(0,0,0,.35); outline: none; }
/* Cor forte so quando o ativo pede atencao: a faixa do topo e a etiqueta. */
.cd.e-atencao { border-top-color: #f59e0b; }
.cd.e-critico { border-top-color: #ef4444; box-shadow: 0 0 0 1px rgba(239,68,68,.18); }
.cd.e-sem_dados { border-top-color: #5c6773; }

.cd-topo { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; margin-bottom: 14px; }
.cd-nome { min-width: 0; }
.cd-tag { font-size: 16px; font-weight: 650; color: #e6edf3; letter-spacing: -.01em; }
.cd-desc { font-size: 12px; color: #6e7a87; margin-top: 3px; line-height: 1.4; min-height: 2.8em; }
.cd-chip { font-size: 10px; font-weight: 650; letter-spacing: .06em; padding: 3px 9px; border-radius: 999px;
           white-space: nowrap; color: #8bb4e8; background: rgba(88,166,255,.10); }
.e-atencao .cd-chip { color: #f59e0b; background: rgba(245,158,11,.12); }
.e-critico .cd-chip { color: #ef4444; background: rgba(239,68,68,.12); }
.e-sem_dados .cd-chip { color: #8b98a5; background: rgba(139,152,165,.12); }

.cd-med { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.cd-mr { font-size: 11px; color: #6e7a87; text-transform: uppercase; letter-spacing: .07em; }
.cd-mv { font-size: 24px; font-weight: 650; color: #e6edf3; letter-spacing: -.02em; margin-top: 4px; white-space: nowrap; }
.cd-mv small { font-size: 12px; font-weight: 500; color: #8b98a5; margin-left: 3px; }
.cd-mv.vazio { color: #5c6773; }
.cd-d { font-size: 11px; font-weight: 600; height: 16px; margin-top: 2px; }
.cd-d .up { color: #79c0ff; } .cd-d .down { color: #9fb3c8; }
.cd-sp { width: 100%; height: 30px; margin-top: 4px; display: block; }
.cd-sp-vazio { height: 30px; margin-top: 4px; border-bottom: 1px dashed #2a323c; }

.cd-rod { display: flex; justify-content: space-between; margin-top: auto; padding-top: 14px;
          font-size: 12px; color: #6e7a87; }
.cd-marcha.on { color: #8bb4e8; }
</style>
"""
