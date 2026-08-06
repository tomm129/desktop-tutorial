#!/usr/bin/env python3
"""Gera o nodered/flows.json (Dashboard 2.0) do projeto de monitoramento.

Escrever 700 linhas de JSON na mao e um convite a erro; aqui o fluxo e
descrito em Python e serializado. Rode e depois importe o resultado.
"""
import json
import sys

# --- Paleta validada (validate_palette.js, modo escuro) ---------------
#
# Tema ESCURO. Os tons nao sao os do tema claro "invertidos": sao os passos
# proprios da mesma familia, escolhidos para a superficie escura e
# validados contra ela (banda de luminosidade, piso de croma, separacao sob
# daltonismo e contraste -- os quatro passam, inclusive o contraste, que no
# tema claro so dava aviso).
#
# Categorica, em ordem fixa: a cor segue o ATIVO, nunca a posicao na lista.
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500",
          "#d55181", "#008300", "#9085e9", "#e66767"]

# Status: paleta reservada, nunca usada para serie. Os mesmos quatro passos
# do tema claro -- todos limpam 3:1 na superficie escura.
STATUS = {"good": "#0ca30c", "warning": "#fab219", "critical": "#d03b3b"}

# Superficies e tinta do tema escuro.
FUNDO_PAGINA = "#0d0d0d"
FUNDO_CARTAO = "#1a1a19"
TINTA_1 = "#ffffff"    # primaria
TINTA_2 = "#c3c2b7"    # secundaria
TINTA_3 = "#898781"    # apagada (eixos, rotulos)
LINHA   = "#2c2c2a"    # grade / divisoria
BORDA   = "#383835"

BASE, TEMA = "ui_base", "ui_tema"

# Duas telas: a visao geral e uma parede de cards (um por ativo principal),
# e o clique num card abre o detalhe daquele ativo.
PAGINA, PAGINA_DET = "pg_visao", "pg_detalhe"

G_RESUMO, G_CARDS = "grp_resumo", "grp_cards"
G_CAB, G_TILES, G_PARTES, G_CMD = "grp_cab", "grp_tiles", "grp_partes", "grp_cmd"
G_TEMP, G_VIB, G_CORR = "grp_temp", "grp_vib", "grp_corr"

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

no(id=TEMA, type="ui-theme", name="Industrial escuro",
   colors={"surface": FUNDO_CARTAO, "primary": SERIES[0],
           "bgPage": FUNDO_PAGINA, "groupBg": FUNDO_CARTAO,
           "groupOutline": BORDA},
   sizes={"density": "default", "pagePadding": "12px", "groupGap": "12px",
          "groupBorderRadius": "4px", "widgetGap": "12px"})

BREAKPOINTS = [{"name": "Default", "px": "0", "cols": "3"},
               {"name": "Tablet", "px": "576", "cols": "6"},
               {"name": "Small Desktop", "px": "768", "cols": "9"},
               {"name": "Desktop", "px": "1024", "cols": "12"}]

no(id=PAGINA, type="ui-page", name="Visao Geral", ui=BASE, path="/visao",
   icon="view-dashboard", layout="grid", theme=TEMA, order=1, className="",
   visible=True, disabled=False, breakpoints=BREAKPOINTS)

no(id=PAGINA_DET, type="ui-page", name="Detalhe", ui=BASE, path="/detalhe",
   icon="magnify", layout="grid", theme=TEMA, order=2, className="",
   visible=True, disabled=False, breakpoints=BREAKPOINTS)


def grupo(gid, nome, largura, ordem, altura=1, pagina=PAGINA, titulo=True):
    no(id=gid, type="ui-group", name=nome, page=pagina, width=str(largura),
       height=str(altura), order=ordem, showTitle=titulo, className="",
       visible=True, disabled=False, groupType="default")


# --- Tela 1: visao geral (a parede de cards) --------------------------
grupo(G_RESUMO, "Resumo",  12, 1, altura=1, titulo=False)
grupo(G_CARDS,  "Ativos",  12, 2, altura=8, titulo=False)

