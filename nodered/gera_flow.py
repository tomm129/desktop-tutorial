#!/usr/bin/env python3
"""Gera o nodered/flows.json (Dashboard 2.0) do projeto de monitoramento.

Escrever 700 linhas de JSON na mao e um convite a erro; aqui o fluxo e
descrito em Python e serializado. Rode e depois importe o resultado.
"""
import json
import sys

# --- Paleta validada (scripts/validate_palette.js) --------------------
# Categorica, em ordem fixa: a cor segue o ATIVO, nunca a posicao na lista.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
# Status: paleta reservada, nunca usada para serie.
STATUS = {"good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b"}

BASE, TEMA, PAGINA = "ui_base", "ui_tema", "pg_monitor"
G_ATIVOS, G_ALARMES = "grp_ativos", "grp_alarmes"
G_TEMP, G_VIB, G_CORR = "grp_temp", "grp_vib", "grp_corr"
G_DETALHE, G_CMD = "grp_detalhe", "grp_cmd"

flows = []


def no(**kw):
    flows.append(kw)
    return kw["id"]


# =====================================================================
#  Aba, broker e infraestrutura do dashboard
# =====================================================================
no(id="flow_monitor", type="tab", label="Monitoramento", disabled=False,
   info="Monitoramento de corrente, temperatura e vibracao.\n"
        "Dashboard em /dashboard")

no(id="broker_local", type="mqtt-broker", name="Mosquitto local",
   broker="localhost", port="1883", clientid="", autoConnect=True,
   usetls=False, protocolVersion="4", keepalive="60", cleansession=True,
   birthTopic="", birthQos="0", birthPayload="",
   closeTopic="", closeQos="0", closePayload="",
   willTopic="", willQos="0", willPayload="")

no(id=BASE, type="ui-base", name="Monitoramento", path="/dashboard",
   appIcon="", includeClientData=True, acceptsClientConfig=[
       "ui-notification", "ui-control"],
   showPathInSidebar=False, headerContent="page", navigationStyle="default",
   titleBarStyle="default", showReconnectNotification=True,
   notificationDisplayTime="5", showDisconnectNotification=True,
   allowInstall=True)

no(id=TEMA, type="ui-theme", name="Industrial",
   colors={"surface": "#fafafa", "primary": "#2a78d6", "bgPage": "#f1f1ee",
           "groupBg": "#ffffff", "groupOutline": "#d8d7d0"},
   sizes={"density": "default", "pagePadding": "12px", "groupGap": "12px",
          "groupBorderRadius": "4px", "widgetGap": "12px"})

no(id=PAGINA, type="ui-page", name="Monitoramento", ui=BASE, path="/monitor",
   icon="gauge", layout="grid", theme=TEMA, order=1, className="",
   visible=True, disabled=False,
   breakpoints=[{"name": "Default", "px": "0", "cols": "3"},
                {"name": "Tablet", "px": "576", "cols": "6"},
                {"name": "Small Desktop", "px": "768", "cols": "9"},
                {"name": "Desktop", "px": "1024", "cols": "12"}])


def grupo(gid, nome, largura, ordem, altura=1):
    no(id=gid, type="ui-group", name=nome, page=PAGINA, width=str(largura),
       height=str(altura), order=ordem, showTitle=True, className="",
       visible=True, disabled=False, groupType="default")


# A altura dos grupos de grafico precisa caber o plot MAIS a faixa do eixo X;
# com altura 1 o grafico virava um risco e o eixo sumia.
grupo(G_ATIVOS,  "Ativos",                12, 1)
grupo(G_ALARMES, "Alarmes",               12, 2)
grupo(G_DETALHE, "Detalhe do ativo",       6, 3, altura=3)
grupo(G_CMD,     "Comandos",               6, 4, altura=3)
grupo(G_TEMP,    "Temperatura (°C)",       6, 5, altura=7)
grupo(G_VIB,     "Vibracao RMS (g)",       6, 6, altura=7)
grupo(G_CORR,    "Corrente (A)",          12, 7, altura=7)

