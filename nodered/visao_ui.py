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
    <div class="rs-anel" title="Saúde da planta: quanto do tempo os ativos ficaram em OK na última hora, somando todos. O anel mostra quantos ativos estão em cada estado agora.">
      <svg viewBox="0 0 120 120" width="104" height="104">
        <circle cx="60" cy="60" r="48" class="rs-trilha"/>
        <circle v-for="s in arcos" :key="s.k" cx="60" cy="60" r="48" fill="none"
                :stroke="s.cor" stroke-width="10" stroke-linecap="round"
                :stroke-dasharray="s.dash" :stroke-dashoffset="s.off" transform="rotate(-90 60 60)"/>
      </svg>
      <div class="rs-centro">
        <b>{{ r.saude === null ? '—' : r.saude + '%' }}</b>
        <span>do tempo em OK</span>
      </div>
      <div class="rs-anel-rot">Saúde da planta · última hora</div>
    </div>

    <div class="rs-cont">
      <div class="rs-c"><span class="rs-cr"><i style="background:#58a6ff"></i>Normais</span><b>{{ r.cnt.normal }}</b></div>
      <div class="rs-c"><span class="rs-cr"><i style="background:#f59e0b"></i>Atenção</span>
        <b :class="{ at: r.cnt.atencao }">{{ r.cnt.atencao }}</b></div>
      <div class="rs-c"><span class="rs-cr"><i style="background:#ef4444"></i>Críticos</span>
        <b :class="{ cr: r.cnt.critico }">{{ r.cnt.critico }}</b></div>
      <div class="rs-c"><span class="rs-cr"><i class="sd"></i>Sem dados</span><b>{{ r.cnt.sem_dados }}</b></div>
      <div class="rs-c" v-if="r.cnt.silenciado"><span class="rs-cr">🔕 Silenciados</span><b class="sil">{{ r.cnt.silenciado }}</b></div>
      <div class="rs-pend" v-if="r.cnt.pendentes">● {{ r.cnt.pendentes }} {{ r.cnt.pendentes > 1 ? 'alarmes não reconhecidos' : 'alarme não reconhecido' }}</div>
    </div>

    <div class="rs-sis">
      <div v-for="e in r.elos" :key="e.nome" class="rs-elo" :class="{ mal: !e.ok }">
        <i></i><span class="rs-en">{{ e.nome }}</span><span class="rs-ed">{{ e.det }}</span>
      </div>
    </div>
  </div>
  <div v-else class="rs-vazio">Aguardando o primeiro ativo publicar...</div>

  <!-- fila de acao: so o que pede gente, com o que fazer -->
  <div v-if="r && r.fila && r.fila.length" class="fa">
    <div class="fa-cab">
      <span class="fa-tit">O que fazer agora</span>
      <span class="fa-n">{{ r.fila.length }} {{ r.fila.length > 1 ? 'ocorrências' : 'ocorrência' }}</span>
      <button v-if="r.fila.length > LIM" class="fa-mais" @click="tudo = !tudo">
        {{ tudo ? 'mostrar menos' : 'ver todas' }}</button>
    </div>
    <div v-for="(f, i) in (tudo ? r.fila : r.fila.slice(0, LIM))" :key="f.chave + f.parte + f.estado + i"
         class="fa-i" :class="['e-' + f.estado, { pend: f.pendente }]">
      <span class="fa-sev">{{ f.simb }}</span>
      <div class="fa-txt">
        <div class="fa-l1">
          <b>{{ f.ativo }}</b><span v-if="f.parte" class="fa-p"> › {{ f.parte }}</span>
          <span class="fa-mot">{{ f.motivo }}</span>
        </div>
        <div class="fa-rec">{{ f.recomendacao }}</div>
      </div>
      <span class="fa-ha">{{ f.pendente ? '● ' : '✓ ' }}há {{ dur(r.agora - f.desde_ms) }}</span>
      <button v-if="f.pendente" class="fa-b pri" @click="send({ payload: { acao: 'reconhecer', chave: f.chave } })">Reconhecer</button>
      <button class="fa-b" @click="send({ payload: f.chave })">Abrir</button>
    </div>
  </div>
</template>