# --- Tela 2: detalhe de um ativo --------------------------------------
# A altura dos grupos de grafico precisa caber o plot MAIS a faixa do eixo X;
# com altura 1 o grafico vira um risco e o eixo some.
grupo(G_CAB,    "",                       12, 1, altura=2, pagina=PAGINA_DET, titulo=False)
grupo(G_TILES,  "Leituras agora",          6, 2, altura=4, pagina=PAGINA_DET)
grupo(G_CMD,    "Comandos",                6, 3, altura=2, pagina=PAGINA_DET)
grupo(G_PARTES, "Partes deste ativo",     12, 4, altura=4, pagina=PAGINA_DET)
grupo(G_TEMP,   "Temperatura (°C)",        6, 5, altura=7, pagina=PAGINA_DET)
grupo(G_VIB,    "Vibracao RMS (g)",        6, 6, altura=7, pagina=PAGINA_DET)
grupo(G_CORR,   "Corrente (A)",           12, 7, altura=7, pagina=PAGINA_DET)

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
   name="telemetria do inversor", topic="monitoramento/+/inversor",
   qos="0", datatype="auto", broker="broker_local", nl=False, rap=True,
   rh=0, inputs=0, x=140, y=180, wires=[["reg_corrente"]])

no(id="reg_corrente", type="function", z="flow_monitor",
   name="registrar corrente", outputs=1, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=500, y=180,
   wires=[["chart_corr"]],
   func=r"""
// O sidecar pycomm3 publica a telemetria do drive: corrente, tensao,
// barramento CC, frequencia, se esta rodando e o codigo de falha.
//
// Nao confie no datatype do no MQTT: dependendo da versao e do que chega,
// o payload pode vir objeto ja parseado, string JSON ou Buffer. Tratar os
// tres aqui e mais barato que descobrir depois que o dado sumiu.
let p = msg.payload;

if (Buffer.isBuffer(p)) { p = p.toString('utf8'); }
if (typeof p === 'string') {
    try { p = JSON.parse(p); } catch (e) { p = Number(p); }
}

// Aceita numero puro (util para testar com mosquitto_pub) tratando-o
// como se fosse so a corrente.
if (typeof p === 'number' && isFinite(p)) { p = { corrente_a: p }; }
if (!p || typeof p !== 'object') {
    node.warn('payload do inversor ilegivel: ' + JSON.stringify(msg.payload));
    return null;
}

const id = (msg.topic || '').split('/')[1] || 'inversor';
const ativos = flow.get('ativos') || {};
const a = ativos[id] || { id: id };

if (typeof p.corrente_a === 'number')    { a.corrente_a    = p.corrente_a; }
if (typeof p.tensao_v === 'number')      { a.tensao_v      = p.tensao_v; }
if (typeof p.dc_bus_v === 'number')      { a.dc_bus_v      = p.dc_bus_v; }
if (typeof p.frequencia_hz === 'number') { a.frequencia_hz = p.frequencia_hz; }
if (typeof p.rodando === 'boolean')      { a.rodando       = p.rodando; }
if (p.falha) {
    a.falha_codigo = p.falha.codigo || 0;
    a.falha_texto  = p.falha.texto || null;
}

a.visto_em = Date.now();
ativos[id] = a;
flow.set('ativos', ativos);

return (typeof a.corrente_a === 'number')
    ? { topic: id, payload: Math.round(a.corrente_a * 100) / 100 }
    : null;
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
   name="montar painel", outputs=5, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=350, y=380,
   wires=[["tabela_ativos"], ["txt_resumo"], ["stat_tiles"],
          ["cards_ativos"], ["cab_detalhe"]],
   func=r"""
// Unico ponto que decide estado, cor e texto -- se os limites mudarem,
// mudam aqui e valem para a tabela, os alarmes e os medidores.

// ---- Cadastro de ativos ----------------------------------------------
// A chave de topo e o ATIVO (o equipamento que a producao conhece pelo
// nome). Dentro dele vem as PARTES -- normalmente um motor por parte, cada
// uma com seu ESP32.
//
// Cada parte declara de onde vem cada numero:
//   esp32         quem manda temperatura e vibracao
//   inversor      device_id do sidecar que le a corrente
//   tag_inversor  como esse inversor e identificado no painel (U1, U2...)
//
// A tag do inversor e so rotulo: e por ela que o eletricista acha o drive
// no painel, entao ela aparece na tela -- mas quem tem estado, historico e
// alarme e o ATIVO e a PARTE, nao o inversor. Um inversor nao "esta
// critico"; quem esta e o motor que ele aciona.
//
// Deixe VAZIO para descoberta automatica: cada device_id vira uma linha
// solta. E o modo util enquanto a instalacao ainda esta sendo montada.
//
// Os nomes vivem AQUI, nao no firmware (mesmo criterio de
// docs/visualizacao.md): trocar um ESP32 queimado e editar uma linha deste
// cadastro, sem regravar nada e sem perder o historico do ativo.
const ATIVOS = {
    // 'Transporte 1': {
    //     partes: {
    //         'Motor 1': { esp32: 'motor-01',
    //                      inversor: 'powerflex-01', tag_inversor: 'U1' },
    //         'Motor 2': { esp32: 'motor-02',
    //                      inversor: 'powerflex-02', tag_inversor: 'U2' }
    //     }
    // },
    // 'Exaustor de Cabine': {
    //     partes: {
    //         'Motor': { esp32: 'motor-03' }   // sem inversor monitorado
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

// Marcha nao e estado de saude: um motor parado nao esta "ruim". Mas e o
// contexto que da sentido aos numeros -- 0,00 A com o motor rodando e
// suspeito; parado, e o esperado.
function marcha_txt(a) {
    if (a.rodando === undefined) { return '--'; }
    if (!a.rodando) { return '■ parado'; }
    const f = (typeof a.frequencia_hz === 'number')
        ? ' (' + a.frequencia_hz.toFixed(1) + ' Hz)' : '';
    return '▶ rodando' + f;
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
        // Procedencia: de onde veio cada numero. E o que o eletricista
        // precisa para achar o drive no painel.
        fonte_esp32: cfg.esp32,
        fonte_inversor: cfg.inversor,
        tag_inversor: cfg.tag_inversor,
        temperatura_c: esp.temperatura_c,
        vib_rms_g: esp.vib_rms_g,
        corrente_a: inv.corrente_a,
        tensao_v: inv.tensao_v,
        dc_bus_v: inv.dc_bus_v,
        frequencia_hz: inv.frequencia_hz,
        rodando: inv.rodando,
        falha_codigo: inv.falha_codigo,
        falha_texto: inv.falha_texto,
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
    // Falha de drive em QUALQUER parte sobe para o ativo -- e a mesma
    // logica do estado: o ativo esta tao bem quanto sua pior parte.
    const com_falha = partes.find(function (p) { return p.falha_codigo; });
    // "Rodando" e verdadeiro se ALGUMA parte esta girando: numa linha com
    // varios motores, um so girando ja significa linha em operacao.
    const algum_rodando = partes.some(function (p) { return p.rodando === true; });
    const sabe_rodando = partes.some(function (p) { return p.rodando !== undefined; });

    return {
        chave: tag,
        rotulo: tag,
        nivel: 0,
        eh_pai: true,
        temperatura_c: pior('temperatura_c'),
        vib_rms_g: pior('vib_rms_g'),
        corrente_a: pior('corrente_a'),
        tensao_v: pior('tensao_v'),
        dc_bus_v: pior('dc_bus_v'),
        frequencia_hz: pior('frequencia_hz'),
        rodando: sabe_rodando ? algum_rodando : undefined,
        falha_codigo: com_falha ? com_falha.falha_codigo : 0,
        falha_texto: com_falha ? com_falha.falha_texto : null,
        visto_em: Math.max.apply(null, partes.map(function (p) { return p.visto_em || 0; })),
        conexao: partes.some(function (p) { return p.conexao === 'offline'; })
            ? 'offline' : 'online'
    };
}

// Quais ESP32 respondem por cada chave -- e o que o botao "Publicar agora"
// precisa para saber a quem mandar o comando.
const esp32_por_chave = {};

function consolidar() {
    const tags = Object.keys(ATIVOS);

    if (!tags.length) {
        // Sem cadastro: cada device_id vira uma linha solta. Modo util
        // enquanto a instalacao ainda esta sendo montada.
        return Object.keys(registro).sort().map(function (id) {
            // Na descoberta automatica a chave JA e o device_id.
            esp32_por_chave[id] = [id];
            return Object.assign({ chave: id, rotulo: id, nivel: 0 }, registro[id]);
        });
    }

    const saida = [];
    for (const tag of tags.sort()) {
        const cfg = ATIVOS[tag];

        // Ativo sem 'partes': trata como equipamento unico (um nivel so).
        if (!cfg.partes) {
            if (cfg.esp32) { esp32_por_chave[tag] = [cfg.esp32]; }
            saida.push(juntar_parte(tag, tag, cfg, 0));
            continue;
        }

        const nomes = Object.keys(cfg.partes);
        const partes = nomes.map(function (nome) {
            const chave = tag + '/' + nome;
            if (cfg.partes[nome].esp32) {
                esp32_por_chave[chave] = [cfg.partes[nome].esp32];
            }
            return juntar_parte(chave, nome, cfg.partes[nome], 1);
        });
        // O ativo principal comanda todas as suas partes de uma vez.
        esp32_por_chave[tag] = nomes
            .map(function (n) { return cfg.partes[n].esp32; })
            .filter(Boolean);

        saida.push(consolidar_pai(tag, cfg, partes));
        for (const p of partes) { saida.push(p); }
    }
    return saida;
}

const lista = consolidar();
flow.set('esp32_por_chave', esp32_por_chave);
const agora = Date.now();


const linhas = [];
const alarmes = [];
const estados = {};
let pai_atual = '';
let pai_chave = '';

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
        // Falha no inversor e CRITICO por definicao: o proprio drive ja
        // decidiu que ha um problema, nao ha limite a comparar.
        if (a.falha_codigo) {
            estado = 'critico';
            motivos.push('inversor em falha F' +
                         String(a.falha_codigo).padStart(3, '0') +
                         (a.falha_texto ? ' — ' + a.falha_texto : ''));
        }

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
        Tensao: fmt(a.tensao_v, 1, 'V'),
        Marcha: marcha_txt(a),
        Inversor: a.tag_inversor || (a.nivel > 0 ? '--' : ''),
        Estado: SIMB[estado] + ' ' + ROTULO[estado],
        'Visto ha': ha_quanto(a.visto_em),
        // Campos de trabalho, retirados antes de exibir: servem para
        // filtrar as partes do ativo aberto na tela de detalhe.
        _chave: a.chave,
        _pai: (a.nivel > 0) ? pai_chave : a.chave
    });

    // Guarda o estado apurado: o card do pai e o cabecalho do detalhe
    // reaproveitam, em vez de recalcular com regra possivelmente diferente.
    estados[a.chave] = { estado: estado, motivos: motivos, item: a };

    // O ativo principal so vira alarme proprio quando ele mesmo esta mudo.
    // Se o problema esta numa parte, quem alarma e a parte -- senao a mesma
    // ocorrencia apareceria duas vezes, com o pai repetindo o pior filho.
    const so_consolidado = a.eh_pai && estado !== 'sem_dados';
    if (estado !== 'normal' && !so_consolidado) {
        alarmes.push({ id: a.nivel > 0 ? (pai_atual + ' / ' + id) : id,
                       estado: estado, motivos: motivos });
    }
    if (a.nivel === 0) { pai_atual = id; pai_chave = a.chave; }
}