# =====================================================================
#  Ingestao: tres topicos alimentam UM registro em flow context
# =====================================================================
no(id="mqtt_telemetria", type="mqtt in", z="flow_monitor",
   name="telemetria de campo", topic="monitoramento/+/telemetria",
   qos="0", datatype="auto", broker="broker_local", nl=False, rap=True,
   rh=0, inputs=0, x=140, y=100, wires=[["parse_json"]])

no(id="parse_json", type="json", z="flow_monitor", name="", property="payload",
   action="obj", pretty=False, x=330, y=100, wires=[["reg_telemetria"]])

no(id="reg_telemetria", type="function", z="flow_monitor",
   name="registrar telemetria", outputs=2, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=500, y=100,
   wires=[["chart_temp"], ["chart_vib"]],
   func=r"""
// Guarda a ultima leitura de cada ativo num registro unico (flow context)
// e repassa os valores para os graficos.
//
// msg.topic vira o device_id: e ele que separa as series no grafico, o que
// faz o dashboard funcionar com N ativos em vez de um so.
const p = msg.payload || {};
const id = p.device_id;
if (!id) { node.warn('telemetria sem device_id, descartada'); return null; }

const ativos = flow.get('ativos') || {};
const a = ativos[id] || { id: id };

a.visto_em = Date.now();

// null explicito quando o sensor falhou -- a UI mostra FALHA, e nao o
// ultimo valor bom congelado, que leria como "esta tudo bem".
a.temperatura_c = (p.temperatura_c === undefined || p.temperatura_c === null)
    ? null : p.temperatura_c;

if (p.vibracao) {
    a.vib_rms_g  = p.vibracao.rms_g  ?? null;
    a.vib_pico_g = p.vibracao.pico_g ?? null;
    a.fs_hz      = p.vibracao.fs_hz  ?? null;
} else {
    a.vib_rms_g = null;
}
if (p.rede) { a.rssi_dbm = p.rede.rssi_dbm ?? null; }

ativos[id] = a;
flow.set('ativos', ativos);

const temp = (a.temperatura_c === null) ? null : { topic: id, payload: a.temperatura_c };
const vib  = (a.vib_rms_g === null)     ? null : { topic: id, payload: a.vib_rms_g };
return [temp, vib];
""")

no(id="mqtt_corrente", type="mqtt in", z="flow_monitor",
   name="corrente do PowerFlex 525", topic="monitoramento/+/corrente",
   qos="0", datatype="auto", broker="broker_local", nl=False, rap=True,
   rh=0, inputs=0, x=140, y=180, wires=[["reg_corrente"]])

no(id="reg_corrente", type="function", z="flow_monitor",
   name="registrar corrente", outputs=1, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=500, y=180,
   wires=[["chart_corr"]],
   func=r"""
// O sidecar pycomm3 publica {"corrente_a": <n>, "ts": <epoch_ms>}.
//
// Nao confie no datatype do no MQTT: dependendo da versao e do que chega,
// o payload pode vir objeto ja parseado, string JSON ou Buffer. Tratar os
// tres aqui e mais barato que descobrir depois que a corrente sumiu.
let v = msg.payload;

if (Buffer.isBuffer(v)) { v = v.toString('utf8'); }
if (typeof v === 'string') {
    try { v = JSON.parse(v); } catch (e) { /* pode ser numero puro */ }
}
if (v && typeof v === 'object') { v = v.corrente_a; }

v = Number(v);
if (!isFinite(v)) {
    node.warn('payload de corrente ilegivel: ' + JSON.stringify(msg.payload));
    return null;
}

const id = (msg.topic || '').split('/')[1] || 'powerflex';
const ativos = flow.get('ativos') || {};
const a = ativos[id] || { id: id };
a.corrente_a = v;
a.corrente_vista_em = Date.now();
a.visto_em = Date.now();
ativos[id] = a;
flow.set('ativos', ativos);

return { topic: id, payload: Math.round(v * 100) / 100 };
""")

