"""Tela de Detalhe: painel principal (KPIs + grafico) e painel lateral.

Linguagem visual do simulador, em tons de azul: cor forte so para estado
(atencao/critico). Os dados chegam prontos do no "montar painel" (saida 3):
nada aqui decide alarme -- so apresenta.

Grafico proprio em SVG, e nao o ui-chart nativo, por tres motivos:
  - abre ja desenhado com a ultima hora (o nativo comeca vazio);
  - area em degrade, cursor vertical e cartao com o valor de cada parte;
  - linhas de limite (atencao/critico) desenhadas contra a curva.

A curva e suavizada por interpolacao MONOTONA (Fritsch-Carlson): passa por
todos os pontos medidos e nunca ultrapassa o maior/menor vizinho. Uma
curva "bonita" comum (Catmull-Rom, Bezier livre) inventa picos que nao
aconteceram -- inaceitavel num grafico de vibracao.
"""

DET_PRINCIPAL = r"""
<template>
  <div class="dp">
    <!-- KPIs: numero grande, variacao contra a ultima hora, estado -->
    <div class="dp-kpis">
      <div v-for="k in kpis" :key="k.id" class="dp-kpi" :class="{ sel: metrica === k.id }"
           @click="metrica = k.id" :title="k.dica || ''">
        <div class="dp-k-top">
          <span class="dp-k-nome" :title="k.nome === 'Vibração' ? 'Velocidade de vibração RMS (mm/s) — a grandeza da ISO 20816' : (k.nome === 'Aceleração' ? 'Aceleração de vibração RMS (g)' : '')">{{ k.nome }}</span>
          <span class="dp-tag" :style="tagEstilo(k)">{{ k.rotulo || '—' }}</span>
        </div>
        <div class="dp-k-val">{{ k.texto }}<small>{{ k.un }}</small></div>
        <div class="dp-k-rod">
          <span v-if="k.delta !== null" class="dp-delta" :class="k.delta >= 0 ? 'up' : 'down'">
            {{ k.delta >= 0 ? '▲' : '▼' }} {{ Math.abs(k.delta).toFixed(1) }}%
          </span>
          <span v-else class="dp-delta nd">—</span>
          <span class="dp-vs">vs média 1 h</span>
        </div>
      </div>
    </div>

    <!-- leituras secundarias, sem alarme -->
    <div class="dp-sec">
      <div v-for="s in sec" :key="s.nome" class="dp-sec-i">
        <span class="dp-sec-n">{{ s.nome }}</span>
        <b>{{ s.texto }}</b><small v-if="s.texto !== '--'">{{ s.un }}</small>
        <span v-if="s.rotulo" class="dp-sec-r">{{ s.rotulo }}</span>
      </div>
    </div>

    <!-- grafico -->
    <div class="dp-graf">
      <div class="dp-g-top">
        <div class="dp-abas">
          <button v-for="k in kpis" :key="k.id" class="dp-aba" :class="{ on: metrica === k.id }"
                  @click="metrica = k.id">{{ k.nome }}</button>
        </div>
        <div class="dp-jans">
          <button v-for="j in [15, 60]" :key="j" class="dp-jan" :class="{ on: janela === j }"
                  @click="janela = j">{{ j === 60 ? '1 h' : j + ' min' }}</button>
        </div>
      </div>

      <div class="dp-leg" v-if="curvas.length">
        <span v-for="c in curvas" :key="c.nome"><i :style="{ background: c.cor }"></i>{{ c.nome }}</span>
        <span v-if="lim" class="dp-leg-lim">{{ lim.txt }}</span>
      </div>

      <div class="dp-svg" ref="caixa" @mousemove="mover" @mouseleave="cursor = null">
        <svg :width="L" :height="A" v-if="L">
          <defs>
            <linearGradient v-for="(c, i) in curvas" :key="'g'+i" :id="'dpg' + uid + i" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" :stop-color="c.cor" stop-opacity="0.28"/>
              <stop offset="100%" :stop-color="c.cor" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <!-- grade -->
          <g v-for="g in grade" :key="'y'+g.v">
            <line :x1="M.e" :x2="L - M.d" :y1="g.y" :y2="g.y" class="dp-grade"/>
            <text :x="M.e - 8" :y="g.y + 3" class="dp-eixo" text-anchor="end">{{ g.rot }}</text>
          </g>
          <text v-for="g in gradeX" :key="'x'+g.t" :x="g.x" :y="A - 6" class="dp-eixo" text-anchor="middle">{{ g.rot }}</text>
          <!-- limites -->
          <g v-if="lim">
            <line v-if="yDe(lim.at) > M.t" :x1="M.e" :x2="L - M.d" :y1="yDe(lim.at)" :y2="yDe(lim.at)" class="dp-lim at"/>
            <line v-if="yDe(lim.cr) > M.t" :x1="M.e" :x2="L - M.d" :y1="yDe(lim.cr)" :y2="yDe(lim.cr)" class="dp-lim cr"/>
          </g>
          <!-- areas e linhas -->
          <path v-for="(c, i) in curvas" :key="'a'+i" :d="c.area" :fill="'url(#dpg' + uid + i + ')'"/>
          <path v-for="(c, i) in curvas" :key="'l'+i" :d="c.linha" fill="none" :stroke="c.cor" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round"/>
          <!-- cursor -->
          <g v-if="cursor">
            <line :x1="cursor.x" :x2="cursor.x" :y1="M.t" :y2="A - M.b" class="dp-cursor"/>
            <circle v-for="p in cursor.pts" :key="p.nome" :cx="cursor.x" :cy="p.y" r="4.5"
                    :fill="p.cor" stroke="#0e1116" stroke-width="2"/>
          </g>
        </svg>
        <div v-if="!curvas.length" class="dp-vazio">
          Coletando dados — o gráfico se completa nos próximos minutos.
        </div>
        <div v-if="cursor" class="dp-dica" :style="{ left: cursor.dx + 'px' }">
          <div class="dp-d-t">{{ cursor.hora }}</div>
          <div v-for="p in cursor.pts" :key="p.nome" class="dp-d-l">
            <i :style="{ background: p.cor }"></i>{{ p.nome }}
            <b>{{ p.txt }} <small>{{ atual.un }}</small></b>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  data () {
    return { kpis: [], sec: [], series: {}, agora: Date.now(), metrica: 'vel', janela: 60,
             L: 0, A: 280, cursor: null, uid: Math.random().toString(36).slice(2, 7),
             M: { e: 48, d: 12, t: 12, b: 26 },
             CORES: ['#58a6ff', '#56d4dd', '#a5b4fc', '#79c0ff', '#7ee0c3', '#9fb7ff'] }
  },
  computed: {
    atual () { return this.kpis.find(k => k.id === this.metrica) || null; },
    t0 () { return this.agora - this.janela * 60000; },
    // Inicio do EIXO: o da janela, ou o primeiro dado se ele for mais novo.
    // Sem isso, logo depois de ligar, uma hora de eixo vazio espreme a
    // curva na ponta direita.
    x0 () {
      let ini = this.agora;
      for (const s of this.brutas) { if (s.pts[0][0] < ini) { ini = s.pts[0][0]; } }
      return Math.max(this.t0, Math.min(ini, this.agora - 60000));
    },
    // Limites so com UMA curva: num ativo com varias partes cada uma tem a
    // sua corrente nominal, e uma linha unica de limite enganaria.
    lim () { return (this.atual && this.atual.lim && this.brutas.length === 1) ? this.atual.lim : null; },
    brutas () {
      return (this.series[this.metrica] || []).map((s, i) => ({
        nome: s.nome, cor: this.CORES[i % this.CORES.length],
        pts: s.pts.filter(p => p[0] >= this.t0) })).filter(s => s.pts.length > 1);
    },
    dom () {
      let lo = Infinity, hi = -Infinity;
      for (const s of this.brutas) for (const p of s.pts) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }
      if (!isFinite(lo)) { return [0, 1]; }
      // Inclui o limite de atencao quando a curva chega perto dele: o
      // limite so informa se aparece junto do dado.
      const lim = this.lim;
      if (lim && hi > lim.at * 0.6) { hi = Math.max(hi, lim.at); }
      if (lim && hi > lim.cr * 0.8) { hi = Math.max(hi, lim.cr); }
      const folga = (hi - lo) * 0.15 || Math.abs(hi) * 0.1 || 1;
      return [Math.max(0, lo - folga), hi + folga];
    },
    curvas () {
      return this.brutas.map(s => {
        const xy = s.pts.map(p => [this.xDe(p[0]), this.yDe(p[1])]);
        const linha = this.monotona(xy);
        const base = this.A - this.M.b;
        const area = linha + ' L' + xy[xy.length - 1][0] + ',' + base + ' L' + xy[0][0] + ',' + base + ' Z';
        return { nome: s.nome, cor: s.cor, linha: linha, area: area, pts: s.pts };
      });
    },
    grade () {
      const [lo, hi] = this.dom, r = [];
      for (let k = 0; k <= 4; k++) {
        const v = lo + (hi - lo) * k / 4;
        r.push({ v: v, y: this.yDe(v), rot: v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2) });
      }
      return r;
    },
    gradeX () {
      const r = [];
      for (let k = 0; k <= 4; k++) {
        const t = this.x0 + (this.agora - this.x0) * k / 4;
        // Menos de 10 min de eixo: com so hora:minuto os rotulos se repetem.
        const fmt = (this.agora - this.x0 < 600000)
          ? { hour: '2-digit', minute: '2-digit', second: '2-digit' } : { hour: '2-digit', minute: '2-digit' };
        r.push({ t: t, x: this.xDe(t), rot: new Date(t).toLocaleTimeString([], fmt) });
      }
      return r;
    }
  },
  methods: {
    xDe (t) { return this.M.e + (t - this.x0) / (this.agora - this.x0) * (this.L - this.M.e - this.M.d); },
    yDe (v) {
      const [lo, hi] = this.dom;
      return this.M.t + (1 - (v - lo) / (hi - lo)) * (this.A - this.M.t - this.M.b);
    },
    // Fritsch-Carlson: tangentes que preservam a monotonia entre pontos.
    monotona (p) {
      const n = p.length;
      if (n < 3) { return 'M' + p.map(q => q[0] + ',' + q[1]).join(' L'); }
      const d = [], m = [];
      for (let i = 0; i < n - 1; i++) { d.push((p[i + 1][1] - p[i][1]) / ((p[i + 1][0] - p[i][0]) || 1)); }
      m.push(d[0]);
      for (let i = 1; i < n - 1; i++) { m.push(d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2); }
      m.push(d[n - 2]);
      for (let i = 0; i < n - 1; i++) {
        if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; continue; }
        const a = m[i] / d[i], b = m[i + 1] / d[i], h = a * a + b * b;
        if (h > 9) { const t = 3 / Math.sqrt(h); m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]; }
      }
      let s = 'M' + p[0][0] + ',' + p[0][1];
      for (let i = 0; i < n - 1; i++) {
        const dx = (p[i + 1][0] - p[i][0]) / 3;
        s += ' C' + (p[i][0] + dx) + ',' + (p[i][1] + m[i] * dx) + ' ' +
             (p[i + 1][0] - dx) + ',' + (p[i + 1][1] - m[i + 1] * dx) + ' ' + p[i + 1][0] + ',' + p[i + 1][1];
      }
      return s;
    },
    mover (ev) {
      if (!this.curvas.length) { return; }
      const r = this.$refs.caixa.getBoundingClientRect();
      const x = ev.clientX - r.left;
      if (x < this.M.e || x > this.L - this.M.d) { this.cursor = null; return; }
      const t = this.x0 + (x - this.M.e) / (this.L - this.M.e - this.M.d) * (this.agora - this.x0);
      // Ponto MEDIDO mais proximo de cada curva: o cartao mostra dado
      // real, nunca um valor interpolado.
      const pts = this.curvas.map(c => {
        let mel = c.pts[0];
        for (const p of c.pts) { if (Math.abs(p[0] - t) < Math.abs(mel[0] - t)) { mel = p; } }
        return { nome: c.nome, cor: c.cor, t: mel[0], y: this.yDe(mel[1]),
                 txt: mel[1].toFixed({ temp: 1, vel: 2, vib: 3, corr: 2 }[this.metrica]) };
      });
      const tx = pts[0].t;
      this.cursor = { x: this.xDe(tx), pts: pts,
                      hora: new Date(tx).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
                      dx: Math.min(Math.max(this.xDe(tx) + 14, 0), this.L - 210) };
    },
    tagEstilo (k) {
      // Normal fica em azul-acinzentado: cor forte so quando pede atencao.
      if (k.cor === '#22c55e' || !k.simb) { return { color: '#8bb4e8', borderColor: '#2a3a52', background: 'rgba(88,166,255,.08)' }; }
      return { color: k.cor, borderColor: k.cor, background: 'transparent' };
    },
    medir () { if (this.$refs.caixa) { this.L = this.$refs.caixa.clientWidth; } }
  },
  mounted () {
    this.medir();
    this._ro = new ResizeObserver(() => this.medir());
    if (this.$refs.caixa) { this._ro.observe(this.$refs.caixa); }
    try { const m = localStorage.getItem('ix_det_metrica'); if (m) { this.metrica = m; } } catch (e) {}
  },
  unmounted () { if (this._ro) { this._ro.disconnect(); } },
  watch: {
    metrica (m) { try { localStorage.setItem('ix_det_metrica', m); } catch (e) {} },
    msg: {
      immediate: true,
      handler (m) {
        const p = (m && m.payload) || {};
        if (!p.kpis) { return; }
        this.kpis = p.kpis; this.sec = p.sec || []; this.series = p.series || {};
        this.agora = p.agora || Date.now();
        // Ativo sem a metrica escolhida (ex.: sem inversor): cai na primeira que tenha dado.
        if (!(this.series[this.metrica] || []).length) {
          const k = this.kpis.find(x => (this.series[x.id] || []).length);
          if (k) { this.metrica = k.id; }
        }
      }
    }
  }
}
</script>

<style scoped>
.dp { font-variant-numeric: tabular-nums; }
.dp-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.dp-kpi { background: #1c232c; border: 1px solid #2a323c; border-radius: 10px; padding: 14px 16px;
          cursor: pointer; transition: border-color .15s; }
.dp-kpi:hover { border-color: #3b4a5c; }
.dp-kpi.sel { border-color: #2f81f7; box-shadow: 0 0 0 1px rgba(47,129,247,.35) inset; }
.dp-k-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.dp-k-nome { font-size: 12px; color: #8b98a5; }
.dp-tag { font-size: 10px; font-weight: 600; letter-spacing: .05em; padding: 1px 8px;
          border: 1px solid; border-radius: 999px; white-space: nowrap; }
.dp-k-val { font-size: 32px; font-weight: 650; letter-spacing: -.02em; color: #e6edf3; margin: 8px 0 6px; line-height: 1.05; }
.dp-k-val small { font-size: 14px; font-weight: 500; color: #8b98a5; margin-left: 4px; }
.dp-k-rod { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.dp-delta { font-weight: 600; padding: 1px 7px; border-radius: 6px; }
.dp-delta.up { color: #79c0ff; background: rgba(88,166,255,.12); }
.dp-delta.down { color: #9fb3c8; background: rgba(139,152,165,.12); }
.dp-delta.nd { color: #5c6773; }
.dp-vs { color: #5c6773; }

.dp-sec { display: flex; flex-wrap: wrap; gap: 8px 26px; margin: 14px 2px 4px; font-size: 13px; }
.dp-sec-i { display: inline-flex; align-items: baseline; gap: 6px; color: #e6edf3; }
.dp-sec-n { color: #6e7a87; font-size: 12px; }
.dp-sec-i small { color: #8b98a5; }
.dp-sec-r { color: #5c6773; font-size: 11px; }

.dp-graf { margin-top: 14px; background: #1c232c; border: 1px solid #2a323c; border-radius: 10px; padding: 12px 14px 6px; }
.dp-g-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.dp-abas { display: flex; gap: 4px; background: #161b22; border: 1px solid #2a323c; border-radius: 9px; padding: 3px; }
.dp-aba { background: transparent; border: 0; color: #8b98a5; font-size: 12px; padding: 5px 12px; border-radius: 7px; cursor: pointer; }
.dp-aba.on { background: #2f81f7; color: #fff; }
.dp-jans { display: flex; gap: 6px; }
.dp-jan { background: transparent; color: #8b98a5; border: 1px solid #2a323c; border-radius: 999px; padding: 3px 11px; font-size: 12px; cursor: pointer; }
.dp-jan.on { color: #79c0ff; border-color: #2f81f7; background: rgba(47,129,247,.14); }
.dp-leg { display: flex; flex-wrap: wrap; gap: 14px; margin: 10px 2px 0; font-size: 12px; color: #8b98a5; }
.dp-leg i { display: inline-block; width: 10px; height: 3px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }
.dp-leg-lim { margin-left: auto; color: #5c6773; }

.dp-svg { position: relative; height: 280px; margin-top: 4px; }
.dp-grade { stroke: #222a33; stroke-width: 1; }
.dp-eixo { fill: #5c6773; font-size: 10px; }
.dp-lim { stroke-width: 1; stroke-dasharray: 5 5; }
.dp-lim.at { stroke: rgba(245,158,11,.45); }
.dp-lim.cr { stroke: rgba(239,68,68,.45); }
.dp-cursor { stroke: #8b98a5; stroke-width: 1; stroke-dasharray: 3 3; }
.dp-vazio { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #5c6773; font-size: 13px; }
.dp-dica { position: absolute; top: 10px; min-width: 190px; background: #161b22; border: 1px solid #2a323c;
           border-radius: 10px; padding: 8px 12px; box-shadow: 0 8px 24px rgba(0,0,0,.5); pointer-events: none; }
.dp-d-t { font-size: 11px; color: #6e7a87; margin-bottom: 4px; }
.dp-d-l { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #8b98a5; }
.dp-d-l i { width: 8px; height: 8px; border-radius: 50%; }
.dp-d-l b { margin-left: auto; color: #e6edf3; font-size: 14px; }
.dp-d-l small { color: #8b98a5; font-weight: 400; font-size: 11px; }

@media (max-width: 760px) {
  .dp-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dp-k-val { font-size: 26px; }
}
</style>
"""