// ---- Saida 1: tabela das PARTES do ativo aberto ----------------------
// Na tela de detalhe so interessam as partes daquele ativo.  E tambem a
// "table view" que garante acesso a todo valor sem depender de cor.
const sel = flow.get('ativo_sel');

function limpar(l) {
    const c = Object.assign({}, l);
    delete c._pai; delete c._chave;
    return c;
}
let linhas_det = linhas.filter(function (l) { return l._pai === sel; });
if (!linhas_det.length) { linhas_det = linhas; }
const m1 = { payload: linhas_det.map(limpar) };

// ---- Saida 2: faixa de resumo da visao geral -------------------------
const n_pai = lista.filter(function (x) { return x.nivel === 0; }).length;
let html;
if (!lista.length) {
    html = '<span style="color:#898781">Aguardando o primeiro ativo publicar...</span>';
} else if (!alarmes.length) {
    html = '<span style="color:' + COR.normal + '">' + SIMB.normal +
           ' Todos os ' + n_pai + ' ativos em condicao normal</span>';
} else {
    html = alarmes.map(function (al) {
        return '<span style="color:' + COR[al.estado] + '">' + SIMB[al.estado] +
               ' <b>' + al.id + '</b> — ' + al.motivos.join(' | ') + '</span>';
    }).join('<br>');
}
const m2 = { payload: html };