no(id="mqtt_status", type="mqtt in", z="flow_monitor",
   name="status de campo (LWT)", topic="monitoramento/+/status",
   qos="0", datatype="utf8", broker="broker_local", nl=False, rap=True,
   rh=0, inputs=0, x=140, y=260, wires=[["reg_status"]])

no(id="reg_status", type="function", z="flow_monitor",
   name="registrar status", outputs=0, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=500, y=260, wires=[],
   func=r"""
// online/offline vindo do LWT. O broker publica 'offline' sozinho se o
// dispositivo cair, entao isso e mais confiavel que so olhar o silencio.
const id = (msg.topic || '').split('/')[1];
if (!id) { return null; }

const ativos = flow.get('ativos') || {};
const a = ativos[id] || { id: id };
a.conexao = String(msg.payload).trim();
ativos[id] = a;
flow.set('ativos', ativos);
return null;
""")

# =====================================================================
#  Renderizador: um so lugar decide estado, cor e texto
# =====================================================================
no(id="tick", type="inject", z="flow_monitor", name="a cada 2s",
   props=[{"p": "payload"}], repeat="2", crontab="", once=True,
   onceDelay="1", topic="", payload="", payloadType="date",
   x=140, y=380, wires=[["montar_painel"]])

no(id="montar_painel", type="function", z="flow_monitor",
   name="montar painel", outputs=3, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=350, y=380,
   wires=[["tabela_ativos"], ["txt_alarmes"], ["stat_tiles"]],
   func=r"""
// Unico ponto que decide estado, cor e texto -- se os limites mudarem,
// mudam aqui e valem para a tabela, os alarmes e os medidores.

// ---- Cadastro de ativos (hierarquico) --------------------------------
// Dois problemas resolvidos aqui:
//
// 1. Um mesmo equipamento manda dado por DOIS caminhos -- o ESP32
//    (temperatura + vibracao) e o inversor (corrente), cada um com seu
//    device_id. Sem mapeamento ele apareceria em duas linhas, cada uma
//    sem metade das grandezas.
//
// 2. Um ativo principal (uma linha, uma prensa, um conjunto) costuma ter
//    VARIOS ESP32 dentro dele -- um por motor, por bomba, por redutor.
//    Sao SUB-ATIVOS: cada um tem leitura propria, mas quem opera pergunta
//    "a Linha 1 esta bem?", nao "o ESP32 de numero 7 esta bem?".
//
// O painel entao mostra dois niveis: o ativo principal com o estado
// consolidado (o PIOR entre suas partes, e o valor mais alto de cada
// grandeza) e, abaixo, cada parte com seu proprio numero.
//
// Deixe VAZIO para descoberta automatica: cada device_id vira uma linha
// solta. E o modo util enquanto voce ainda esta montando a instalacao.
//
// A TAG vive AQUI, nao no firmware (mesmo criterio de docs/visualizacao.md):
// trocar um ESP32 queimado e editar uma linha deste cadastro, sem regravar
// nada e sem perder o historico do ativo.
const ATIVOS = {
    // 'U1': {
    //     descricao: 'Linha de Transporte 1',
    //     partes: {
    //         'Motor principal':  { esp32: 'motor-01', inversor: 'powerflex-01' },
    //         'Bomba hidraulica': { esp32: 'motor-02' },
    //         'Redutor':          { esp32: 'motor-03' }
    //     }
    // },
};

// ---- Limites. Calibre com o equipamento em condicao normal. ----------
const LIM = {
    temperatura_c: { atencao: 60,  critico: 75,   nome: 'Temperatura', un: '°C' },
    vib_rms_g:     { atencao: 0.5, critico: 1.0,  nome: 'Vibracao',    un: 'g'  },
    corrente_a:    { atencao: 9.0, critico: 11.0, nome: 'Corrente',    un: 'A'  }
};

// Sem telemetria por mais que isso, o ativo entra em SEM DADOS. Tem de ser
// maior que o intervalo de publicacao (5s no firmware) com folga, senao
// pisca a cada atraso de rede.
const SEM_DADOS_MS = 20000;

// Paleta de status reservada -- nunca usada para identificar serie.
const COR = { normal: '#0ca30c', atencao: '#fab219', critico: '#d03b3b',
              sem_dados: '#898781' };
// A cor nunca carrega o significado sozinha: sempre vem com simbolo e texto.
const SIMB = { normal: '●', atencao: '▲', critico: '■', sem_dados: '○' };
const ROTULO = { normal: 'OK', atencao: 'ATENCAO', critico: 'CRITICO',
                 sem_dados: 'SEM DADOS' };

const PIOR = { sem_dados: 0, normal: 1, atencao: 2, critico: 3 };

function avaliar(valor, lim) {
    if (valor === null || valor === undefined) { return null; }
    if (valor >= lim.critico) { return 'critico'; }
    if (valor >= lim.atencao) { return 'atencao'; }
    return 'normal';
}

function ha_quanto(ms) {
    if (!ms) { return '--'; }
    const s = Math.floor((Date.now() - ms) / 1000);
    if (s < 60)   { return s + 's'; }
    if (s < 3600) { return Math.floor(s / 60) + 'min'; }
    return Math.floor(s / 3600) + 'h';
}

// Tres estados distintos, e a diferenca importa:
//   '--'    o ativo nao tem esse sensor (nunca reportou)  -> nao e problema
//   'FALHA' reportou null: o sensor existe e nao respondeu -> E problema
//   valor   leitura boa
function fmt(v, casas, un) {
    if (v === undefined) { return '--'; }
    if (v === null) { return 'FALHA'; }
    return v.toFixed(casas) + ' ' + un;
}

const registro = flow.get('ativos') || {};

// Junta os device_id de UMA parte (o ESP32 e o inversor dela).
function juntar_parte(chave, rotulo, cfg, nivel) {
    const esp = registro[cfg.esp32] || {};
    const inv = registro[cfg.inversor] || {};
    return {
        chave: chave,
        rotulo: rotulo,
        nivel: nivel,
        temperatura_c: esp.temperatura_c,
        vib_rms_g: esp.vib_rms_g,
        corrente_a: inv.corrente_a,
        // A parte so esta muda quando TODAS as suas fontes estao mudas.
        visto_em: Math.max(esp.visto_em || 0, inv.visto_em || 0),
        conexao: (esp.conexao === 'offline' || inv.conexao === 'offline')
            ? 'offline' : 'online'
    };
}

// Consolida N partes num ativo principal: cada grandeza vira o valor mais
// alto entre as partes (o ponto mais quente da linha, a maior vibracao),
// que e o numero pelo qual o ativo deve ser cobrado.
function consolidar_pai(tag, cfg, partes) {
    function pior(campo) {
        // undefined = nenhuma parte tem o sensor; null = alguma tem e falhou.
        let melhor;
        let houve_falha = false;
        for (const p of partes) {
            const v = p[campo];
            if (v === undefined) { continue; }
            if (v === null) { houve_falha = true; continue; }
            melhor = (melhor === undefined) ? v : Math.max(melhor, v);
        }
        if (melhor !== undefined) { return melhor; }
        return houve_falha ? null : undefined;
    }
    return {
        chave: tag,
        rotulo: cfg.descricao ? (tag + ' — ' + cfg.descricao) : tag,
        nivel: 0,
        eh_pai: true,
        temperatura_c: pior('temperatura_c'),
        vib_rms_g: pior('vib_rms_g'),
        corrente_a: pior('corrente_a'),
        visto_em: Math.max.apply(null, partes.map(function (p) { return p.visto_em || 0; })),
        conexao: partes.some(function (p) { return p.conexao === 'offline'; })
            ? 'offline' : 'online'
    };
}

function consolidar() {
    const tags = Object.keys(ATIVOS);

    if (!tags.length) {
        // Sem cadastro: cada device_id vira uma linha solta. Modo util
        // enquanto a instalacao ainda esta sendo montada.
        return Object.keys(registro).sort().map(function (id) {
            return Object.assign({ chave: id, rotulo: id, nivel: 0 }, registro[id]);
        });
    }

    const saida = [];
    for (const tag of tags.sort()) {
        const cfg = ATIVOS[tag];

        // Ativo sem 'partes': trata como equipamento unico (um nivel so).
        if (!cfg.partes) {
            saida.push(juntar_parte(tag,
                cfg.descricao ? (tag + ' — ' + cfg.descricao) : tag, cfg, 0));
            continue;
        }

        const nomes = Object.keys(cfg.partes);
        const partes = nomes.map(function (nome) {
            return juntar_parte(tag + '/' + nome, nome, cfg.partes[nome], 1);
        });

        saida.push(consolidar_pai(tag, cfg, partes));
        for (const p of partes) { saida.push(p); }
    }
    return saida;
}

const lista = consolidar();
const agora = Date.now();

// O dropdown precisa das mesmas chaves da tabela. Publicamos aqui para o
// cadastro ATIVOS existir num lugar so. O recuo do sub-ativo vai junto no
// rotulo, senao a lista perde a hierarquia.
flow.set('opcoes_ativos', lista.map(function (x) {
    return { value: x.chave,
             label: (x.nivel > 0 ? '   └ ' : '') + x.rotulo };
}));

const linhas = [];
const alarmes = [];
let pai_atual = '';

for (const a of lista) {
    const id = a.rotulo;
    const mudo = (agora - (a.visto_em || 0)) > SEM_DADOS_MS;
    const offline = a.conexao === 'offline';

    let estado = 'normal';
    const motivos = [];

    if (mudo || offline) {
        estado = 'sem_dados';
        motivos.push(offline ? 'dispositivo offline (LWT)' : 'sem telemetria');
    } else {
        for (const campo of Object.keys(LIM)) {
            const lim = LIM[campo];
            const v = a[campo];
            if (v === undefined) { continue; }   // ativo nao tem esse sensor
            if (v === null) {
                // Reportou null: o sensor existe e nao respondeu. Isso e
                // ausencia de informacao, nao "esta tudo bem" -- por isso
                // vira ATENCAO, e nao passa despercebido.
                if (PIOR.atencao > PIOR[estado]) { estado = 'atencao'; }
                motivos.push(lim.nome + ' sem leitura');
                continue;
            }
            const nivel = avaliar(v, lim);
            if (PIOR[nivel] > PIOR[estado]) { estado = nivel; }
            if (nivel !== 'normal') {
                motivos.push(lim.nome + ' ' + ROTULO[nivel].toLowerCase() +
                             ': ' + v + lim.un);
            }
        }
    }

    // Sub-ativo entra recuado, para a hierarquia se ler de relance.
    const nome = (a.nivel > 0) ? ('    └ ' + id) : id;

    linhas.push({
        Ativo: nome,
        Temperatura: fmt(a.temperatura_c, 1, '°C'),
        'Vibracao RMS': fmt(a.vib_rms_g, 3, 'g'),
        Corrente: fmt(a.corrente_a, 2, 'A'),
        Estado: SIMB[estado] + ' ' + ROTULO[estado],
        'Visto ha': ha_quanto(a.visto_em)
    });

    // O ativo principal so vira alarme proprio quando ele mesmo esta mudo.
    // Se o problema esta numa parte, quem alarma e a parte -- senao a mesma
    // ocorrencia apareceria duas vezes, com o pai repetindo o pior filho.
    const so_consolidado = a.eh_pai && estado !== 'sem_dados';
    if (estado !== 'normal' && !so_consolidado) {
        alarmes.push({ id: a.nivel > 0 ? (pai_atual + ' / ' + id) : id,
                       estado: estado, motivos: motivos });
    }
    if (a.nivel === 0) { pai_atual = id; }
}

// ---- Saida 1: tabela (tambem e a "table view" que garante acesso aos
//      valores sem depender de cor) ------------------------------------
const m1 = { payload: linhas };

// ---- Saida 2: alarmes -------------------------------------------------
let html;
// Conta so os ativos principais: dizer "12 ativos" quando sao 3 linhas com
// 4 motores cada da uma nocao errada do tamanho da planta.
const n_pai = lista.filter(function (x) { return x.nivel === 0; }).length;
if (!lista.length) {
    html = '<div style="color:#898781">Aguardando o primeiro ativo publicar...</div>';
} else if (!alarmes.length) {
    html = '<div style="color:' + COR.normal + '">' + SIMB.normal +
           ' Todos os ' + n_pai + ' ativos em condicao normal</div>';
} else {
    html = alarmes.map(function (al) {
        return '<div style="color:' + COR[al.estado] + '">' + SIMB[al.estado] +
               ' <b>' + al.id + '</b> — ' + al.motivos.join(' | ') + '</div>';
    }).join('');
}
const m2 = { payload: html };

// ---- Saida 3: stat tiles do ativo selecionado -------------------------
// Um painel de detalhe mostra UM ativo; com varios em tela os valores se
// sobrescreveriam alternadamente. Por isso segue a selecao do dropdown.
const sel = flow.get('ativo_sel');
const alvo = lista.find(function (x) { return x.chave === sel; }) || lista[0];
if (!alvo) { return [m1, m2, null]; }

function tile(nome, campo, casas, un) {
    const v = alvo[campo];
    const lim = LIM[campo];

    if (v === undefined) {
        return { nome: nome, texto: '--', un: '', pct: 0,
                 cor: COR.sem_dados, simb: SIMB.sem_dados, rotulo: 'sem sensor' };
    }
    if (v === null) {
        return { nome: nome, texto: 'FALHA', un: '', pct: 0,
                 cor: COR.atencao, simb: SIMB.atencao, rotulo: 'sem leitura' };
    }
    const nivel = avaliar(v, lim);
    // A barra e um medidor contra o limite critico: cheia = no limite.
    const pct = Math.max(0, Math.min(100, (v / lim.critico) * 100));
    return { nome: nome, texto: v.toFixed(casas), un: un, pct: pct,
             cor: COR[nivel], simb: SIMB[nivel], rotulo: ROTULO[nivel] };
}

const m3 = { payload: [
    tile('Temperatura',  'temperatura_c', 1, '°C'),
    tile('Vibracao RMS', 'vib_rms_g',     3, 'g'),
    tile('Corrente',     'corrente_a',    2, 'A')
], topic: alvo.chave };

return [m1, m2, m3];
""")