<script>
export default {
  data () { return { r: null, tudo: false, LIM: 4 } },
  methods: {
    dur (ms) {
      const m = Math.round(ms / 60000);
      if (m < 1) { return 'menos de 1 min'; }
      if (m < 60) { return m + ' min'; }
      const h = Math.floor(m / 60);
      return h + ' h' + (m % 60 ? ' ' + (m % 60) + ' min' : '');
    }
  },
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
.rs-centro span { font-size: 9px; color: #6e7a87; }
.rs-anel { margin-bottom: 14px; }
.rs-anel-rot { position: absolute; left: 50%; bottom: -16px; transform: translateX(-50%);
               white-space: nowrap; font-size: 10px; color: #6e7a87; letter-spacing: .02em; }
.rs-cont { display: flex; gap: 26px; }
.rs-c { display: flex; flex-direction: column; gap: 4px; min-width: 70px; }
.rs-cr { font-size: 11px; color: #6e7a87; text-transform: uppercase; letter-spacing: .07em;
         display: inline-flex; align-items: center; gap: 6px; }
.rs-cr i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.rs-cr i.sd { border: 1.5px solid #6e7a87; width: 6px; height: 6px; }
.rs-c b { font-size: 30px; font-weight: 650; color: #e6edf3; line-height: 1; letter-spacing: -.02em; }
.rs-c b.at { color: #f59e0b; } .rs-c b.cr { color: #ef4444; } .rs-c b.sil { color: #8b98a5; }
.rs-cont { flex-wrap: wrap; align-items: flex-end; }
.rs-pend { align-self: center; font-size: 12px; font-weight: 600; color: #f59e0b;
           background: rgba(245,158,11,.10); border-radius: 999px; padding: 4px 12px;
           animation: rs-pisca 1.2s ease-in-out infinite; }
@keyframes rs-pisca { 50% { opacity: .45; } }
.rs-sis { margin-left: auto; display: flex; flex-direction: column; gap: 6px; }
.rs-elo { display: flex; align-items: center; gap: 8px; font-size: 12px; background: #1c232c;
          border: 1px solid #2a323c; border-radius: 999px; padding: 4px 12px; }
.rs-elo i { width: 7px; height: 7px; border-radius: 50%; background: #58a6ff; }
.rs-elo.mal { border-color: rgba(239,68,68,.5); } .rs-elo.mal i { background: #ef4444; }
.rs-en { color: #e6edf3; font-weight: 600; }
.rs-ed { color: #6e7a87; }
.rs-vazio { color: #6e7a87; font-size: 14px; padding: 8px; }

/* --- fila de acao --- */
.fa { margin-top: 16px; padding-top: 14px; border-top: 1px solid #222a33; }
.fa-cab { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.fa-tit { font-size: 13px; font-weight: 650; color: #e6edf3; }
.fa-n { font-size: 12px; color: #6e7a87; }
.fa-mais { margin-left: auto; background: transparent; border: 0; color: #79c0ff; font-size: 12px; cursor: pointer; }
.fa-i { display: grid; grid-template-columns: 22px 1fr auto auto auto; align-items: center; gap: 12px;
        padding: 10px 12px; border-radius: 10px; background: #1c232c; border: 1px solid #2a323c;
        border-left: 3px solid #5c6773; margin-bottom: 6px; }
.fa-i.e-critico { border-left-color: #ef4444; }
.fa-i.e-atencao { border-left-color: #f59e0b; }
.fa-sev { font-size: 14px; text-align: center; color: #8b98a5; }
.e-critico .fa-sev { color: #ef4444; } .e-atencao .fa-sev { color: #f59e0b; }
.fa-txt { min-width: 0; }
.fa-l1 { font-size: 13px; color: #e6edf3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fa-p { color: #8b98a5; }
.fa-mot { color: #8b98a5; margin-left: 10px; font-size: 12px; }
.fa-rec { font-size: 12px; color: #8bb4e8; margin-top: 3px; line-height: 1.4; }
.fa-ha { font-size: 12px; color: #6e7a87; white-space: nowrap; }
.pend .fa-ha { color: #f59e0b; }
.fa-b { background: #161b22; color: #c9d4df; border: 1px solid #2a323c; border-radius: 7px;
        padding: 5px 12px; font-size: 12px; cursor: pointer; }
.fa-b:hover { border-color: #3b4a5c; color: #e6edf3; }
.fa-b.pri { background: #2f81f7; border-color: #2f81f7; color: #fff; }
@media (max-width: 700px) {
  .fa-i { grid-template-columns: 22px 1fr; }
  .fa-ha { grid-column: 2; }
  .fa-b { grid-column: 2; justify-self: start; }
}
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
  <div class="pa-barra" v-if="cards.length">
    <span class="pa-tit">Ativos</span>
    <span class="pa-n">{{ cards.length }}</span>
    <label v-if="temArea" class="pa-chk"><input type="checkbox" v-model="porArea"> por área</label>
    <div class="pa-seg">
      <button :class="{ on: modo === 'cards' }" @click="modo = 'cards'">Cards</button>
      <button :class="{ on: modo === 'lista' }" @click="modo = 'lista'">Lista</button>
    </div>
  </div>
  <div v-if="!cards.length" class="pa-vazio">Aguardando o primeiro ativo publicar...</div>

  <div v-for="g in grupos" :key="g.nome" class="pa-area">
  <div v-if="g.nome !== null" class="pa-ah">
    <span class="pa-an">{{ g.nome || 'Sem área definida' }}</span>
    <span class="pa-ac">{{ g.cards.length }} {{ g.cards.length > 1 ? 'ativos' : 'ativo' }}</span>
    <span v-for="e in g.resumo" :key="e.k" class="pa-ae" :class="'e-' + e.k">{{ e.simb }} {{ e.n }} {{ e.rot }}</span>
  </div>

  <!-- modo lista: uma linha por ativo, para planta grande -->
  <div v-if="modo === 'lista'" class="ls">
    <div v-for="c in g.cards" :key="c.chave" class="ls-l" :class="['e-' + (c.alarme && c.alarme.silenciado ? 'silenciado' : c.estado), { pend: c.alarme && c.alarme.pendente }]"
         role="button" tabindex="0" @click="abrir(c)" @keyup.enter="abrir(c)">
      <span class="cd-chip ls-chip">{{ c.alarme && c.alarme.silenciado ? '🔕 SILENCIADO' : c.simb + ' ' + c.rotulo }}</span>
      <span class="ls-nome">{{ c.tag }}<small v-if="c.descricao">{{ c.descricao }}</small></span>
      <span v-for="m in c.medidas" :key="m.nome" class="ls-m">
        <small :title="DICA[m.nome] || ''">{{ m.nome }}</small>
        <b :style="m.alerta ? { color: m.cor } : {}">{{ m.texto }}<i v-if="m.un"> {{ m.un }}</i></b>
      </span>
      <span class="ls-al" @click.stop>
        <button v-if="c.alarme && c.alarme.pendente" class="cd-b pri" @click="acao(c, 'reconhecer')">Reconhecer</button>
        <span v-else-if="c.alarme && c.alarme.reconhecido" class="ls-rec">✓</span>
      </span>
      <span class="ls-visto">{{ c.visto }}</span>
    </div>
  </div>

  <div v-else class="pa">
    <div v-for="c in g.cards" :key="c.chave" class="cd"
         :class="['e-' + (c.alarme && c.alarme.silenciado ? 'silenciado' : c.estado),
                  { pend: c.alarme && c.alarme.pendente }]"
         role="button" tabindex="0" @click="abrir(c)" @keyup.enter="abrir(c)">
      <div class="cd-topo">
        <div class="cd-nome">
          <div class="cd-tag">{{ c.tag }}</div>
          <div class="cd-desc">{{ c.descricao }}</div>
        </div>
        <span class="cd-chip" v-if="c.alarme && c.alarme.silenciado">🔕 SILENCIADO</span>
        <span class="cd-chip" v-else>{{ c.simb }} {{ c.rotulo }}</span>
      </div>

      <div class="cd-med">
        <div v-for="(m, i) in c.medidas" :key="m.nome" class="cd-m">
          <div class="cd-mr" :title="DICA[m.nome] || ''">{{ m.nome }}</div>
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
                <stop offset="0%" stop-color="#58a6ff" stop-opacity=".35"/>
                <stop offset="100%" stop-color="#58a6ff" stop-opacity="0"/>
              </linearGradient>
            </defs>
            <!-- faixa do normal (ISA-101): do fundo ate o limite de atencao -->
            <rect v-if="faixa(m)" x="0" :y="faixa(m).y" width="100" :height="26 - faixa(m).y" class="cd-fx"/>
            <line v-if="faixa(m)" x1="0" x2="100" :y1="faixa(m).y" :y2="faixa(m).y" class="cd-fx-l"
                  vector-effect="non-scaling-stroke"/>
            <path :d="area(m.spark, m)" :fill="'url(#sp' + c.chave.replace(/\W/g, '') + i + ')'"/>
            <polyline :points="pontos(m.spark, m)" fill="none" stroke="#58a6ff" stroke-width="1.6"
                      vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/>
            <!-- o trecho ACIMA do limite, colorido: so ele chama atencao -->
            <clipPath v-if="faixa(m)" :id="'cl' + c.chave.replace(/\W/g, '') + i">
              <rect x="0" y="0" width="100" :height="faixa(m).y"/>
            </clipPath>
            <polyline v-if="faixa(m)" :points="pontos(m.spark, m)" fill="none" stroke="#f59e0b"
                      stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linejoin="round"
                      :clip-path="'url(#cl' + c.chave.replace(/\W/g, '') + i + ')'"/>
          </svg>
          <div v-else class="cd-sp-vazio"></div>
        </div>
      </div>

      <!-- alarme aberto: reconhecer / silenciar (ISA-18.2). Os botoes nao
           abrem o Detalhe: @click.stop. -->
      <div v-if="c.alarme && (c.estado !== 'normal' || c.alarme.silenciado)" class="cd-al" @click.stop>
        <template v-if="c.alarme.silenciado">
          <span class="cd-al-t">{{ c.alarme.sil_txt }}</span>
          <span class="cd-al-esp"></span>
          <button class="cd-b" @click="acao(c, 'reativar')">Reativar</button>
        </template>
        <template v-else>
          <span class="cd-al-t" v-if="c.alarme.reconhecido">✓ {{ c.alarme.rec_txt }}</span>
          <span class="cd-al-t pend" v-else-if="c.alarme.pendente">● não reconhecido</span>
          <span class="cd-al-esp"></span>
          <button v-if="c.alarme.pendente" class="cd-b pri" @click="acao(c, 'reconhecer')">Reconhecer</button>
          <span class="cd-sil">
            <button class="cd-b" @click="menu = menu === c.chave ? null : c.chave">Silenciar ▾</button>
            <span v-if="menu === c.chave" class="cd-menu">
              <button v-for="h in [1, 2, 4, 8, 24]" :key="h" @click="acao(c, 'silenciar', h)">{{ h }} h</button>
            </span>
          </span>
        </template>
      </div>

      <div class="cd-rod">
        <span>{{ c.n_partes }}<span v-if="c.marcha" class="cd-marcha" :class="c.marcha_cls"> · {{ c.marcha }}</span></span>
        <span>visto há {{ c.visto }}</span>
      </div>
    </div>
  </div>
  </div>
</template>

<script>
export default {
  data () { return { cards: [], menu: null, modo: 'cards', porArea: true,
                     DICA: { 'Vibração': 'Velocidade de vibração RMS (mm/s) — a grandeza da ISO 20816',
                             'Corrente': 'Corrente do motor, lida do inversor' } } },
  computed: {
    // So agrupa quando AGRUPA: com cada ativo numa area diferente, os
    // cabecalhos so repetiriam o nome de cada card.
    temArea () {
      const areas = new Set(this.cards.map(c => c.local));
      return this.cards.some(c => c.local) && areas.size < this.cards.length;
    },
    // Grupos por area, em ordem alfabetica; dentro de cada um, a ordem do
    // cadastro (estavel: o card nao muda de lugar quando o estado muda).
    grupos () {
      if (!this.temArea || !this.porArea) { return [{ nome: null, cards: this.cards, resumo: [] }]; }
      const mapa = {};
      for (const c of this.cards) { (mapa[c.local] = mapa[c.local] || []).push(c); }
      const ROT = { critico: ['■', 'crítico', 'críticos'], atencao: ['▲', 'atenção', 'atenção'],
                    sem_dados: ['○', 'sem dados', 'sem dados'] };
      return Object.keys(mapa).sort((a, b) => (a === '') - (b === '') || a.localeCompare(b))
        .map(nome => {
          const resumo = ['critico', 'atencao', 'sem_dados'].map(k => {
            const n = mapa[nome].filter(c => c.estado === k && !(c.alarme && c.alarme.silenciado)).length;
            return n ? { k: k, n: n, simb: ROT[k][0], rot: n > 1 ? ROT[k][2] : ROT[k][1] } : null;
          }).filter(Boolean);
          return { nome: nome, cards: mapa[nome], resumo: resumo };
        });
    }
  },
  watch: {
    modo (v) { try { localStorage.setItem('ix_vis_modo', v); } catch (e) {} },
    porArea (v) { try { localStorage.setItem('ix_vis_area', v ? '1' : '0'); } catch (e) {} },
    msg: { immediate: true,
           handler (m) { if (m && Array.isArray(m.payload)) { this.cards = m.payload } } }
  },
  mounted () {
    try {
      const m = localStorage.getItem('ix_vis_modo'); if (m === 'lista' || m === 'cards') { this.modo = m; }
      const a = localStorage.getItem('ix_vis_area'); if (a !== null) { this.porArea = a === '1'; }
    } catch (e) {}
  },
  methods: {
    abrir (c) { this.send({ payload: c.chave }) },
    acao (c, a, horas) {
      this.menu = null;
      this.send({ payload: { acao: a, chave: c.chave, horas: horas } });
    },
    corSpark (m) { return m.alerta ? m.cor : '#58a6ff'; },
    // Escala: a da propria serie, para mostrar FORMA. Quando a curva chega
    // perto do limite de atencao (70% dele ou mais), a escala passa a
    // incluir o limite -- ai a faixa do normal aparece e a distancia ate o
    // limite fica visivel, como pede a ISA-101. Longe do limite, a faixa
    // ocuparia o grafico inteiro e nao diria nada.
    dom (arr, m) {
      let lo = Math.min(...arr), hi = Math.max(...arr);
      if (m && m.lim_at && hi >= m.lim_at * 0.7) {
        // O limite entra na escala pelos DOIS lados: curva toda acima dele
        // (o pior caso) tambem tem de mostrar a faixa e o trecho colorido.
        hi = Math.max(hi, m.lim_at * 1.08);
        lo = Math.min(lo, m.lim_at * 0.85);
      }
      return [lo, hi];
    },
    xy (arr, m) {
      const [lo, hi] = this.dom(arr, m), amp = (hi - lo) || 1, n = arr.length - 1;
      return arr.map((v, i) => [(i / n) * 100, 24 - ((v - lo) / amp) * 20]);
    },
    faixa (m) {
      if (!m.lim_at || !m.spark || m.spark.length < 3) { return null; }
      const [lo, hi] = this.dom(m.spark, m);
      if (m.lim_at > hi || m.lim_at < lo) { return null; }
      return { y: 24 - ((m.lim_at - lo) / ((hi - lo) || 1)) * 20 };
    },
    pontos (arr, m) { return this.xy(arr, m).map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' '); },
    area (arr, m) {
      const p = this.xy(arr, m);
      return 'M' + p.map(q => q[0].toFixed(1) + ',' + q[1].toFixed(1)).join(' L') + ' L100,26 L0,26 Z';
    }
  },
}
</script>

<style scoped>
.pa-barra { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.pa-tit { font-size: 13px; font-weight: 650; color: #e6edf3; }
.pa-n { font-size: 12px; color: #6e7a87; }
.pa-chk { margin-left: auto; font-size: 12px; color: #8b98a5; display: inline-flex; gap: 6px; align-items: center; cursor: pointer; }
.pa-chk input { accent-color: #2f81f7; }
.pa-seg { display: flex; gap: 3px; background: #161b22; border: 1px solid #2a323c; border-radius: 9px; padding: 3px; }
.pa-barra .pa-seg:first-child { margin-left: auto; }
.pa-seg button { background: transparent; border: 0; color: #8b98a5; font-size: 12px; padding: 4px 12px; border-radius: 7px; cursor: pointer; }
.pa-seg button.on { background: #2f81f7; color: #fff; }
.pa-area + .pa-area { margin-top: 20px; }
.pa-ah { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin: 4px 2px 10px;
         padding-bottom: 6px; border-bottom: 1px solid #222a33; }
.pa-an { font-size: 13px; font-weight: 600; color: #c9d4df; }
.pa-ac { font-size: 12px; color: #6e7a87; }
.pa-ae { font-size: 12px; color: #8b98a5; }
.pa-ae.e-critico { color: #ef4444; } .pa-ae.e-atencao { color: #f59e0b; }

/* --- modo lista --- */
.ls { display: flex; flex-direction: column; gap: 4px; }
.ls-l { display: grid; grid-template-columns: 118px minmax(160px, 1.6fr) repeat(3, minmax(70px, .7fr)) 110px 70px;
        align-items: center; gap: 12px; padding: 8px 12px; background: #161b22; border: 1px solid #2a323c;
        border-left: 3px solid #2a3a52; border-radius: 8px; cursor: pointer; font-variant-numeric: tabular-nums; }
.ls-l:hover { background: #1c232c; }
.ls-l.e-atencao { border-left-color: #f59e0b; } .ls-l.e-critico { border-left-color: #ef4444; }
.ls-l.e-sem_dados, .ls-l.e-silenciado { border-left-color: #5c6773; }
.ls-chip { justify-self: start; }
.ls-nome { font-size: 13px; color: #e6edf3; font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ls-nome small { display: block; font-weight: 400; font-size: 11px; color: #6e7a87; overflow: hidden; text-overflow: ellipsis; }
.ls-m { display: flex; flex-direction: column; }
.ls-m small { font-size: 10px; color: #6e7a87; text-transform: uppercase; letter-spacing: .06em; }
.ls-m b { font-size: 15px; color: #e6edf3; font-weight: 650; }
.ls-m i { font-style: normal; font-size: 11px; color: #8b98a5; font-weight: 400; }
.ls-al { justify-self: end; cursor: default; }
.ls-rec { color: #8bb4e8; font-size: 12px; }
.ls-visto { font-size: 12px; color: #6e7a87; text-align: right; }
.ls-l.pend .ls-chip { animation: cd-pisca 1.2s ease-in-out infinite; }
@media (max-width: 760px) {
  .ls-l { grid-template-columns: 1fr 1fr 1fr; }
  .ls-nome { grid-column: 1 / -1; order: -1; }
  .ls-chip { grid-column: 1 / -1; order: -2; }
  .ls-al, .ls-visto { display: none; }
}

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
.cd.e-silenciado { border-top-color: #3b4a5c; }
.e-silenciado .cd-chip { color: #8b98a5; background: rgba(139,152,165,.10); }
.e-silenciado .cd-mv { opacity: .7; }
/* So o NAO reconhecido pisca (ISA-18.2): o reconhecido fica fixo. */
.cd.pend .cd-chip { animation: cd-pisca 1.2s ease-in-out infinite; }
@keyframes cd-pisca { 50% { opacity: .35; } }

.cd-al { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding-top: 10px;
         border-top: 1px solid #222a33; font-size: 12px; cursor: default; flex-wrap: wrap; }
.cd-al-t { color: #8b98a5; }
.cd-al-t.pend { color: #f59e0b; }
.cd-al-esp { flex: 1; }
.cd-b { background: #1c232c; color: #c9d4df; border: 1px solid #2a323c; border-radius: 7px;
        padding: 4px 10px; font-size: 12px; cursor: pointer; }
.cd-b:hover { border-color: #3b4a5c; color: #e6edf3; }
.cd-b.pri { background: #2f81f7; border-color: #2f81f7; color: #fff; }
.cd-sil { position: relative; }
.cd-menu { position: absolute; right: 0; bottom: 110%; display: flex; gap: 4px; background: #161b22;
           border: 1px solid #2a323c; border-radius: 9px; padding: 4px; z-index: 5;
           box-shadow: 0 8px 22px rgba(0,0,0,.45); }
.cd-menu button { background: transparent; border: 0; color: #c9d4df; font-size: 12px; padding: 4px 8px;
                  border-radius: 6px; cursor: pointer; white-space: nowrap; }
.cd-menu button:hover { background: #2f81f7; color: #fff; }

.cd-med { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.cd-mr { font-size: 11px; color: #6e7a87; text-transform: uppercase; letter-spacing: .07em; }
.cd-mv { font-size: 24px; font-weight: 650; color: #e6edf3; letter-spacing: -.02em; margin-top: 4px; white-space: nowrap; }
.cd-mv small { font-size: 12px; font-weight: 500; color: #8b98a5; margin-left: 3px; }
.cd-mv.vazio { color: #5c6773; }
.cd-d { font-size: 11px; font-weight: 600; height: 16px; margin-top: 2px; }
.cd-d .up { color: #79c0ff; } .cd-d .down { color: #9fb3c8; }
.cd-sp { width: 100%; height: 30px; margin-top: 4px; display: block; }
.cd-fx { fill: rgba(139,152,165,.08); }
.cd-fx-l { stroke: rgba(245,158,11,.45); stroke-width: 1; stroke-dasharray: 2 2; }
.cd-sp-vazio { height: 30px; margin-top: 4px; border-bottom: 1px dashed #2a323c; }

.cd-rod { display: flex; justify-content: space-between; margin-top: auto; padding-top: 14px;
          font-size: 12px; color: #6e7a87; }
.cd-marcha.on { color: #8bb4e8; }
</style>
"""