// ---- Saidas 3..5: a tela de detalhe ----------------------------------
const alvo = lista.find(function (x) { return x.chave === sel; }) || lista[0];
if (!alvo) { return [m1, m2, null, m4_cards(), null]; }

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

// Tensao e barramento CC nao tem limite configurado -- sao leitura de
// referencia, nao criterio de alarme. O tile sem limite so mostra o numero,
// com a barra apagada, para nao sugerir uma faixa que nao existe.
function tile_simples(nome, campo, casas, un) {
    const v = alvo[campo];
    if (v === undefined) {
        return { nome: nome, texto: '--', un: '', pct: 0,
                 cor: COR.sem_dados, simb: '', rotulo: 'sem leitura' };
    }
    return { nome: nome, texto: v.toFixed(casas), un: un, pct: 0,
             cor: COR.sem_dados, simb: '', rotulo: '' };
}

const m3 = { payload: [
    tile('Temperatura',  'temperatura_c', 1, '°C'),
    tile('Vibracao RMS', 'vib_rms_g',     3, 'g'),
    tile('Corrente',     'corrente_a',    2, 'A'),
    tile_simples('Tensao',    'tensao_v', 1, 'V'),
    tile_simples('Barramento CC', 'dc_bus_v', 1, 'V'),
    tile_simples('Frequencia', 'frequencia_hz', 1, 'Hz')
], topic: alvo.chave };