# =====================================================================
#  Widgets
# =====================================================================
no(id="tabela_ativos", type="ui-table", z="flow_monitor", group=G_ATIVOS,
   name="tabela de ativos", label="", order=1, width="0", height="0",
   maxrows=0, passthru=False, autocols=True, columns=[],
   # 'none' desliga o modo cartao: num painel a tabela e sempre tabela,
   # senao cada ativo virava um bloco empilhado de chave/valor.
   mobileBreakpoint="", mobileBreakpointType="none",
   showSearch=False, deselect=True,
   action="replace", selectionType="none", className="",
   x=620, y=340, wires=[[]])

no(id="txt_alarmes", type="ui-text", z="flow_monitor", group=G_ALARMES,
   order=1, width="0", height="0", name="alarmes", label="",
   format="{{msg.payload}}", layout="row-left", style=False, font="",
   fontSize=16, color="#717171", wrapText=True, className="",
   x=620, y=380, wires=[])


# Painel de detalhe: STAT TILES, nao medidores de ponteiro.
#
# Um ponteiro nao sabe dizer "nao tenho esse sensor" -- ele cai em zero, e
# "0 A" num painel industrial le como "motor parado", que e uma afirmacao
# forte e errada. O stat tile mostra "--" e resolve isso. Cada tile traz a
# barra de faixa (medidor contra o limite), o valor e o estado com simbolo
# + texto, para a cor nunca ser o unico portador do significado.
STAT_TILES = r"""
<template>
    <div class="tiles">
        <div v-for="t in tiles" :key="t.nome" class="tile">
            <div class="rot">{{ t.nome }}</div>
            <div class="val" :class="{ vazio: t.texto === '--' || t.texto === 'FALHA' }">
                {{ t.texto }}<span v-if="t.un" class="un">{{ t.un }}</span>
            </div>
            <div class="trilho">
                <div class="preenche" :style="{ width: t.pct + '%', background: t.cor }"></div>
            </div>
            <div class="estado" :style="{ color: t.cor }">{{ t.simb }} {{ t.rotulo }}</div>
        </div>
    </div>
</template>

<script>
export default {
    data () { return { tiles: [] } },
    watch: {
        msg: {
            immediate: true,
            handler (m) { if (m && m.payload) { this.tiles = m.payload } }
        }
    }
}
</script>

<style scoped>
.tiles { display: flex; gap: 12px; flex-wrap: wrap; }
.tile  { flex: 1 1 120px; min-width: 110px; }
.rot   { font-size: 12px; color: #52514e; margin-bottom: 2px; }
/* Figuras proporcionais no numero grande: tabular deixa solto nesse tamanho */
.val   { font-size: 30px; line-height: 1.1; color: #0b0b0b;
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.val.vazio { color: #898781; font-size: 22px; }
.un    { font-size: 13px; color: #52514e; margin-left: 4px; }
.trilho   { height: 4px; background: #e1e0d9; border-radius: 2px; margin: 6px 0 4px; }
.preenche { height: 100%; border-radius: 2px; transition: width .3s ease; }
.estado   { font-size: 12px; }
</style>
"""