DET_LATERAL = r"""
<template>
  <div class="dl" v-if="l">
    <div class="dl-cab">
      <div class="dl-nome">{{ l.nome }}</div>
      <div class="dl-local" v-if="l.local">{{ l.local }}</div>
      <span class="dl-pill" :class="l.estado">{{ ROT[l.estado] }}</span>
      <div class="dl-mot" v-if="l.motivos">{{ l.motivos }}</div>
    </div>

    <div v-if="l.partes.length" class="dl-sec">
      <div class="dl-tit">Partes</div>
      <div v-for="p in l.partes" :key="p.nome" class="dl-parte">
        <i class="dl-bola" :class="p.estado"></i>
        <span class="dl-pn">{{ p.nome }}</span>
        <span v-if="p.tag" class="dl-ptag">{{ p.tag }}</span>
        <span class="dl-pe" :class="p.estado">{{ ROT[p.estado] }}</span>
      </div>
    </div>

    <div v-if="l.tem_inversor" class="dl-sec">
      <div class="dl-tit">Falhas do inversor</div>
      <div class="dl-falhas">
        <div class="dl-f" :class="{ ativa: l.falha }">
          <span class="dl-fr">{{ l.falha ? '⚠ Falha ativa' : '✓ Falha ativa' }}</span>
          <b>{{ l.falha ? l.falha.cod : 'nenhuma' }}</b>
          <span class="dl-ft">{{ l.falha ? l.falha.txt : 'drive sem falha agora' }}</span>
        </div>
        <div class="dl-f">
          <span class="dl-fr">Última falha</span>
          <b>{{ l.ultima ? l.ultima.cod : '—' }}</b>
          <span class="dl-ft">{{ l.ultima ? l.ultima.txt : 'sem histórico' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  data () {
    return { l: null,
             ROT: { normal: 'OK', atencao: 'ATENÇÃO', critico: 'CRÍTICO', sem_dados: 'SEM DADOS' } }
  },
  watch: {
    msg: { immediate: true,
           handler (m) { const p = (m && m.payload) || {}; if (p.lateral) { this.l = p.lateral; } } }
  }
}
</script>

<style scoped>
.dl-cab { padding-bottom: 12px; border-bottom: 1px solid #222a33; }
.dl-nome { font-size: 17px; font-weight: 650; color: #e6edf3; letter-spacing: -.01em; }
.dl-local { font-size: 12px; color: #6e7a87; margin: 2px 0 8px; }
.dl-pill { display: inline-block; font-size: 11px; font-weight: 650; letter-spacing: .05em;
           padding: 3px 10px; border-radius: 999px; }
.dl-pill.normal { color: #8bb4e8; background: rgba(88,166,255,.10); }
.dl-pill.atencao { color: #f59e0b; background: rgba(245,158,11,.12); }
.dl-pill.critico { color: #ef4444; background: rgba(239,68,68,.12); }
.dl-pill.sem_dados { color: #8b98a5; background: rgba(139,152,165,.12); }
.dl-mot { font-size: 12px; color: #8b98a5; margin-top: 8px; line-height: 1.4; }

.dl-sec { padding-top: 12px; }
.dl-tit { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #5c6773; margin-bottom: 8px; }
.dl-parte { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 5px 0; }
.dl-bola { width: 7px; height: 7px; border-radius: 50%; flex: none; background: #58a6ff; }
.dl-bola.atencao { background: #f59e0b; } .dl-bola.critico { background: #ef4444; }
.dl-bola.sem_dados { background: transparent; border: 1.5px solid #6e7a87; }
.dl-pn { color: #e6edf3; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dl-ptag { font-size: 11px; color: #79c0ff; border: 1px solid #2a3a52; border-radius: 999px; padding: 0 7px; }
.dl-pe { font-size: 11px; color: #6e7a87; }
.dl-pe.atencao { color: #f59e0b; } .dl-pe.critico { color: #ef4444; }

.dl-falhas { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.dl-f { background: #1c232c; border: 1px solid #2a323c; border-radius: 10px; padding: 10px 12px;
        display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.dl-f.ativa { background: rgba(239,68,68,.08); border-color: rgba(239,68,68,.45); }
.dl-fr { font-size: 11px; color: #6e7a87; }
.dl-f b { font-size: 20px; color: #e6edf3; }
.dl-f.ativa b { color: #ef4444; }
.dl-ft { font-size: 11px; color: #8b98a5; line-height: 1.3; }
</style>
"""