// ---- Saida 4: os cards da visao geral --------------------------------
// Um card por ativo PRINCIPAL. As partes aparecem quando o card e aberto.
function m4_cards() {
    const cards = lista.filter(function (x) { return x.nivel === 0; })
    .map(function (a) {
        const e = (estados[a.chave] || {}).estado || 'sem_dados';
        const partes = lista.filter(function (x) {
            return x.nivel > 0 && x.chave.split('/')[0] === a.chave;
        }).length;

        function medida(nome, campo, casas, un) {
            const v = a[campo];
            const lim = LIM[campo];
            if (v === undefined) {
                return { nome: nome, texto: '--', un: '', pct: 0,
                         cor: COR.sem_dados, vazio: true };
            }
            if (v === null) {
                return { nome: nome, texto: 'FALHA', un: '', pct: 0,
                         cor: COR.atencao, vazio: true };
            }
            return { nome: nome, texto: v.toFixed(casas), un: un,
                     pct: Math.max(0, Math.min(100, (v / lim.critico) * 100)),
                     cor: COR[avaliar(v, lim)], vazio: false };
        }

        const partes_txt = partes ? (partes + (partes > 1 ? ' partes' : ' parte'))
                                  : 'equipamento unico';
        // Resume as partes no card: "Motor 1 · U1" ajuda a reconhecer o
        // equipamento sem precisar abrir.
        const nomes_partes = lista
            .filter(function (x) { return x.nivel > 0 && x.chave.split('/')[0] === a.chave; })
            .map(function (x) {
                // A tag do inversor entre parenteses: e rotulo do drive, nao
                // um nome de parte, entao nao pode competir com "Motor 1".
                return x.tag_inversor ? (x.rotulo + ' (' + x.tag_inversor + ')')
                                      : x.rotulo;
            });
        return {
            chave: a.chave,
            tag: a.rotulo,
            descricao: nomes_partes.join(' • '),
            cor: COR[e], simb: SIMB[e], rotulo: ROTULO[e],
            n_partes: partes_txt,
            marcha: (a.rodando === undefined) ? ''
                    : (a.rodando ? '▶ rodando' : '■ parado'),
            marcha_cls: a.rodando ? 'on' : 'off',
            visto: ha_quanto(a.visto_em),
            medidas: [ medida('Temp', 'temperatura_c', 1, '°C'),
                       medida('Vib',  'vib_rms_g',     3, 'g'),
                       medida('Corr', 'corrente_a',    2, 'A') ]
        };
    });
    return { payload: cards };
}