no(id="stat_tiles", type="ui-template", z="flow_monitor", group=G_DETALHE,
   name="stat tiles do ativo", order=2, width="6", height="4",
   head="", format=STAT_TILES, storeOutMessages=True, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=420, wires=[[]])


def grafico(nid, grupo_id, rotulo, eixo_y, ymin, ymax, largura=6):
    # O WIDGET precisa da propria altura: so aumentar a do grupo nao basta,
    # o grafico fica com altura zero e vira um risco, sem eixo X visivel.
    no(id=nid, type="ui-chart", z="flow_monitor", group=grupo_id,
       name=rotulo, label="", order=1, chartType="line",
       category="topic", categoryType="msg",
       xAxisLabel="", xAxisProperty="", xAxisPropertyType="timestamp",
       xAxisType="time", xAxisFormat="", xAxisFormatType="auto",
       yAxisLabel=eixo_y, yAxisProperty="payload", yAxisPropertyType="msg",
       ymin=ymin, ymax=ymax, xmin="", xmax="", bins=100, action="append",
       stackSeries=False, pointShape="circle", pointRadius=0,
       showLegend=True, removeOlder="30", removeOlderUnit="60",
       removeOlderPoints="", colors=SERIES, textColor=["#52514e"],
       textColorDefault=False, gridColor=["#e1e0d9"], gridColorDefault=False,
       width=str(largura), height="6", className="", interpolation="linear",
       x=820, y=100, wires=[[]])


grafico("chart_temp", G_TEMP,  "Temperatura",  "°C", "", "")
grafico("chart_vib",  G_VIB,   "Vibracao RMS", "g",  "0", "")
grafico("chart_corr", G_CORR,  "Corrente",     "A",  "0", "", largura=12)

# =====================================================================
#  Comandos: escolher o ativo e mandar publicar
# =====================================================================
no(id="dd_ativo", type="ui-dropdown", z="flow_monitor", group=G_CMD,
   name="seletor de ativo", label="Ativo", tooltip="", order=1,
   width="0", height="0", passthru=False, multiple=False, chips=False,
   clearable=False, topic="topic", topicType="msg", className="",
   options=[], payload="", payloadType="str", x=140, y=480,
   wires=[["sel_ativo"]])

no(id="sel_ativo", type="function", z="flow_monitor",
   name="guardar selecao", outputs=0, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=340, y=480, wires=[],
   func=r"""
flow.set('ativo_sel', msg.payload);
return null;
""")

# O dropdown precisa da lista de ativos; ela vem do mesmo registro.
no(id="tick_opcoes", type="inject", z="flow_monitor", name="lista de ativos",
   props=[{"p": "payload"}], repeat="5", crontab="", once=True,
   onceDelay="2", topic="", payload="", payloadType="date",
   x=140, y=540, wires=[["montar_opcoes"]])