// ---- Saida 5: cabecalho da tela de detalhe ---------------------------
const e_alvo = (estados[alvo.chave] || {}).estado || 'sem_dados';

// Procedencia: de onde vem cada numero desta tela.
const fontes = [];
if (alvo.fonte_esp32) { fontes.push('sensor ' + alvo.fonte_esp32); }
if (alvo.tag_inversor) {
    fontes.push('inversor ' + alvo.tag_inversor +
                (alvo.fonte_inversor ? ' (' + alvo.fonte_inversor + ')' : ''));
} else if (alvo.fonte_inversor) {
    fontes.push('inversor ' + alvo.fonte_inversor);
}
const nome_exib = (alvo.nivel > 0)
    ? (alvo.chave.split('/')[0] + '  ›  ' + alvo.rotulo)
    : alvo.rotulo;

const marcha = marcha_txt(alvo);
const m5 = { payload:
    '<span style="font-size:20px;font-weight:600;color:#ffffff">' + nome_exib + '</span>' +
    '<span style="margin-left:12px;color:' + COR[e_alvo] + '">' +
    SIMB[e_alvo] + ' ' + ROTULO[e_alvo] + '</span>' +
    (marcha !== '--'
        ? '<span style="margin-left:12px;color:#c3c2b7">' + marcha + '</span>'
        : '') +
    (alvo.falha_codigo
        ? '<div style="font-size:13px;color:' + COR.critico + ';margin-top:3px">' +
          '■ F' + String(alvo.falha_codigo).padStart(3, '0') +
          (alvo.falha_texto ? ' — ' + alvo.falha_texto : '') + '</div>'
        : '') +
    (fontes.length
        ? '<div style="font-size:12px;color:#898781;margin-top:2px">' +
          fontes.join(' · ') + '</div>'
        : '') };

return [m1, m2, m3, m4_cards(), m5];
""")

# =====================================================================
#  Widgets
# =====================================================================
CARDS = r"""
<template>
    <div class="parede">
        <div v-if="!cards.length" class="vazio">
            Aguardando o primeiro ativo publicar...
        </div>
        <div v-for="c in cards" :key="c.chave" class="card"
             :style="{ borderLeftColor: c.cor }"
             role="button" tabindex="0"
             @click="abrir(c)" @keyup.enter="abrir(c)">

            <div class="topo">
                <div class="nome">
                    <div class="tag">{{ c.tag }}</div>
                    <div class="desc" v-if="c.descricao">{{ c.descricao }}</div>
                </div>
                <!-- simbolo + texto: a cor nunca carrega o estado sozinha -->
                <div class="chip" :style="{ color: c.cor, borderColor: c.cor }">
                    {{ c.simb }} {{ c.rotulo }}
                </div>
            </div>

            <div class="medidas">
                <div v-for="m in c.medidas" :key="m.nome" class="medida">
                    <div class="mrot">{{ m.nome }}</div>
                    <div class="mval" :class="{ vazio: m.vazio }">
                        {{ m.texto }}<span v-if="m.un" class="mun">{{ m.un }}</span>
                    </div>
                    <div class="trilho">
                        <div class="preenche"
                             :style="{ width: m.pct + '%', background: m.cor }"></div>
                    </div>
                </div>
            </div>

            <div class="rodape">
                <span>
                    {{ c.n_partes }}
                    <span v-if="c.marcha" class="marcha" :class="c.marcha_cls">
                        {{ c.marcha }}
                    </span>
                </span>
                <span>visto ha {{ c.visto }}</span>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    data () { return { cards: [] } },
    methods: {
        // Manda a chave para o fluxo, que guarda a selecao e navega.
        abrir (c) { this.send({ payload: c.chave }) }
    },
    watch: {
        msg: {
            immediate: true,
            handler (m) { if (m && Array.isArray(m.payload)) { this.cards = m.payload } }
        }
    }
}
</script>