no(id="montar_opcoes", type="function", z="flow_monitor",
   name="montar opcoes", outputs=1, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=340, y=540,
   wires=[["dd_ativo"]],
   func=r"""
// Alimenta o dropdown com as opcoes que o renderizador publicou -- assim
// o cadastro ATIVOS fica definido num lugar so ("montar painel").
//
// Reenvia sempre, de proposito: o widget so guarda o que recebe DEPOIS de
// existir, e uma versao anterior guardava a lista para nao repetir -- o
// resultado era um dropdown eternamente vazio quando a pagina abria antes
// da primeira leitura chegar.
const opcoes = flow.get('opcoes_ativos') || [];
if (!opcoes.length) { return null; }

if (!flow.get('ativo_sel')) { flow.set('ativo_sel', opcoes[0].value); }

return { ui_update: { options: opcoes }, payload: flow.get('ativo_sel') };
""")

no(id="btn_publicar", type="ui-button", z="flow_monitor", group=G_CMD,
   name="publicar agora", label="Publicar agora", order=2, width="0",
   height="0", tooltip="Forca uma leitura imediata no ativo selecionado",
   color="", bgcolor="", className="", icon="", iconPosition="left",
   payload="", payloadType="str", topic="topic", topicType="msg",
   buttonColor="", textColor="", iconColor="", enableClick=True,
   enablePointerdown=False, pointerdownPayload="",
   pointerdownPayloadType="str", enablePointerup=False,
   pointerupPayload="", pointerupPayloadType="str",
   x=140, y=600, wires=[["monta_cmd"]])

no(id="monta_cmd", type="function", z="flow_monitor", name="monta comando",
   outputs=1, timeout=0, noerr=0, initialize="", finalize="", libs=[],
   x=340, y=600, wires=[["mqtt_cmd"]],
   func=r"""
// Manda para o ativo SELECIONADO no dropdown, em vez de um id fixo no codigo.
const id = flow.get('ativo_sel');
if (!id) { node.warn('nenhum ativo selecionado'); return null; }
msg.topic = 'monitoramento/' + id + '/cmd';
msg.payload = JSON.stringify({ comando: 'publicar' });
return msg;
""")

no(id="mqtt_cmd", type="mqtt out", z="flow_monitor", name="comando -> ESP32",
   topic="", qos="1", retain="false", respTopic="", contentType="",
   userProps="", correl="", expiry="", broker="broker_local",
   x=560, y=600, wires=[])

# =====================================================================
if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else "flows.json"
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        json.dump(flows, f, indent=4, ensure_ascii=False)
        f.write("\n")
    print(f"{len(flows)} nos -> {destino}")