<style scoped>
/* align-content/items em start: sem isso o grid estica os cards para
   preencher a altura do grupo, e cada card vira uma coluna vazia enorme. */
.parede { display: grid; gap: 12px; align-content: start; align-items: start;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
.vazio  { color: #898781; padding: 8px; }

.card {
    background: #1a1a19;
    border: 1px solid #383835;
    border-left: 4px solid #898781;   /* faixa de estado */
    border-radius: 4px;
    padding: 12px 14px;
    cursor: pointer;
    transition: box-shadow .15s ease, transform .15s ease;
}
.card:hover, .card:focus-visible {
    /* No escuro a sombra some; quem marca o hover e a borda clareando. */
    border-color: #5a5a55;
    background: #212120;
    transform: translateY(-1px);
    outline: none;
}

.topo { display: flex; justify-content: space-between; align-items: flex-start;
        gap: 8px; margin-bottom: 10px; }
.tag  { font-size: 16px; font-weight: 600; color: #ffffff; }
.desc { font-size: 12px; color: #c3c2b7; margin-top: 1px; }
.chip { font-size: 11px; white-space: nowrap; border: 1px solid;
        border-radius: 10px; padding: 1px 8px; }

.medidas { display: flex; gap: 10px; }
.medida  { flex: 1; min-width: 0; }
.mrot { font-size: 10px; color: #898781; text-transform: uppercase;
        letter-spacing: .3px; }
/* Figuras proporcionais: tabular deixa o numero solto nesse tamanho */
.mval { font-size: 20px; color: #ffffff; line-height: 1.2;
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.mval.vazio { font-size: 14px; color: #898781; }
.mun  { font-size: 11px; color: #c3c2b7; margin-left: 2px; }
.trilho   { height: 3px; background: #2c2c2a; border-radius: 2px; margin-top: 4px; }
.preenche { height: 100%; border-radius: 2px; transition: width .3s ease; }

.rodape { display: flex; justify-content: space-between; margin-top: 10px;
          font-size: 11px; color: #898781; }
/* Marcha e contexto, nao saude: fica discreta e nunca usa a cor de status,
   senao "rodando" leria como "OK" e "parado" como alarme. */
.marcha        { margin-left: 6px; }
.marcha.on     { color: #c3c2b7; }
.marcha.off    { color: #898781; }
</style>
"""

no(id="cards_ativos", type="ui-template", z="flow_monitor", group=G_CARDS,
   name="cards dos ativos", order=1, width="12", height="8",
   head="", format=CARDS, storeOutMessages=True, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=340, wires=[["abrir_ativo"]])

no(id="abrir_ativo", type="function", z="flow_monitor",
   name="abrir detalhe", outputs=1, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=840, y=340,
   wires=[["nav_detalhe"]],
   func=r"""
// Clique num card: guarda o ativo e pede a troca de tela. O nome tem de
// bater com o do no ui-page, senao o ui-control reclama que nao achou.
flow.set('ativo_sel', msg.payload);
return { payload: { page: 'Detalhe' } };
""")

no(id="nav_detalhe", type="ui-control", z="flow_monitor", ui=BASE,
   name="navegar", events="all", x=1020, y=340, wires=[[]])

no(id="btn_voltar", type="ui-button", z="flow_monitor", group=G_CAB,
   name="voltar", label="← Todos os ativos", order=1, width="3", height="1",
   tooltip="", color="", bgcolor="", className="", icon="",
   iconPosition="left", payload="", payloadType="str", topic="topic",
   topicType="msg", buttonColor="", textColor="", iconColor="",
   enableClick=True, enablePointerdown=False, pointerdownPayload="",
   pointerdownPayloadType="str", enablePointerup=False, pointerupPayload="",
   pointerupPayloadType="str", x=140, y=660, wires=[["voltar_visao"]])

no(id="voltar_visao", type="function", z="flow_monitor", name="voltar",
   outputs=1, timeout=0, noerr=0, initialize="", finalize="", libs=[],
   x=340, y=660, wires=[["nav_detalhe"]],
   func=r"""
return { payload: { page: 'Visao Geral' } };
""")

no(id="cab_detalhe", type="ui-text", z="flow_monitor", group=G_CAB,
   order=2, width="9", height="1", name="cabecalho do detalhe", label="",
   format="{{msg.payload}}", layout="row-left", style=False, font="",
   fontSize=16, color="#717171", wrapText=True, className="",
   x=640, y=460, wires=[])

no(id="tabela_ativos", type="ui-table", z="flow_monitor", group=G_PARTES,
   name="tabela de ativos", label="", order=1, width="0", height="0",
   maxrows=0, passthru=False, autocols=True, columns=[],
   # 'none' desliga o modo cartao: num painel a tabela e sempre tabela,
   # senao cada ativo virava um bloco empilhado de chave/valor.
   mobileBreakpoint="", mobileBreakpointType="none",
   showSearch=False, deselect=True,
   action="replace", selectionType="none", className="",
   x=620, y=340, wires=[[]])

no(id="txt_resumo", type="ui-text", z="flow_monitor", group=G_RESUMO,
   order=1, width="12", height="1", name="resumo", label="",
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
.tiles { display: flex; gap: 12px 10px; flex-wrap: wrap; }
.tile  { flex: 1 1 30%; min-width: 100px; }
.rot   { font-size: 12px; color: #c3c2b7; margin-bottom: 2px; }
/* Figuras proporcionais no numero grande: tabular deixa solto nesse tamanho */
.val   { font-size: 30px; line-height: 1.1; color: #ffffff;
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.val.vazio { color: #898781; font-size: 22px; }
.un    { font-size: 13px; color: #c3c2b7; margin-left: 4px; }
.trilho   { height: 4px; background: #2c2c2a; border-radius: 2px; margin: 6px 0 4px; }
.preenche { height: 100%; border-radius: 2px; transition: width .3s ease; }
.estado   { font-size: 12px; }
</style>
"""

no(id="stat_tiles", type="ui-template", z="flow_monitor", group=G_TILES,
   name="stat tiles do ativo", order=1, width="6", height="4",
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
       removeOlderPoints="", colors=SERIES, textColor=[TINTA_3],
       textColorDefault=False, gridColor=[LINHA], gridColorDefault=False,
       width=str(largura), height="6", className="", interpolation="linear",
       x=820, y=100, wires=[[]])


grafico("chart_temp", G_TEMP,  "Temperatura",  "°C", "", "")
grafico("chart_vib",  G_VIB,   "Vibracao RMS", "g",  "0", "")
grafico("chart_corr", G_CORR,  "Corrente",     "A",  "0", "", largura=12)

# =====================================================================
#  Comandos: escolher o ativo e mandar publicar
# =====================================================================
no(id="btn_publicar", type="ui-button", z="flow_monitor", group=G_CMD,
   name="publicar agora", label="Publicar agora", order=1, width="6",
   height="1", tooltip="Forca uma leitura imediata no ativo aberto",
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
// Manda para o ativo ABERTO na tela, em vez de um id fixo no codigo.
//
// A chave pode ser um device_id ("motor-01", descoberta automatica) ou uma
// TAG do cadastro ("U1", "U1/Motor principal"). O comando so faz sentido
// para um ESP32 de verdade, entao quem resolve isso e o registro publicado
// pelo renderizador.
const chave = flow.get('ativo_sel');
if (!chave) { node.warn('nenhum ativo aberto'); return null; }

const destinos = (flow.get('esp32_por_chave') || {})[chave] || [];
if (!destinos.length) {
    node.warn('ativo "' + chave + '" nao tem ESP32 conhecido para comandar');
    return null;
}

// Um ativo principal com varias partes dispara em todas elas. O array
// vem aninhado de proposito: assim as N mensagens saem PELA MESMA saida.
return [destinos.map(function (dev) {
    return { topic: 'monitoramento/' + dev + '/cmd',
             payload: JSON.stringify({ comando: 'publicar' }) };
})];
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
