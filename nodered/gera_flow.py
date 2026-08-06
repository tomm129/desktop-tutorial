#!/usr/bin/env python3
"""Gera o nodered/flows.json (Dashboard 2.0) do projeto de monitoramento.

Escrever 700 linhas de JSON na mao e um convite a erro; aqui o fluxo e
descrito em Python e serializado. Rode e depois importe o resultado.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from marca import LOGO_LOCKUP, LOGO_ICONE

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

# Status: paleta reservada, nunca usada para serie. Tons vibrantes mas
# controlados, com contraste > 3:1 sobre fundo escuro.
STATUS = {"good": "#22c55e", "warning": "#f59e0b", "critical": "#ef4444"}

# Superficies e tinta do tema escuro moderno.
FUNDO_PAGINA = "#0b0b0c"      # fundo geral quase preto
FUNDO_CARTAO = "#151518"      # superficie dos cards/grupos
FUNDO_ELEV   = "#1e1e22"      # hover/elevacao
TINTA_1 = "#f4f4f5"           # primaria (quase branco)
TINTA_2 = "#a1a1aa"           # secundaria
TINTA_3 = "#71717a"           # apagada (eixos, rotulos)
TINTA_4 = "#52525b"           # muito apagada
LINHA   = "#27272a"           # grade / divisoria
BORDA   = "#3f3f46"           # bordas sutis
SOMBRA  = "rgba(0,0,0,0.35)"  # sombras dos cards

BASE, TEMA = "ui_base", "ui_tema"

# Duas telas: a visao geral e uma parede de cards (um por ativo principal),
# e o clique num card abre o detalhe daquele ativo.
PAGINA, PAGINA_DET, PAGINA_CAD, PAGINA_ALARMES = "pg_visao", "pg_detalhe", "pg_cadastro", "pg_alarmes"
PAGINA_ATIVOS, PAGINA_TEND = "pg_ativos", "pg_tendencias"
PAGINA_IA, PAGINA_REL = "pg_ia", "pg_relatorios"

G_RESUMO, G_CARDS = "grp_resumo", "grp_cards"
G_LINHA = "grp_linha"
G_CAB, G_TILES, G_PARTES, G_CMD = "grp_cab", "grp_tiles", "grp_partes", "grp_cmd"
G_PLACA = "grp_placa"
G_TEMP, G_VIB, G_CORR = "grp_temp", "grp_vib", "grp_corr"
G_CAD = "grp_cadastro"
G_ALARMES_KPI, G_ALARMES_LISTA = "grp_alarmes_kpi", "grp_alarmes_lista"
G_ATIVOS_TAB = "grp_ativos_tab"
G_TEND_T, G_TEND_V, G_TEND_C = "grp_tend_t", "grp_tend_v", "grp_tend_c"
G_IA, G_REL = "grp_ia", "grp_rel"

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
   appIcon=LOGO_ICONE, includeClientData=True, acceptsClientConfig=[
       "ui-notification", "ui-control"],
   showPathInSidebar=False, headerContent="page", navigationStyle="default",
   titleBarStyle="default", showReconnectNotification=True,
   notificationDisplayTime="5", showDisconnectNotification=True,
   allowInstall=True)

no(id=TEMA, type="ui-theme", name="Industrial escuro",
   colors={"surface": FUNDO_CARTAO, "primary": SERIES[0],
           "bgPage": FUNDO_PAGINA, "groupBg": FUNDO_CARTAO,
           "groupOutline": BORDA},
   sizes={"density": "comfortable", "pagePadding": "16px", "groupGap": "16px",
          "groupBorderRadius": "10px", "widgetGap": "14px"})

BREAKPOINTS = [{"name": "Mobile", "px": "0", "cols": "4"},
               {"name": "Tablet", "px": "576", "cols": "8"},
               {"name": "Small Desktop", "px": "768", "cols": "10"},
               {"name": "Desktop", "px": "1024", "cols": "12"}]

no(id=PAGINA, type="ui-page", name="Visao Geral", ui=BASE, path="/visao",
   icon="view-dashboard", layout="grid", theme=TEMA, order=1, className="",
   visible=True, disabled=False, breakpoints=BREAKPOINTS)

no(id=PAGINA_DET, type="ui-page", name="Detalhe", ui=BASE, path="/detalhe",
   icon="magnify", layout="grid", theme=TEMA, order=99, className="",
   # Fora do menu de proposito: e uma tela de aprofundamento, alcancada
   # clicando num card. Um item de menu chamado "Detalhe" nao diz detalhe
   # DE QUE, e clicado sem contexto abriria um ativo arbitrario.
   visible=False, disabled=False, breakpoints=BREAKPOINTS)

no(id=PAGINA_ATIVOS, type="ui-page", name="Ativos", ui=BASE, path="/ativos",
   icon="factory", layout="grid", theme=TEMA, order=2, className="",
   visible=True, disabled=False, breakpoints=BREAKPOINTS)

no(id=PAGINA_TEND, type="ui-page", name="Tendencias", ui=BASE, path="/tendencias",
   icon="chart-line", layout="grid", theme=TEMA, order=3, className="",
   visible=True, disabled=False, breakpoints=BREAKPOINTS)

no(id=PAGINA_IA, type="ui-page", name="IA", ui=BASE, path="/ia",
   icon="robot-outline", layout="grid", theme=TEMA, order=4, className="",
   visible=True, disabled=False, breakpoints=BREAKPOINTS)

no(id=PAGINA_REL, type="ui-page", name="Relatorios", ui=BASE, path="/relatorios",
   icon="file-document-outline", layout="grid", theme=TEMA, order=6,
   className="", visible=True, disabled=False, breakpoints=BREAKPOINTS)

no(id=PAGINA_CAD, type="ui-page", name="Configuracao", ui=BASE, path="/cadastro",
   icon="cog-outline", layout="grid", theme=TEMA, order=7, className="",
   visible=True, disabled=False, breakpoints=BREAKPOINTS)

no(id=PAGINA_ALARMES, type="ui-page", name="Alarmes", ui=BASE, path="/alarmes",
   icon="bell-alert", layout="grid", theme=TEMA, order=5, className="",
   visible=True, disabled=False, breakpoints=BREAKPOINTS)


def grupo(gid, nome, largura, ordem, altura=1, pagina=PAGINA, titulo=True):
    no(id=gid, type="ui-group", name=nome, page=pagina, width=str(largura),
       height=str(altura), order=ordem, showTitle=titulo, className="",
       visible=True, disabled=False, groupType="default")


# --- Tela 1: visao geral (a parede de cards) --------------------------
grupo(G_RESUMO, "Resumo",  12, 1, altura=4, titulo=False)
grupo(G_LINHA,  "",        12, 2, altura=7, titulo=False)
grupo(G_CARDS,  "Ativos",  12, 3, altura=9, titulo=False)

# --- Tela 2: detalhe de um ativo --------------------------------------
# A altura dos grupos de grafico precisa caber o plot MAIS a faixa do eixo X;
# com altura 1 o grafico vira um risco e o eixo some.
grupo(G_CAB,    "",                       12, 1, altura=2, pagina=PAGINA_DET, titulo=False)
grupo(G_TILES,  "Leituras agora",          6, 2, altura=5, pagina=PAGINA_DET)
grupo(G_CMD,    "Comandos",                6, 3, altura=2, pagina=PAGINA_DET)
grupo(G_PARTES, "Partes deste ativo",     12, 4, altura=5, pagina=PAGINA_DET)
grupo(G_PLACA,  "Dados de placa e sobressalentes", 12, 5, altura=13,
      pagina=PAGINA_DET)
grupo(G_TEMP,   "Temperatura (°C)",        6, 6, altura=8, pagina=PAGINA_DET)
grupo(G_VIB,    "Vibracao RMS (g)",        6, 7, altura=8, pagina=PAGINA_DET)
grupo(G_CORR,   "Corrente (A)",           12, 8, altura=8, pagina=PAGINA_DET)

# --- Tela 3: cadastro de dispositivos ---------------------------------
grupo(G_CAD, "", 12, 1, altura=14, pagina=PAGINA_CAD, titulo=False)

# --- Tela: Ativos (tabela completa da planta) -------------------------
grupo(G_ATIVOS_TAB, "Todos os ativos e partes", 12, 1, altura=16,
      pagina=PAGINA_ATIVOS)

# --- Tela: Tendencias (as tres grandezas, planta inteira) -------------
grupo(G_TEND_T, "Temperatura (°C)",  12, 1, altura=8, pagina=PAGINA_TEND)
grupo(G_TEND_V, "Vibracao RMS (g)",  12, 2, altura=8, pagina=PAGINA_TEND)
grupo(G_TEND_C, "Corrente (A)",      12, 3, altura=8, pagina=PAGINA_TEND)

# --- Telas de roadmap -------------------------------------------------
grupo(G_IA,  "", 12, 1, altura=12, pagina=PAGINA_IA,  titulo=False)
grupo(G_REL, "", 12, 1, altura=12, pagina=PAGINA_REL, titulo=False)

# --- Tela 4: alarmes/historico ----------------------------------------
grupo(G_ALARMES_KPI,  "Resumo de alarmes", 12, 1, altura=2,
      pagina=PAGINA_ALARMES, titulo=False)
grupo(G_ALARMES_LISTA, "Historico",         12, 2, altura=14,
      pagina=PAGINA_ALARMES, titulo=False)

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
   wires=[["chart_temp", "tend_temp"], ["chart_vib", "tend_vib"]],
   func=r"""
// Guarda a ultima leitura de cada ativo num registro unico (flow context)
// e repassa os valores para os graficos. Tambem mantem um cache curto para
// tendencia/sparklines e descarta valores fisicamente impossiveis.
//
// msg.topic vira o device_id: e ele que separa as series no grafico, o que
// faz o dashboard funcionar com N ativos em vez de um so.
const p = msg.payload || {};
const id = p.device_id;
if (!id) { node.warn('telemetria sem device_id, descartada'); return null; }

const ativos = flow.get('ativos') || {};
const a = ativos[id] || { id: id };

// Quem publica telemetria e sensor de campo; quem publica no topico do
// inversor e drive. A tela de Cadastro usa isso para nao oferecer um
// inversor onde se espera um ESP32.
a.tipo = 'esp32';
a.visto_em = Date.now();

// Validacao simples: descarta valores absurdos que so podem ser ruido/erro.
function valida_temp(v) {
    if (v === undefined || v === null) { return null; }
    if (typeof v !== 'number' || !isFinite(v)) { return null; }
    if (v < -40 || v > 200) { node.warn('temperatura fora da faixa para ' + id + ': ' + v); return null; }
    return v;
}
function valida_vib(v) {
    if (v === undefined || v === null) { return null; }
    if (typeof v !== 'number' || !isFinite(v) || v < 0) { return null; }
    if (v > 50) { node.warn('vibracao fora da faixa para ' + id + ': ' + v); return null; }
    return v;
}

// null explicito quando o sensor falhou -- a UI mostra FALHA, e nao o
// ultimo valor bom congelado, que leria como "esta tudo bem".
a.temperatura_c = valida_temp(p.temperatura_c);

if (p.vibracao) {
    a.vib_rms_g  = valida_vib(p.vibracao.rms_g);
    a.vib_pico_g = valida_vib(p.vibracao.pico_g);
    a.fs_hz      = (typeof p.vibracao.fs_hz === 'number' && isFinite(p.vibracao.fs_hz))
                       ? p.vibracao.fs_hz : null;
} else {
    a.vib_rms_g = null;
}
if (p.rede) { a.rssi_dbm = p.rede.rssi_dbm ?? null; }

// Cache curto das ultimas leituras para tendencia e sparklines.
const MAX_HIST = 30;
if (!a.hist) { a.hist = { temp: [], vib: [] }; }
if (a.temperatura_c !== null) {
    a.hist.temp.push(a.temperatura_c);
    if (a.hist.temp.length > MAX_HIST) { a.hist.temp.shift(); }
}
if (a.vib_rms_g !== null) {
    a.hist.vib.push(a.vib_rms_g);
    if (a.hist.vib.length > MAX_HIST) { a.hist.vib.shift(); }
}

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
   wires=[["chart_corr", "tend_corr"]],
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
a.tipo = 'inversor';

function valida_corr(v) {
    if (typeof v !== 'number' || !isFinite(v) || v < 0) { return null; }
    if (v > 500) { node.warn('corrente fora da faixa para ' + id + ': ' + v); return null; }
    return v;
}
function valida_tensao(v) {
    if (typeof v !== 'number' || !isFinite(v) || v < 0) { return null; }
    if (v > 1000) { node.warn('tensao fora da faixa para ' + id + ': ' + v); return null; }
    return v;
}

if (typeof p.corrente_a === 'number') { a.corrente_a = valida_corr(p.corrente_a); }
if (typeof p.tensao_v === 'number')   { a.tensao_v   = valida_tensao(p.tensao_v); }
if (typeof p.dc_bus_v === 'number')   { a.dc_bus_v   = valida_tensao(p.dc_bus_v); }
if (typeof p.frequencia_hz === 'number' && isFinite(p.frequencia_hz) && p.frequencia_hz >= 0) {
    a.frequencia_hz = p.frequencia_hz;
}
if (typeof p.rodando === 'boolean') { a.rodando = p.rodando; }
if (p.falha) {
    a.falha_codigo = (typeof p.falha.codigo === 'number') ? p.falha.codigo : 0;
    a.falha_texto  = p.falha.texto || null;
}

// Cache curto para tendencia de corrente.
const MAX_HIST = 30;
if (!a.hist) { a.hist = { corr: [] }; }
if (typeof a.corrente_a === 'number') {
    a.hist.corr.push(a.corrente_a);
    if (a.hist.corr.length > MAX_HIST) { a.hist.corr.shift(); }
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
#  Cadastro em disco: dados de placa e sobressalentes
# =====================================================================
# Fica em arquivo, e nao dentro do fluxo, por tres motivos: e conteudo de
# engenharia (nao logica), muda por motivos diferentes do resto, e assim
# pode ser editado sem deploy -- e, mais adiante, migrado para a tabela
# "ativos" do banco (docs/visualizacao.md) sem mexer no painel.
no(id="tick_cadastro", type="inject", z="flow_monitor",
   name="reler cadastro (60s)", props=[{"p": "payload"}], repeat="60",
   crontab="", once=True, onceDelay="0.5", topic="", payload="",
   payloadType="date", x=140, y=720, wires=[["caminho_cadastro"]])

no(id="caminho_cadastro", type="function", z="flow_monitor",
   name="caminho do cadastro", outputs=1, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=350, y=720,
   wires=[["ler_cadastro"]],
   func=r"""
// Caminho ABSOLUTO, resolvido em tempo de execucao.
//
// O no "file in" resolve caminho relativo contra o diretorio do PROCESSO,
// nao o do Node-RED -- ou seja, dependeria de onde o servico foi iniciado,
// e quebraria calado (arquivo nao encontrado = sem dados de placa, sem
// nenhum sintoma obvio no painel).
//
// Define IOT_DADOS no ambiente para apontar outro lugar; o padrao segue o
// mesmo /opt/iot onde o sidecar do PowerFlex e instalado.
const base = env.get('IOT_DADOS') || '/opt/iot/dados';
msg.filename = base + '/ativos.json';
return msg;
""")

# Com filenameType="msg", o campo filename guarda o NOME da propriedade
# que carrega o caminho -- nao o caminho, e nunca vazio.
no(id="ler_cadastro", type="file in", z="flow_monitor", name="ativos.json",
   filename="filename", filenameType="msg", format="utf8",
   chunk=False, sendError=False, encoding="utf8", allProps=False,
   x=560, y=720, wires=[["guardar_cadastro"]])

no(id="guardar_cadastro", type="function", z="flow_monitor",
   name="guardar cadastro", outputs=0, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=760, y=720, wires=[],
   func=r"""
// Arquivo ausente ou ilegivel nao pode derrubar o painel: sem cadastro o
// sistema segue funcionando, so sem dados de placa. Por isso sendError
// esta desligado no no de leitura e o parse e protegido aqui.
if (!msg.payload) { return null; }
try {
    const cad = JSON.parse(msg.payload);
    delete cad._leiame;
    flow.set('cadastro', cad);
} catch (e) {
    node.warn('dados/ativos.json invalido, ignorado: ' + e.message);
}
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
   name="montar painel", outputs=10, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=350, y=380,
   wires=[["tabela_ativos"], ["txt_resumo"], ["stat_tiles"],
          ["cards_ativos"], ["cab_detalhe"], ["painel_placa"],
          ["alarmes_kpi"], ["alarmes_lista"], ["tabela_planta"], ["linha_tempo"]],
   func=r"""
// Unico ponto que decide estado, cor e texto -- se os limites mudarem,
// mudam aqui e valem para a tabela, os alarmes e os medidores.

// ---- Cadastro de ativos ----------------------------------------------
// Vem INTEIRO de dados/ativos.json -- mapeamento de hardware e dados de
// placa no mesmo lugar.
//
// Antes o mapeamento morava numa constante aqui e a placa no arquivo, com
// as chaves tendo de bater na mao. Alem de fragil, impedia a tela de
// Cadastro de existir: nenhuma tela edita constante de codigo.
//
// Formato:
//   'Nome do ativo': {
//       local: 'onde fica',
//       partes: {
//           'Motor 1': {
//               esp32: 'esp-a1b2c3',        // quem manda temp + vibracao
//               inversor: 'pf-01',          // quem manda corrente
//               tag_inversor: 'U11',        // como o drive e chamado no painel
//               placa: { ... }, sobressalentes: [ ... ]
//           }
//       }
//   }
//
// Vazio = descoberta automatica: todo device_id que publicar vira uma linha
// solta, e a tela de Cadastro serve para atribui-lo a um ativo.
const ATIVOS = flow.get('cadastro') || {};

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
const COR = { normal: '#22c55e', atencao: '#f59e0b', critico: '#ef4444',
              sem_dados: '#71717a' };
// A cor nunca carrega o significado sozinha: sempre vem com simbolo e texto.
const SIMB = { normal: '●', atencao: '▲', critico: '■', sem_dados: '○' };
const ROTULO = { normal: 'OK', atencao: 'ATENÇÃO', critico: 'CRÍTICO',
                 sem_dados: 'SEM DADOS' };

const PIOR = { sem_dados: 0, normal: 1, atencao: 2, critico: 3 };

// Fracao do limite usada como banda de histerese: o alarme dispara no
// limite, mas so limpa 5% abaixo dele.
//
// Sem isso, um valor pousado em cima do limite (60,0 °C num limite de 60)
// entra e sai de alarme a cada ciclo -- o histórico enche de ruido
// justamente do ativo que mais interessa, e quem opera aprende a ignorar.
const HISTERESE = 0.05;

// Guarda o nivel anterior de cada grandeza para saber se estamos subindo
// (aplica o limite cheio) ou descendo (aplica o limite reduzido).
const niveis_ant = flow.get('niveis_anteriores') || {};
const niveis_novos = {};

function avaliar(valor, lim, id_hist) {
    if (valor === null || valor === undefined) { return null; }

    const ant = id_hist ? niveis_ant[id_hist] : null;

    // Ja estava em atencao/critico? Entao so sai quando cair abaixo da
    // banda -- e nao no instante em que cruza o limite de volta.
    const lim_crit = (ant === 'critico')
        ? lim.critico * (1 - HISTERESE) : lim.critico;
    const lim_aten = (ant === 'critico' || ant === 'atencao')
        ? lim.atencao * (1 - HISTERESE) : lim.atencao;

    let n;
    if (valor >= lim_crit)      { n = 'critico'; }
    else if (valor >= lim_aten) { n = 'atencao'; }
    else                        { n = 'normal'; }

    if (id_hist) { niveis_novos[id_hist] = n; }
    return n;
}

// Limites do ativo: os de LIM valem para todos, MENOS a corrente quando a
// placa informa a corrente nominal (In).
//
// Corrente e a unica grandeza aqui cujo limite nao pode ser universal: 12 A
// e operacao normal num motor de 15 A e sobrecarga num de 10 A. Com a In da
// placa, 90%/110% dela viram os limites daquele ativo -- que e a regra que
// docs/arquitetura.md sempre recomendou e que ate agora estava chutada.
function limites_de(a) {
    const inom = (((a.placa || {}).corrente_nominal_a) || 0);
    if (!inom) { return LIM; }
    const l = Object.assign({}, LIM);
    l.corrente_a = { atencao: inom * 0.9, critico: inom * 1.1,
                     nome: 'Corrente', un: 'A', derivado: inom };
    return l;
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

// Tendencia a partir de um array de valores. Usa a media da primeira metade
// contra a media da segunda metade -- suaviza ruido e ainda reage em
// poucas leituras.
function tendencia(hist) {
    if (!hist || hist.length < 4) { return { simb: '—', pct: 0, cor: '#71717a' }; }
    const meio = Math.floor(hist.length / 2);
    const ant = hist.slice(0, meio).reduce((a, b) => a + b, 0) / meio;
    const rec = hist.slice(meio).reduce((a, b) => a + b, 0) / (hist.length - meio);
    if (ant === 0) { return { simb: '—', pct: 0, cor: '#71717a' }; }
    const varia = (rec - ant) / ant;
    if (Math.abs(varia) < 0.02) { return { simb: '—', pct: 0, cor: '#71717a' }; }
    return {
        simb: varia > 0 ? '▲' : '▼',
        pct: Math.min(100, Math.abs(varia) * 100),
        cor: varia > 0 ? '#ef4444' : '#22c55e'   // subindo -> quente, descendo -> frio
    };
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
const cadastro = ATIVOS;

function ficha(tag, nome_parte) {
    const at = cadastro[tag] || {};
    if (!nome_parte) { return at; }
    return ((at.partes || {})[nome_parte]) || {};
}

function juntar_parte(chave, rotulo, cfg, nivel, tag, nome_parte) {
    const esp = registro[cfg.esp32] || {};
    const inv = registro[cfg.inversor] || {};
    const f = ficha(tag, nome_parte);
    return {
        placa: f.placa,
        sobressalentes: f.sobressalentes,
        chave: chave,
        rotulo: rotulo,
        nivel: nivel,
        // Procedencia: de onde veio cada numero. E o que o eletricista
        // precisa para achar o drive no painel.
        hist: {
            temp: (esp.hist || {}).temp || [],
            vib:  (esp.hist || {}).vib  || [],
            corr: (inv.hist || {}).corr || []
        },
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
    // Guarda de qual parte veio cada maximo, para o sparkline do card do
    // pai mostrar a serie DAQUELA parte -- e nao uma media que nao existe
    // em lugar nenhum da planta.
    const dono = {};

    function pior(campo) {
        // undefined = nenhuma parte tem o sensor; null = alguma tem e falhou.
        let melhor;
        let houve_falha = false;
        for (const p of partes) {
            const v = p[campo];
            if (v === undefined) { continue; }
            if (v === null) { houve_falha = true; continue; }
            if (melhor === undefined || v > melhor) { melhor = v; dono[campo] = p; }
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

    // Com uma parte so, o ativo E o equipamento: mostra a placa dela em vez
    // de deixar a tela vazia e obrigar mais um clique.
    const unica = (partes.length === 1) ? partes[0] : {};

    // Nivel de cada grandeza avaliado com o limite DA PARTE que o produziu.
    // Sem isso o card do pai pinta a barra usando o limite generico, e um
    // ativo com partes saudaveis aparece vermelho -- foi o que aconteceu
    // com uma caldeira cuja bomba tem In de 21,5 A: 12 A e folgado para
    // ela, mas estourava o limite fixo de 11 A do codigo.
    const niveis = {};
    for (const campo of ['temperatura_c', 'vib_rms_g', 'corrente_a']) {
        let pior_n = null;
        for (const pt of partes) {
            const v = pt[campo];
            if (v === null || v === undefined) { continue; }
            const n = avaliar(v, limites_de(pt)[campo], pt.chave + '::' + campo);
            if (pior_n === null || PIOR[n] > PIOR[pior_n]) { pior_n = n; }
        }
        if (pior_n) { niveis[campo] = pior_n; }
    }

    return {
        chave: tag,
        rotulo: tag,
        nivel: 0,
        eh_pai: true,
        niveis: niveis,
        placa: (cadastro[tag] || {}).placa || unica.placa,
        sobressalentes: (cadastro[tag] || {}).sobressalentes || unica.sobressalentes,
        local: (cadastro[tag] || {}).local,
        temperatura_c: pior('temperatura_c'),
        vib_rms_g: pior('vib_rms_g'),
        corrente_a: pior('corrente_a'),
        tensao_v: pior('tensao_v'),
        dc_bus_v: pior('dc_bus_v'),
        frequencia_hz: pior('frequencia_hz'),
        rodando: sabe_rodando ? algum_rodando : undefined,
        hist: {
            temp: ((dono.temperatura_c || {}).hist || {}).temp || [],
            vib:  ((dono.vib_rms_g || {}).hist || {}).vib  || [],
            corr: ((dono.corrente_a || {}).hist || {}).corr || []
        },
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
            return Object.assign({ chave: id, rotulo: id, nivel: 0 },
                                registro[id], ficha(id, null));
        });
    }

    const saida = [];
    for (const tag of tags.sort()) {
        const cfg = ATIVOS[tag];

        // Ativo sem 'partes': trata como equipamento unico (um nivel so).
        if (!cfg.partes) {
            if (cfg.esp32) { esp32_por_chave[tag] = [cfg.esp32]; }
            saida.push(juntar_parte(tag, tag, cfg, 0, tag, null));
            continue;
        }

        const nomes = Object.keys(cfg.partes);
        const partes = nomes.map(function (nome) {
            const chave = tag + '/' + nome;
            if (cfg.partes[nome].esp32) {
                esp32_por_chave[chave] = [cfg.partes[nome].esp32];
            }
            return juntar_parte(chave, nome, cfg.partes[nome], 1, tag, nome);
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

// ---- Dispositivos ainda nao atribuidos a nenhum ativo ----------------
// E o que a tela de Cadastro mostra. Um dispositivo esta "atribuido"
// quando aparece como esp32 ou inversor de alguma parte.
const atribuidos = new Set();
for (const tag of Object.keys(ATIVOS)) {
    const cfg = ATIVOS[tag];
    const partes = cfg.partes || { '': cfg };
    for (const nome of Object.keys(partes)) {
        const pt = partes[nome] || {};
        if (pt.esp32) { atribuidos.add(pt.esp32); }
        if (pt.inversor) { atribuidos.add(pt.inversor); }
    }
}
flow.set('nao_atribuidos', Object.keys(registro)
    .filter(function (id) { return !atribuidos.has(id); })
    .map(function (id) {
        const r = registro[id];
        return {
            id: id,
            tipo: r.tipo || 'desconhecido',
            visto: ha_quanto(r.visto_em),
            mudo: (Date.now() - (r.visto_em || 0)) > SEM_DADOS_MS,
            resumo: (r.tipo === 'inversor')
                ? ((r.corrente_a !== undefined ? r.corrente_a.toFixed(2) + ' A' : '--') +
                   (r.frequencia_hz !== undefined ? '  ·  ' + r.frequencia_hz.toFixed(1) + ' Hz' : ''))
                : ((r.temperatura_c !== undefined && r.temperatura_c !== null
                        ? r.temperatura_c.toFixed(1) + ' °C' : '--') +
                   (r.vib_rms_g !== undefined && r.vib_rms_g !== null
                        ? '  ·  ' + r.vib_rms_g.toFixed(3) + ' g' : ''))
        };
    }));
flow.set('ativos_existentes', Object.keys(ATIVOS).sort());


// ---- Passo 1: apura o estado de CADA item ----------------------------
const estados = {};
for (const a of lista) {
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

        const lims = limites_de(a);
        for (const campo of Object.keys(lims)) {
            const lim = lims[campo];
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
            const nivel = avaliar(v, lim, a.chave + '::' + campo);
            if (PIOR[nivel] > PIOR[estado]) { estado = nivel; }
            if (nivel !== 'normal') {
                motivos.push(lim.nome + ' ' + ROTULO[nivel].toLowerCase() +
                             ': ' + v.toFixed(2) + lim.un);
            }
        }
    }

    estados[a.chave] = { estado: estado, motivos: motivos, item: a };
}

// ---- Passo 2: o ativo pai herda o PIOR estado das suas partes --------
//
// Nao basta recalcular o estado do pai a partir dos valores consolidados:
// cada parte pode ter limite proprio (a corrente nominal vem da placa
// DELA), entao o pai avaliado com o limite generico discordaria da parte
// avaliada com o limite calibrado -- o card ficaria verde com a parte em
// atencao. O pai reflete as partes; nao as reavalia.
for (const a of lista) {
    if (!a.eh_pai) { continue; }
    const filhos = lista.filter(function (x) {
        return x.nivel > 0 && x.chave.split('/')[0] === a.chave;
    });
    if (!filhos.length) { continue; }

    // SUBSTITUI, nao combina com o estado que o pai calculou sozinho.
    //
    // O pai foi avaliado com os limites genericos (a placa e das partes),
    // entao a avaliacao propria dele e sempre menos informada que a das
    // partes -- e pode acusar critico onde toda parte esta folgada. Uma
    // caldeira cuja bomba tem In de 21,5 A operando a 12 A e o caso: as
    // partes normais, o pai vermelho, e nenhum alarme explicando por que.
    let pior = 'normal';
    for (const f of filhos) {
        const e = estados[f.chave].estado;
        if (PIOR[e] > PIOR[pior]) { pior = e; }
    }
    // Exceto quando o proprio ativo esta mudo: isso e dele, nao das partes.
    if (estados[a.chave].estado === 'sem_dados') {
        pior = 'sem_dados';
    } else {
        // Os MOTIVOS tambem sao das partes, nao da autoavaliacao do pai.
        //
        // Trocar so o estado deixava o texto contradizendo a cor: o pai e
        // avaliado com os limites genericos (a placa e das partes), entao
        // acusava "Corrente critico: 11.72A" num ativo cujas partes tem In
        // de 21,5 A e estao folgadas. O estado ficava certo e o motivo
        // errado -- pior que os dois errados, porque parece confiavel.
        const motivos_filhos = [];
        for (const f of filhos) {
            const ef = estados[f.chave];
            if (ef.estado === 'normal' || !ef.motivos.length) { continue; }
            for (const m of ef.motivos) {
                motivos_filhos.push(f.rotulo + ': ' + m);
            }
        }
        estados[a.chave].motivos = motivos_filhos;
    }
    estados[a.chave].estado = pior;
}

// Guarda os niveis deste ciclo: e a memoria de que a histerese depende.
flow.set('niveis_anteriores', niveis_novos);

// ---- Historico de alarmes --------------------------------------------
// Mantem os ultimos eventos em memoria de fluxo. Um evento e identificado
// por ativo + estado, entao o mesmo problema nao gera duplicatas a cada 2s.
// Quando o estado volta a normal, marcamos o fim do evento para saber a
// duracao.
const MAX_HIST_ALARMES = 100;
let hist = flow.get('historico_alarmes') || [];
const chaves_ativas = new Set();
for (const a of lista) {
    const e = estados[a.chave];
    if (!e || e.estado === 'normal') { continue; }

    // Uma ocorrencia, um registro. Quem entra no historico depende de onde
    // esta o problema:
    //
    //   limite/falha numa parte  -> registra a PARTE (o pai so herdou)
    //   ativo inteiro mudo       -> registra o ATIVO (as partes mudas sao
    //                               consequencia, nao N ocorrencias)
    //
    // Sem a segunda regra, uma queda de rede gera 1 + N linhas por ativo:
    // o pai e cada parte, todos dizendo "sem telemetria" no mesmo segundo.
    const tem_partes = lista.some(function (x) {
        return x.nivel > 0 && x.chave.split('/')[0] === a.chave;
    });
    if (a.eh_pai && tem_partes && e.estado !== 'sem_dados') { continue; }
    if (a.nivel > 0 && e.estado === 'sem_dados') {
        const pai = estados[a.chave.split('/')[0]];
        if (pai && pai.estado === 'sem_dados') { continue; }
    }

    const chave_evt = a.chave + '::' + e.estado;
    chaves_ativas.add(chave_evt);
    const ja = hist.find(function (h) { return h.chave === chave_evt && !h.fim_ms; });
    if (!ja) {
        hist.unshift({
            chave: chave_evt,
            ativo: a.eh_pai ? a.rotulo : (a.chave.split('/')[0] || a.rotulo),
            parte: a.eh_pai ? '' : a.rotulo,
            estado: e.estado,
            motivos: e.motivos.slice(),
            inicio_ms: agora,
            fim_ms: null
        });
    }
}
// Fecha eventos que ja normalizaram.
for (const h of hist) {
    if (!h.fim_ms && !chaves_ativas.has(h.chave)) {
        h.fim_ms = agora;
    }
}
if (hist.length > MAX_HIST_ALARMES) { hist = hist.slice(0, MAX_HIST_ALARMES); }
flow.set('historico_alarmes', hist);

// ---- Passo 3: monta as linhas e a lista de alarmes -------------------
const linhas = [];
const alarmes = [];
let pai_atual = '';
let pai_chave = '';

for (const a of lista) {
    const id = a.rotulo;
    const estado = estados[a.chave].estado;
    const motivos = estados[a.chave].motivos;

    // Sub-ativo entra recuado, para a hierarquia se ler de relance.
    const nome = (a.nivel > 0) ? ('\u00a0\u00a0\u00a0\u00a0\u2514 ' + id) : id;

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

    // O ativo principal so vira alarme proprio quando ele mesmo esta mudo.
    // Se o problema esta numa parte, quem alarma e a parte -- senao a mesma
    // ocorrencia apareceria duas vezes, com o pai repetindo o pior filho.
    const so_consolidado = a.eh_pai && estado !== 'sem_dados';
    if (estado !== 'normal' && !so_consolidado && motivos.length) {
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

// ---- Saude dos elos ---------------------------------------------------
//
// "Gateway online" mostrado PELO gateway e tautologia: se o Orange Pi
// cair, esta pagina nem carrega -- o navegador da erro de conexao, nao um
// ponto vermelho. Um indicador que so sabe dizer "sim" nao informa nada.
//
// O que vale mostrar sao os elos que quebram COM a pagina ainda de pe:
//
//   broker    Mosquitto pode morrer com o Node-RED vivo. A tela continua
//             abrindo, os dados congelam. E o modo de falha silencioso.
//   sidecar   o servico do PowerFlex pode cair sozinho (LWT avisa).
//   ciclo     prova que o renderizador esta girando, e nao travado numa
//             excecao -- valores "de agora" que na verdade sao de ontem.
const ciclo_ant = flow.get('ultimo_ciclo') || 0;
flow.set('ultimo_ciclo', agora);

// O sidecar publica online/offline retido no proprio topico de status.
const sidecars = Object.keys(registro).filter(function (id) {
    return registro[id].tipo === 'inversor';
});
const sidecars_ok = sidecars.filter(function (id) {
    return registro[id].conexao !== 'offline' &&
           (agora - (registro[id].visto_em || 0)) <= SEM_DADOS_MS;
}).length;

// Sem dispositivo nenhum publicando ha mais de SEM_DADOS_MS, o suspeito
// nao e cada dispositivo: e o barramento.
const visto_algum = Math.max.apply(null,
    [0].concat(Object.keys(registro).map(function (id) {
        return registro[id].visto_em || 0;
    })));
const barramento_mudo = Object.keys(registro).length > 0 &&
                        (agora - visto_algum) > SEM_DADOS_MS;

const elos = [
    { nome: 'Broker MQTT',
      ok: !barramento_mudo,
      det: barramento_mudo
            ? 'nenhuma mensagem ha ' + ha_quanto(visto_algum)
            : 'ultima mensagem ' + (visto_algum ? ha_quanto(visto_algum) : '--') + ' atras' },
    { nome: 'Inversores',
      ok: sidecars.length > 0 && sidecars_ok === sidecars.length,
      det: sidecars.length
            ? sidecars_ok + ' de ' + sidecars.length + ' respondendo'
            : 'nenhum cadastrado' },
    { nome: 'Painel',
      ok: true,
      det: 'ciclo a cada ' + (ciclo_ant ? Math.round((agora - ciclo_ant) / 1000) + 's' : '2s') }
];

// ---- Saida 2: faixa de resumo da visao geral -------------------------
// A logo vem embutida como data URI (ver nodered/marca.py): assim a marca
// acompanha o flows.json, sem depender de httpStatic no destino.
const LOGO = '__LOGO_LOCKUP__';
const n_pai = lista.filter(function (x) { return x.nivel === 0; }).length;
const cnt = { normal: 0, atencao: 0, critico: 0, sem_dados: 0 };
for (const a of lista) {
    if (a.nivel === 0) { cnt[estados[a.chave].estado] = (cnt[estados[a.chave].estado] || 0) + 1; }
}

function kpi(cor, simb, rot, val, sub) {
    return '<div style="display:inline-block;min-width:130px;margin:6px 10px 6px 0;' +
           'background:#151518;border:1px solid #3f3f46;border-radius:10px;padding:10px 14px;' +
           'box-shadow:0 2px 6px rgba(0,0,0,0.2)">' +
           '<div style="font-size:11px;color:#71717a;text-transform:uppercase;letter-spacing:.4px">' + rot + '</div>' +
           '<div style="font-size:24px;font-weight:600;color:' + cor + ';line-height:1.2">' + simb + ' ' + val + '</div>' +
           (sub ? '<div style="font-size:11px;color:#52525b;margin-top:2px">' + sub + '</div>' : '') +
           '</div>';
}

let html;
if (!lista.length) {
    html = '<span style="color:#71717a;font-size:14px">Aguardando o primeiro ativo publicar...</span>';
} else {
    html = '<img src="' + LOGO + '" alt="insightX" ' +
           // vertical-align:top + a MESMA margem superior dos cards (6px):
           // com 'middle' a logo era centrada na linha e, sendo mais baixa
           // que os cards, descia uns 16px em relacao ao topo deles.
           'style="height:44px;vertical-align:top;margin:6px 20px 6px 0;' +
           'padding-right:20px;border-right:1px solid #3f3f46">' +
           kpi(COR.normal, SIMB.normal, 'Normais', cnt.normal, 'ativos OK') +
           kpi(COR.atencao, SIMB.atencao, 'Atenção', cnt.atencao, 'revisar') +
           kpi(COR.critico, SIMB.critico, 'Críticos', cnt.critico, 'ação urgente') +
           elos.map(function (e) {
               return '<div style="display:inline-block;margin:6px 10px 6px 0;' +
                      'background:#151518;border:1px solid #3f3f46;border-radius:10px;' +
                      'padding:10px 14px;min-width:150px">' +
                      '<div style="font-size:11px;color:#71717a;text-transform:uppercase;' +
                      'letter-spacing:.4px">' + e.nome + '</div>' +
                      '<div style="font-size:14px;color:' +
                      (e.ok ? COR.normal : COR.critico) + ';margin-top:2px">' +
                      (e.ok ? '● conectado' : '■ sem resposta') + '</div>' +
                      '<div style="font-size:11px;color:#52525b;margin-top:2px">' +
                      e.det + '</div></div>';
           }).join('') +
           kpi(COR.sem_dados, SIMB.sem_dados, 'Sem dados', cnt.sem_dados, 'offline/mudo');
}
const m2 = { payload: html };

// ---- Saidas 3..5: a tela de detalhe ----------------------------------
const alvo = lista.find(function (x) { return x.chave === sel; }) || lista[0];
if (!alvo) { return [m1, m2, null, m4_cards(), null]; }

const lims_alvo = limites_de(alvo);

function tile(nome, campo, casas, un, hist) {
    const v = alvo[campo];
    const lim = lims_alvo[campo];
    if (v === undefined) {
        return { nome: nome, texto: '--', un: '', pct: 0,
                 cor: COR.sem_dados, simb: SIMB.sem_dados, rotulo: 'sem sensor',
                 tend: { simb: '—', pct: 0, cor: '#71717a' }, spark: [] };
    }
    if (v === null) {
        return { nome: nome, texto: 'FALHA', un: '', pct: 0,
                 cor: COR.atencao, simb: SIMB.atencao, rotulo: 'sem leitura',
                 tend: { simb: '—', pct: 0, cor: '#71717a' }, spark: [] };
    }
    const nivel = (alvo.niveis && alvo.niveis[campo])
                || avaliar(v, lim, alvo.chave + '::' + campo);
    // A barra e um medidor contra o limite critico: cheia = no limite.
    const pct = Math.max(0, Math.min(100, (v / lim.critico) * 100));
    const t = tendencia(hist);
    return { nome: nome, texto: v.toFixed(casas), un: un, pct: pct,
             cor: COR[nivel], simb: SIMB[nivel], rotulo: ROTULO[nivel],
             tend: t, spark: hist || [] };
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
    tile('Temperatura',  'temperatura_c', 1, '°C',
         ((registro[alvo.fonte_esp32] || {}).hist || {}).temp || []),
    tile('Vibracao RMS', 'vib_rms_g',     3, 'g',
         ((registro[alvo.fonte_esp32] || {}).hist || {}).vib || []),
    tile('Corrente',     'corrente_a',    2, 'A',
         ((registro[alvo.fonte_inversor] || {}).hist || {}).corr || []),
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

        const lims_card = limites_de(a);
        const series = { temperatura_c: 'temp', vib_rms_g: 'vib', corrente_a: 'corr' };

        function medida(nome, campo, casas, un) {
            const serie = ((a.hist || {})[series[campo]]) || [];
            const v = a[campo];
            const lim = lims_card[campo];
            if (v === undefined) {
                return { nome: nome, texto: '--', un: '', pct: 0,
                         cor: COR.sem_dados, vazio: true, spark: [] };
            }
            if (v === null) {
                return { nome: nome, texto: 'FALHA', un: '', pct: 0,
                         cor: COR.atencao, vazio: true, spark: [] };
            }
            // No ativo pai, o nivel ja veio consolidado das partes (cada
            // uma com o limite da SUA placa); so no equipamento folha e
            // que avaliamos aqui.
            const n = (a.niveis && a.niveis[campo])
                    || avaliar(v, lim, a.chave + '::' + campo);
            return { nome: nome, texto: v.toFixed(casas), un: un,
                     pct: Math.max(0, Math.min(100, (v / lim.critico) * 100)),
                     cor: COR[n], vazio: false, spark: serie };
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
    '<span style="font-size:22px;font-weight:600;color:#f4f4f5;letter-spacing:-0.2px">' + nome_exib + '</span>' +
    '<span style="margin-left:14px;padding:2px 10px;border-radius:12px;border:1px solid ' + COR[e_alvo] + ';color:' + COR[e_alvo] + ';font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.4px">' +
    SIMB[e_alvo] + ' ' + ROTULO[e_alvo] + '</span>' +
    (marcha !== '--'
        ? '<span style="margin-left:14px;color:#a1a1aa;font-size:14px">' + marcha + '</span>'
        : '') +
    (alvo.falha_codigo
        ? '<div style="font-size:13px;color:' + COR.critico + ';margin-top:6px;font-weight:500">' +
          '■ F' + String(alvo.falha_codigo).padStart(3, '0') +
          (alvo.falha_texto ? ' — ' + alvo.falha_texto : '') + '</div>'
        : '') +
    (fontes.length
        ? '<div style="font-size:12px;color:#71717a;margin-top:4px">' +
          fontes.join(' · ') + '</div>'
        : '') };

// ---- Saida 6: dados de placa e sobressalentes ------------------------
//
// Um ativo com varias partes nao tem plaqueta propria -- quem tem sao os
// motores dentro dele. Abrir a linha e ver "sem dados de placa" seria
// tecnicamente correto e praticamente inutil, entao o pai mostra as fichas
// das PARTES, uma secao por motor.
function ficha_de(a, titulo) {
    const pl = a.placa;
    const sob = a.sobressalentes || [];
    if (!pl && !sob.length) { return null; }

    const p = pl || {};
    const defs = [
        ['Fabricante',        p.fabricante],
        ['Modelo',            p.modelo],
        ['Numero de serie',   p.numero_serie],
        ['Ano',               p.ano],
        ['Potencia',          p.potencia_cv, ' cv'],
        ['',                  p.potencia_kw, ' kW'],
        ['Tensao',            p.tensao_v, ' V'],
        ['Corrente nominal',  p.corrente_nominal_a, ' A'],
        ['Rotacao',           p.rpm, ' rpm'],
        ['Frequencia',        p.frequencia_hz, ' Hz'],
        ['Polos',             p.polos],
        ['Fator de servico',  p.fator_servico],
        ['Rendimento',        p.rendimento_pct, ' %'],
        ['Fator de potencia', p.fator_potencia],
        ['Carcaca',           p.carcaca],
        ['Grau de protecao',  p.grau_protecao],
        ['Isolamento',        p.classe_isolamento],
        ['Peso',              p.peso_kg, ' kg']
    ];

    // So entram os campos preenchidos: linha com "--" nao informa nada e
    // ainda empurra para baixo o que interessa.
    const campos = [];
    for (const d of defs) {
        const val = d[1];
        if (val === undefined || val === null || val === '') { continue; }
        campos.push({ rot: d[0] || '', val: String(val) + (d[2] || '') });
    }

    // Deixa explicito quando o limite de corrente veio da placa: quem olha
    // precisa saber se o alarme e calibrado ou generico.
    if (p.corrente_nominal_a) {
        campos.push({ rot: 'Limite de alarme',
                      val: (p.corrente_nominal_a * 0.9).toFixed(1) + ' / ' +
                           (p.corrente_nominal_a * 1.1).toFixed(1) +
                           ' A  (90% / 110% da In)' });
    }

    return {
        titulo: titulo,
        // Servido estaticamente pelo Node-RED; ver httpStatic no settings.js.
        foto: p.foto ? ('/fotos/' + p.foto) : '',
        campos: campos,
        sobras: sob
    };
}

function montar_placa() {
    const fichas = [];

    const propria = ficha_de(alvo, '');
    if (propria) { fichas.push(propria); }

    // Sem ficha propria, desce para as partes.
    if (!propria && alvo.eh_pai) {
        const filhos = lista.filter(function (x) {
            return x.nivel > 0 && x.chave.split('/')[0] === alvo.chave;
        });
        for (const f of filhos) {
            const fi = ficha_de(f, f.rotulo);
            if (fi) { fichas.push(fi); }
        }
    }

    if (alvo.local) {
        // O local pertence ao ativo, nao a parte: entra uma vez so.
        if (fichas.length) { fichas[0].local = alvo.local; }
    }

    return { payload: { fichas: fichas } };
}

// ---- Saida 7: KPIs da tela de alarmes --------------------------------
// O widget le msg.payload; sem essa chave ele recebe undefined e fica nos
// zeros iniciais -- que era o motivo de os contadores nunca saírem de 0.
const m7 = { payload: {
    total: hist.length,
    ativos: n_pai,
    abertos: hist.filter(function (h) { return !h.fim_ms; }).length,
    critico: hist.filter(function (h) { return h.estado === 'critico'; }).length,
    atencao: hist.filter(function (h) { return h.estado === 'atencao'; }).length,
    sem_dados: hist.filter(function (h) { return h.estado === 'sem_dados'; }).length
} };

// ---- Saida 8: historico de alarmes ----------------------------------
const m8 = { payload: hist.map(function (h) {
    const duracao = h.fim_ms
        ? Math.round((h.fim_ms - h.inicio_ms) / 1000) + 's'
        : Math.round((agora - h.inicio_ms) / 1000) + 's (aberto)';
    return {
        ativo: h.ativo,
        parte: h.parte,
        estado: SIMB[h.estado] + ' ' + ROTULO[h.estado],
        cor: COR[h.estado],
        motivos: h.motivos.join(' | '),
        inicio: new Date(h.inicio_ms).toLocaleTimeString(),
        duracao: duracao
    };
}) };

// ---- Saida 9: tabela da PLANTA INTEIRA (pagina Ativos) --------------
// Nao pode compartilhar a saida 1: aquela e filtrada no ativo aberto na
// tela de Detalhe. Aqui o recorte e a planta toda, independente do que
// esteja selecionado noutra tela.
const m9 = { payload: linhas.map(limpar) };

// ---- Saida 10: linha do tempo de eventos ---------------------------
// Substitui a lista de alarmes em texto. A lista dizia O QUE esta errado
// -- informacao que os cards ja dao, com mais contexto. A linha do tempo
// acrescenta QUANDO e POR QUANTO TEMPO, que era a dimensao que faltava
// nesta tela.
// Janela ADAPTATIVA. Fixar 24h deixa a faixa vazia numa instalacao nova
// e amontoa tudo na ponta direita -- que e exatamente o estado em que o
// sistema passa os primeiros dias. A janela cobre desde o evento mais
// antigo, com 10% de folga, entre 15 minutos e 24 horas.
const MIN_JANELA = 15 * 60 * 1000;
const MAX_JANELA = 24 * 3600 * 1000;
const mais_antigo = hist.length
    ? Math.min.apply(null, hist.map(function (h) { return h.inicio_ms; }))
    : agora;
const JANELA_MS = Math.max(MIN_JANELA,
                  Math.min(MAX_JANELA, (agora - mais_antigo) * 1.1));
const t0 = agora - JANELA_MS;

function rotulo_janela(ms) {
    const h = ms / 3600000;
    if (h >= 1.5) { return 'ultimas ' + Math.round(h) + ' horas'; }
    return 'ultimos ' + Math.round(ms / 60000) + ' minutos';
}

function pos(ms) { return Math.max(0, Math.min(100, ((ms - t0) / JANELA_MS) * 100)); }

// Distribui em FAIXAS: eventos que se sobrepoem no tempo vao para linhas
// diferentes. Numa linha so, varios ativos em alarme ao mesmo tempo -- que
// e o caso normal quando algo serio acontece -- se cobrem, e a tela mostra
// menos justamente quando ha mais o que ver.
const fim_faixa = [];          // instante em que cada faixa ficou livre

const eventos = hist
    .filter(function (h) { return (h.fim_ms || agora) >= t0; })
    .slice()
    .sort(function (a, b) { return a.inicio_ms - b.inicio_ms; })
    .map(function (h) {
        const ini = Math.max(h.inicio_ms, t0);
        const fim = h.fim_ms || agora;
        const dur_s = Math.round((fim - h.inicio_ms) / 1000);
        const d = new Date(h.inicio_ms);
        // Primeira faixa livre; com folga de 2% da janela para dois
        // eventos quase encostados nao parecerem um so.
        const folga = JANELA_MS * 0.02;
        let faixa = fim_faixa.findIndex(function (f) { return f + folga <= h.inicio_ms; });
        if (faixa < 0) { faixa = fim_faixa.length; }
        fim_faixa[faixa] = fim;

        return {
            faixa: faixa,
            ini: pos(ini),
            // Largura minima de 0,35% para um evento de segundos ainda ser
            // clicavel -- senao vira uma linha de 1px impossivel de acertar.
            larg: Math.max(0.35, pos(fim) - pos(ini)),
            cor: COR[h.estado],
            simb: SIMB[h.estado],
            estado: ROTULO[h.estado],
            aberto: !h.fim_ms,
            ativo: h.ativo,
            parte: h.parte,
            motivos: h.motivos.join(' | '),
            quando: d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            duracao: dur_s < 60 ? (dur_s + 's')
                   : dur_s < 3600 ? (Math.round(dur_s / 60) + 'min')
                   : (Math.round(dur_s / 360) / 10 + 'h')
        };
    });

// Marca de 4 em 4 horas: seis rotulos cabem sem se atropelar.
const marcas = [];
for (let k = 0; k <= 6; k++) {
    const t = t0 + (JANELA_MS * k / 6);
    marcas.push({ pct: (k / 6) * 100,
                  rot: new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
}

const m10 = { payload: { eventos: eventos, marcas: marcas,
                         faixas: Math.max(1, fim_faixa.length),
                         janela: rotulo_janela(JANELA_MS) } };

return [m1, m2, m3, m4_cards(), m5, montar_placa(), m7, m8, m9, m10];
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
                    <!-- Sparkline: mesma altura que a barra ocupava, mas
                         mostrando PARA ONDE o valor vai, nao so onde esta.
                         A barra logo abaixo continua dando o nivel. -->
                    <svg v-if="m.spark && m.spark.length > 2" class="mini"
                         viewBox="0 0 100 22" preserveAspectRatio="none">
                        <polyline :points="pontos(m.spark)" fill="none"
                                  :stroke="m.cor" stroke-width="1.6"
                                  vector-effect="non-scaling-stroke"
                                  stroke-linejoin="round" stroke-linecap="round" />
                    </svg>
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
        abrir (c) { this.send({ payload: c.chave }) },

        // Projeta a serie no viewBox 100x22 usando a escala da PROPRIA
        // serie (min..max), nao a do limite: numa faixa estreita o
        // sparkline continua legivel -- o papel dele e mostrar forma.
        // Quem mostra nivel e a barra logo abaixo.
        pontos (arr) {
            if (!arr || arr.length < 2) { return ''; }
            const min = Math.min(...arr), max = Math.max(...arr);
            const amp = (max - min) || 1;
            const n = arr.length - 1;
            return arr.map(function (v, i) {
                const x = (i / n) * 100;
                const y = 20 - ((v - min) / amp) * 18;
                return x.toFixed(1) + ',' + y.toFixed(1);
            }).join(' ');
        }
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
.parede { display: grid; gap: 16px; align-content: start; align-items: start;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
.vazio  { color: #71717a; padding: 12px; font-size: 14px; }

.card {
    background: #151518;
    border: 1px solid #3f3f46;
    border-left: 5px solid #71717a;   /* faixa de estado */
    border-radius: 12px;
    padding: 16px 18px;
    cursor: pointer;
    transition: border-color .2s ease, background .2s ease, transform .2s ease, box-shadow .2s ease;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}
.card:hover, .card:focus-visible {
    border-color: #52525b;
    background: #1e1e22;
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(0,0,0,0.35);
    outline: none;
}

.topo { display: flex; justify-content: space-between; align-items: flex-start;
        gap: 10px; margin-bottom: 14px; }
.tag  { font-size: 17px; font-weight: 600; color: #f4f4f5; letter-spacing: -0.2px; }
.desc { font-size: 12px; color: #a1a1aa; margin-top: 2px; line-height: 1.3; }
.chip { font-size: 11px; font-weight: 600; white-space: nowrap; border: 1px solid;
        border-radius: 12px; padding: 2px 10px; text-transform: uppercase;
        letter-spacing: .4px; }

.medidas { display: flex; gap: 14px; }
.medida  { flex: 1; min-width: 0; }
.mrot { font-size: 10px; color: #71717a; text-transform: uppercase;
        letter-spacing: .5px; margin-bottom: 3px; }
/* Figuras proporcionais: tabular deixa o numero solto nesse tamanho */
.mval { font-size: 22px; color: #f4f4f5; line-height: 1.2;
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.mval.vazio { font-size: 15px; color: #71717a; }
.mun  { font-size: 12px; color: #a1a1aa; margin-left: 3px; }
.mini     { width: 100%; height: 22px; display: block; margin-top: 3px; opacity: .85; }
.trilho   { height: 4px; background: #27272a; border-radius: 2px; margin-top: 3px; overflow: hidden; }
.preenche { height: 100%; border-radius: 2px; transition: width .4s ease, background .3s ease; }

.rodape { display: flex; justify-content: space-between; margin-top: 14px;
          font-size: 11px; color: #71717a; }
/* Marcha e contexto, nao saude: fica discreta e nunca usa a cor de status,
   senao "rodando" leria como "OK" e "parado" como alarme. */
.marcha        { margin-left: 6px; font-weight: 500; }
.marcha.on     { color: #a1a1aa; }
.marcha.off    { color: #52525b; }
</style>
"""

no(id="cards_ativos", type="ui-template", z="flow_monitor", group=G_CARDS,
   name="cards dos ativos", order=1, width="12", height="9",
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


PLACA = r"""
<template>
    <div v-if="!fichas.length" class="nada">
        Sem dados de placa para este ativo.
        <span class="dica">Cadastre em <code>dados/ativos.json</code>.</span>
    </div>

    <div v-else>
        <div v-for="(f, i) in fichas" :key="i" class="bloco"
             :class="{ primeiro: i === 0 }">
            <div v-if="f.titulo" class="parte">{{ f.titulo }}</div>
            <div v-if="f.local" class="local">{{ f.local }}</div>

            <div class="painel">
                <div class="col foto-col">
                    <div class="titulo">Plaqueta</div>
                    <a v-if="f.foto" :href="f.foto" target="_blank" rel="noopener">
                        <img :src="f.foto" class="foto"
                             :alt="'Plaqueta de ' + (f.titulo || 'motor')">
                    </a>
                    <div v-else class="semfoto">
                        sem foto
                        <span class="dica">coloque em dados/fotos/ e cite no cadastro</span>
                    </div>
                </div>

                <div class="col">
                    <div class="titulo">Dados de placa</div>
                    <table class="ficha">
                        <tr v-for="(c, j) in f.campos" :key="j">
                            <th>{{ c.rot }}</th>
                            <td>{{ c.val }}</td>
                        </tr>
                    </table>
                </div>

                <div class="col">
                    <div class="titulo">
                        Sobressalentes
                        <span v-if="f.sobras.length" class="conta">{{ f.sobras.length }}</span>
                    </div>
                    <table v-if="f.sobras.length" class="sobras">
                        <tr v-for="(x, j) in f.sobras" :key="j">
                            <td class="it">
                                {{ x.item }}
                                <div v-if="x.obs" class="obs">{{ x.obs }}</div>
                            </td>
                            <td class="cod">{{ x.codigo }}</td>
                            <td class="qt">{{ x.qtd }}x</td>
                        </tr>
                    </table>
                    <div v-else class="semfoto">nenhum item cadastrado</div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
export default {
    data () { return { fichas: [] } },
    watch: {
        msg: {
            immediate: true,
            handler (m) {
                this.fichas = ((m && m.payload) || {}).fichas || [];
            }
        }
    }
}
</script>

<style scoped>
.bloco  { border-top: 1px solid #27272a; padding-top: 16px; margin-top: 16px; }
.bloco.primeiro { border-top: none; padding-top: 0; margin-top: 0; }
.parte  { font-size: 16px; font-weight: 600; color: #f4f4f5; margin-bottom: 2px; }
.local  { font-size: 12px; color: #71717a; margin-bottom: 12px; }

.painel { display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }
.col    { flex: 1 1 260px; min-width: 240px; }
.foto-col { flex: 0 1 300px; }
.titulo { font-size: 12px; text-transform: uppercase; letter-spacing: .4px;
          color: #71717a; margin-bottom: 10px; }
.conta  { background: #27272a; color: #a1a1aa; border-radius: 8px;
          padding: 0 7px; margin-left: 6px; }

.foto   { max-width: 100%; border: 1px solid #3f3f46; border-radius: 8px;
          display: block; box-shadow: 0 2px 8px rgba(0,0,0,0.25); }
.foto:hover { border-color: #52525b; }
.semfoto { color: #71717a; font-size: 13px; border: 1px dashed #3f3f46;
           border-radius: 8px; padding: 18px; text-align: center; }
.nada   { color: #71717a; padding: 8px; }
.dica   { display: block; font-size: 11px; color: #52525b; margin-top: 4px; }

table { border-collapse: collapse; width: 100%; }
.ficha th { text-align: left; font-weight: 400; color: #71717a;
            font-size: 12px; padding: 4px 12px 4px 0; white-space: nowrap;
            vertical-align: top; }
/* tabular-nums aqui SIM: sao colunas que alinham verticalmente */
.ficha td { color: #f4f4f5; font-size: 13px; padding: 4px 0;
            font-variant-numeric: tabular-nums; }

.sobras td { padding: 5px 0; border-bottom: 1px solid #27272a;
             font-size: 13px; vertical-align: top; }
.sobras tr:last-child td { border-bottom: none; }
.it  { color: #a1a1aa; }
.obs { font-size: 11px; color: #52525b; }
.cod { color: #f4f4f5; font-family: ui-monospace, "Cascadia Code", monospace;
       padding-left: 12px !important; white-space: nowrap; }
.qt  { color: #71717a; text-align: right; padding-left: 10px !important;
       white-space: nowrap; }
</style>
"""

no(id="painel_placa", type="ui-template", z="flow_monitor", group=G_PLACA,
   name="dados de placa", order=1, width="12", height="13",
   head="", format=PLACA, storeOutMessages=True, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=500, wires=[[]])

CADASTRO = r"""
<template>
    <div class="tela">
        <h2>Cadastro de dispositivos</h2>
        <p class="ajuda">
            Todo ESP32 ou inversor que comeca a publicar aparece aqui ate ser
            atribuido a um ativo. Ligue o dispositivo na rede e ele surge
            sozinho — nao ha nada a digitar antes.
        </p>

        <!-- ---------------- Dispositivos novos ---------------- -->
        <div class="secao">
            <div class="titulo">
                Aguardando cadastro
                <span v-if="novos.length" class="conta">{{ novos.length }}</span>
            </div>

            <div v-if="!novos.length" class="vazio">
                Nenhum dispositivo pendente — todos os que estao publicando ja
                pertencem a um ativo.
            </div>

            <table v-else class="lista">
                <tr v-for="d in novos" :key="d.id"
                    :class="{ sel: sel && sel.id === d.id }"
                    @click="escolher(d)">
                    <td class="id">
                        {{ d.id }}
                        <span class="tipo" :class="d.tipo">{{ d.tipo }}</span>
                    </td>
                    <td class="resumo">{{ d.resumo }}</td>
                    <td class="visto" :class="{ mudo: d.mudo }">
                        {{ d.mudo ? 'sem dados' : 'visto ha ' + d.visto }}
                    </td>
                    <td class="acao">{{ sel && sel.id === d.id ? '✓' : '›' }}</td>
                </tr>
            </table>
        </div>

        <!-- ---------------- Formulario ---------------- -->
        <div v-if="sel" class="secao form">
            <div class="titulo">
                Atribuir <code>{{ sel.id }}</code>
                <span class="tipo" :class="sel.tipo">{{ sel.tipo }}</span>
            </div>

            <div class="linha">
                <label>Ativo</label>
                <select v-model="ativo">
                    <option value="">— escolha —</option>
                    <option v-for="a in ativos" :key="a" :value="a">{{ a }}</option>
                    <option value="__novo__">+ novo ativo…</option>
                </select>
            </div>

            <div class="linha" v-if="ativo === '__novo__'">
                <label>Nome do ativo</label>
                <input v-model="ativo_novo" placeholder="ex.: Caldeira 02">
            </div>

            <div class="linha" v-if="ativo === '__novo__'">
                <label>Local</label>
                <input v-model="local" placeholder="ex.: Casa de Caldeiras — Setor A">
            </div>

            <div class="linha">
                <label>Parte</label>
                <input v-model="parte" placeholder="ex.: Motor 1, Bomba, Ventilador">
            </div>

            <div class="linha" v-if="sel.tipo === 'inversor'">
                <label>TAG do inversor</label>
                <input v-model="tag" placeholder="ex.: U11">
            </div>

            <p class="nota" v-if="sel.tipo === 'inversor'">
                O inversor entra como fonte de corrente da parte. Se essa parte
                ja tem um ESP32 cadastrado, os dois passam a alimentar o mesmo
                equipamento.
            </p>

            <div class="botoes">
                <button class="ok" :disabled="!valido" @click="salvar">
                    Cadastrar
                </button>
                <button class="cancelar" @click="sel = null">Cancelar</button>
            </div>

            <div v-if="aviso" class="aviso">{{ aviso }}</div>
        </div>

        <!-- ---------------- Ja cadastrados ---------------- -->
        <div class="secao">
            <div class="titulo">Ja cadastrados</div>
            <div v-if="!Object.keys(mapa).length" class="vazio">
                Nenhum ativo cadastrado ainda.
            </div>
            <table v-else class="lista compacta">
                <template v-for="(cfg, nome) in mapa">
                    <tr class="pai" :key="nome">
                        <td colspan="3"><b>{{ nome }}</b>
                            <span v-if="cfg.local" class="local">{{ cfg.local }}</span>
                        </td>
                    </tr>
                    <tr v-for="(pt, pn) in (cfg.partes || {})" :key="nome + '/' + pn">
                        <td class="parte-nome">└ {{ pn }}</td>
                        <td class="devs">
                            <span v-if="pt.esp32"><code>{{ pt.esp32 }}</code></span>
                            <span v-if="pt.inversor">
                                <code>{{ pt.inversor }}</code>
                                <span v-if="pt.tag_inversor" class="tagi">{{ pt.tag_inversor }}</span>
                            </span>
                        </td>
                        <td class="acao">
                            <button class="mini" @click="remover(nome, pn)">remover</button>
                        </td>
                    </tr>
                </template>
            </table>
        </div>
    </div>
</template>

<script>
export default {
    data () {
        return {
            novos: [], ativos: [], mapa: {},
            sel: null, ativo: '', ativo_novo: '', local: '', parte: '', tag: '',
            aviso: ''
        }
    },
    computed: {
        valido () {
            const a = (this.ativo === '__novo__') ? this.ativo_novo.trim() : this.ativo;
            return !!a && !!this.parte.trim();
        }
    },
    methods: {
        escolher (d) {
            this.sel = d;
            this.aviso = '';
            this.parte = ''; this.tag = ''; this.ativo = ''; this.ativo_novo = '';
        },
        salvar () {
            const alvo = (this.ativo === '__novo__')
                ? this.ativo_novo.trim() : this.ativo;
            this.send({ payload: {
                acao: 'atribuir',
                dispositivo: this.sel.id,
                tipo: this.sel.tipo,
                ativo: alvo,
                local: this.local.trim(),
                parte: this.parte.trim(),
                tag_inversor: this.tag.trim()
            } });
            this.aviso = 'Enviado. A lista atualiza em alguns segundos.';
            this.sel = null;
        },
        remover (ativo, parte) {
            this.send({ payload: { acao: 'remover', ativo: ativo, parte: parte } });
        }
    },
    watch: {
        msg: {
            immediate: true,
            handler (m) {
                const p = (m && m.payload) || {};
                if (!p.novos && !p.mapa) { return; }
                this.novos = p.novos || [];
                this.ativos = p.ativos || [];
                this.mapa = p.mapa || {};
                // Se o dispositivo selecionado sumiu da lista, ele foi
                // cadastrado -- fecha o formulario sozinho.
                if (this.sel && !this.novos.find(d => d.id === this.sel.id)) {
                    this.sel = null;
                }
            }
        }
    }
}
</script>

<style scoped>
.tela  { color: #a1a1aa; font-size: 14px; }
h2     { color: #f4f4f5; font-size: 22px; margin: 0 0 4px; font-weight: 600; }
.ajuda { color: #71717a; font-size: 13px; margin: 0 0 20px; max-width: 70ch; line-height: 1.4; }

.secao  { margin-bottom: 24px; }
.titulo { font-size: 12px; text-transform: uppercase; letter-spacing: .4px;
          color: #71717a; margin-bottom: 10px; }
.conta  { background: #27272a; color: #f4f4f5; border-radius: 8px;
          padding: 0 7px; margin-left: 6px; }
.vazio  { color: #52525b; font-size: 13px; border: 1px dashed #3f3f46;
          border-radius: 8px; padding: 16px; }

table  { border-collapse: collapse; width: 100%; }
.lista td { padding: 10px 12px; border-bottom: 1px solid #27272a;
            vertical-align: middle; }
.lista tr { cursor: pointer; transition: background .15s ease; }
.lista tr:hover td { background: #1e1e22; }
.lista tr.sel td    { background: #1d2a3a; }
.compacta tr { cursor: default; }
.compacta tr:hover td { background: transparent; }

.id   { color: #f4f4f5; font-family: ui-monospace, "Cascadia Code", monospace; }
.tipo { font-size: 10px; text-transform: uppercase; letter-spacing: .3px;
        border: 1px solid; border-radius: 8px; padding: 1px 6px; margin-left: 8px; }
.tipo.esp32    { color: #3987e5; border-color: #3987e5; }
.tipo.inversor { color: #f59e0b; border-color: #f59e0b; }
.tipo.desconhecido { color: #71717a; border-color: #3f3f46; }

.resumo { color: #a1a1aa; font-variant-numeric: tabular-nums; }
.visto  { color: #71717a; font-size: 12px; text-align: right; }
.visto.mudo { color: #ef4444; }
.acao   { color: #71717a; text-align: right; width: 90px; }

.form   { background: #151518; border: 1px solid #3f3f46; border-radius: 10px; padding: 18px; }
.linha  { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
label   { width: 130px; color: #71717a; font-size: 13px; flex: none; }
input, select {
    background: #0b0b0c; color: #f4f4f5; border: 1px solid #3f3f46;
    border-radius: 6px; padding: 8px 12px; font-size: 14px;
    flex: 1; max-width: 420px; font-family: inherit;
}
input:focus, select:focus { outline: none; border-color: #3987e5; }
.nota { color: #71717a; font-size: 12px; margin: 4px 0 14px; max-width: 70ch; line-height: 1.4; }

.botoes { display: flex; gap: 10px; margin-top: 16px; }
button  { border: none; border-radius: 6px; padding: 10px 20px; font-size: 14px;
          cursor: pointer; font-family: inherit; transition: filter .15s ease; }
button:hover { filter: brightness(1.1); }
.ok       { background: #3987e5; color: #ffffff; }
.ok:disabled { background: #27272a; color: #52525b; cursor: not-allowed; filter: none; }
.cancelar { background: transparent; color: #a1a1aa; border: 1px solid #3f3f46; }
.mini     { background: transparent; color: #a1a1aa; border: 1px solid #3f3f46;
            font-size: 11px; padding: 4px 10px; border-radius: 6px; }
.mini:hover { color: #ef4444; border-color: #ef4444; filter: none; }
.aviso    { color: #22c55e; font-size: 13px; margin-top: 12px; }

.pai td   { padding-top: 16px; color: #f4f4f5; }
.local    { color: #71717a; font-size: 12px; margin-left: 10px; font-weight: 400; }
.parte-nome { color: #a1a1aa; padding-left: 14px !important; }
.devs code  { color: #f4f4f5; font-family: ui-monospace, monospace;
              margin-right: 10px; }
.tagi { color: #f59e0b; font-size: 11px; border: 1px solid #f59e0b;
        border-radius: 8px; padding: 0 6px; margin-left: 4px; }
</style>
"""

no(id="tela_cadastro", type="ui-template", z="flow_monitor", group=G_CAD,
   name="cadastro de dispositivos", order=1, width="12", height="14",
   head="", format=CADASTRO, storeOutMessages=True, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=800, wires=[["aplicar_cadastro"]])

no(id="tick_cad_ui", type="inject", z="flow_monitor",
   name="atualizar tela (3s)", props=[{"p": "payload"}], repeat="3",
   crontab="", once=True, onceDelay="2", topic="", payload="",
   payloadType="date", x=140, y=800, wires=[["montar_cadastro"]])

no(id="montar_cadastro", type="function", z="flow_monitor",
   name="montar tela de cadastro", outputs=1, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=380, y=800,
   wires=[["tela_cadastro"]],
   func=r"""
// Alimenta a tela com o que o renderizador ja apurou: quem esta publicando
// sem dono, quais ativos existem, e o mapa atual.
return { payload: {
    novos:  flow.get('nao_atribuidos') || [],
    ativos: flow.get('ativos_existentes') || [],
    mapa:   flow.get('cadastro') || {}
} };
""")

no(id="aplicar_cadastro", type="function", z="flow_monitor",
   name="aplicar cadastro", outputs=1, timeout=0, noerr=0,
   initialize="", finalize="", libs=[], x=860, y=800,
   wires=[["gravar_cadastro"]],
   func=r"""
// Aplica a alteracao no cadastro e devolve o JSON inteiro para gravacao.
//
// Le do flow context e nao do disco: o arquivo e relido a cada 60s, entao
// gravar por cima do que esta em memoria e coerente -- e evita uma leitura
// sincrona no meio da interacao do usuario.
const p = msg.payload || {};
const cad = JSON.parse(JSON.stringify(flow.get('cadastro') || {}));

if (p.acao === 'remover') {
    const at = cad[p.ativo];
    if (at && at.partes) {
        delete at.partes[p.parte];
        // Ativo sem nenhuma parte nao tem por que continuar existindo.
        if (!Object.keys(at.partes).length) { delete cad[p.ativo]; }
    }
} else if (p.acao === 'atribuir') {
    if (!p.ativo || !p.parte) { node.warn('cadastro incompleto, ignorado'); return null; }

    if (!cad[p.ativo]) { cad[p.ativo] = { partes: {} }; }
    if (p.local) { cad[p.ativo].local = p.local; }
    if (!cad[p.ativo].partes) { cad[p.ativo].partes = {}; }
    if (!cad[p.ativo].partes[p.parte]) { cad[p.ativo].partes[p.parte] = {}; }

    const pt = cad[p.ativo].partes[p.parte];
    if (p.tipo === 'inversor') {
        pt.inversor = p.dispositivo;
        if (p.tag_inversor) { pt.tag_inversor = p.tag_inversor; }
    } else {
        pt.esp32 = p.dispositivo;
    }
} else {
    return null;
}

// Atualiza a memoria na hora: a tela reflete a mudanca no proximo ciclo de
// 3s, sem esperar a releitura do arquivo.
flow.set('cadastro', cad);

msg.filename = (env.get('IOT_DADOS') || '/opt/iot/dados') + '/ativos.json';
msg.payload = JSON.stringify(cad, null, 2) + '\n';
return msg;
""")

no(id="gravar_cadastro", type="file", z="flow_monitor", name="ativos.json",
   filename="filename", filenameType="msg", appendNewline=False,
   createDir=True, overwriteFile="true", encoding="utf8",
   x=1080, y=800, wires=[[]])

ROADMAP_IA = r"""
<template>
    <div class="rm">
        <div class="tag">Em desenvolvimento</div>
        <h2>Detecção de anomalia e diagnóstico</h2>
        <p class="lead">
            O painel hoje compara cada grandeza com um limite. O próximo passo
            é aprender o que é normal <em>para cada ativo</em> e apontar desvio
            antes de qualquer limite ser cruzado.
        </p>

        <div class="escada">
            <div v-for="d in degraus" :key="d.n" class="degrau" :class="d.estado">
                <div class="num">{{ d.n }}</div>
                <div class="txt">
                    <div class="tit">
                        {{ d.titulo }}
                        <span class="pill" :class="d.estado">{{ d.rotulo }}</span>
                    </div>
                    <div class="ent">{{ d.entrega }}</div>
                    <div class="pre">Precisa de: {{ d.precisa }}</div>
                </div>
            </div>
        </div>

        <p class="nota">
            O degrau 4 — o que se costuma imaginar ao ouvir “IA preditiva” —
            exige histórico de máquinas que falharam <em>com registro</em>, que
            quase nenhuma planta tem no início. Por isso a ordem é 2 e 3
            primeiro: funcionam sem histórico de falha, e vão acumulando o dado
            que o degrau 4 precisa.
        </p>
    </div>
</template>

<script>
export default {
    data () {
        return { degraus: [
            { n: 1, titulo: 'Monitorar', estado: 'ok', rotulo: 'operando',
              entrega: 'Valor medido contra limite, por ativo, com a corrente nominal da placa.',
              precisa: 'só o sensor — é o que está no ar agora' },
            { n: 2, titulo: 'Detecção de anomalia', estado: 'prox', rotulo: 'próximo',
              entrega: '"Fora do normal desta máquina", sem depender de limite fixo.',
              precisa: '2 a 4 semanas de operação normal para formar a linha de base' },
            { n: 3, titulo: 'Diagnóstico', estado: 'fut', rotulo: 'médio prazo',
              entrega: '"É rolamento, desbalanceamento ou barra de rotor" — não só "está ruim".',
              precisa: 'análise espectral (FFT) e o código do rolamento no cadastro' },
            { n: 4, titulo: 'Prognóstico (RUL)', estado: 'fut', rotulo: 'longo prazo',
              entrega: 'Estimativa de vida útil remanescente: "falha provável em ~X dias".',
              precisa: 'histórico de falhas reais registradas (run-to-failure)' }
        ] }
    }
}
</script>

<style scoped>
.rm   { color: #a1a1aa; max-width: 90ch; }
.tag  { display: inline-block; font-size: 11px; text-transform: uppercase;
        letter-spacing: .5px; color: #f59e0b; border: 1px solid #f59e0b;
        border-radius: 10px; padding: 2px 10px; margin-bottom: 12px; }
h2    { color: #f4f4f5; font-size: 22px; margin: 0 0 8px; font-weight: 600; }
.lead { font-size: 14px; line-height: 1.6; margin: 0 0 26px; }
em    { color: #f4f4f5; font-style: normal; }

.escada { display: flex; flex-direction: column; gap: 2px; }
.degrau { display: flex; gap: 16px; padding: 14px 16px; border-left: 3px solid #27272a;
          background: #151518; border-radius: 0 8px 8px 0; }
.degrau.ok   { border-left-color: #22c55e; }
.degrau.prox { border-left-color: #3b82f6; }
.degrau.fut  { border-left-color: #3f3f46; }

.num  { font-size: 22px; font-weight: 600; color: #52525b; width: 26px;
        flex: none; text-align: center; font-variant-numeric: tabular-nums; }
.tit  { color: #f4f4f5; font-size: 15px; font-weight: 600; margin-bottom: 3px; }
.ent  { font-size: 13px; color: #a1a1aa; margin-bottom: 3px; }
.pre  { font-size: 12px; color: #71717a; }

.pill { font-size: 10px; text-transform: uppercase; letter-spacing: .4px;
        border-radius: 8px; padding: 1px 8px; margin-left: 10px;
        font-weight: 400; vertical-align: 2px; }
.pill.ok   { color: #22c55e; border: 1px solid #22c55e; }
.pill.prox { color: #3b82f6; border: 1px solid #3b82f6; }
.pill.fut  { color: #71717a; border: 1px solid #3f3f46; }

.nota { font-size: 13px; line-height: 1.6; color: #71717a; margin-top: 26px;
        border-top: 1px solid #27272a; padding-top: 16px; }
</style>
"""

ROADMAP_REL = r"""
<template>
    <div class="rm">
        <div class="tag">Em desenvolvimento</div>
        <h2>Relatórios e histórico</h2>
        <p class="lead">
            O painel mostra o <em>agora</em>. Relatório de tendência, comparação
            entre períodos e exportação exigem gravar cada medição — e MQTT
            transporta, não armazena.
        </p>

        <div class="camadas">
            <div v-for="c in camadas" :key="c.nome" class="camada" :class="c.estado">
                <div class="cab">
                    <span class="nome">{{ c.nome }}</span>
                    <span class="pill" :class="c.estado">{{ c.rotulo }}</span>
                </div>
                <div class="desc">{{ c.desc }}</div>
            </div>
        </div>

        <p class="nota">
            A decisão de projeto é usar <b>PostgreSQL + TimescaleDB</b>: um único
            banco serve o Grafana, a camada de IA e o Power BI — que tem conector
            nativo de PostgreSQL, e nenhum de MQTT. A alternativa comum
            (InfluxDB) exigiria uma ponte só para o Power BI.
        </p>
    </div>
</template>

<script>
export default {
    data () {
        return { camadas: [
            { nome: 'Ao vivo', estado: 'ok', rotulo: 'operando',
              desc: 'Este painel: valor instantâneo, estado e alarme. Funciona sem internet.' },
            { nome: 'Histórico (PostgreSQL + TimescaleDB)', estado: 'prox', rotulo: 'próximo',
              desc: 'Grava cada medição na borda. É o que destrava tudo abaixo.' },
            { nome: 'Gráficos de engenharia (Grafana)', estado: 'fut', rotulo: 'depois do banco',
              desc: 'Tendência longa, zoom, comparação entre ativos e entre períodos.' },
            { nome: 'Relatório corporativo (Power BI)', estado: 'fut', rotulo: 'depois do banco',
              desc: 'KPIs e relatórios lendo a mesma base, pelo conector PostgreSQL.' }
        ] }
    }
}
</script>

<style scoped>
.rm   { color: #a1a1aa; max-width: 90ch; }
.tag  { display: inline-block; font-size: 11px; text-transform: uppercase;
        letter-spacing: .5px; color: #f59e0b; border: 1px solid #f59e0b;
        border-radius: 10px; padding: 2px 10px; margin-bottom: 12px; }
h2    { color: #f4f4f5; font-size: 22px; margin: 0 0 8px; font-weight: 600; }
.lead { font-size: 14px; line-height: 1.6; margin: 0 0 26px; }
em, b { color: #f4f4f5; font-style: normal; font-weight: 600; }

.camadas { display: flex; flex-direction: column; gap: 2px; }
.camada  { padding: 14px 16px; border-left: 3px solid #27272a;
           background: #151518; border-radius: 0 8px 8px 0; }
.camada.ok   { border-left-color: #22c55e; }
.camada.prox { border-left-color: #3b82f6; }
.camada.fut  { border-left-color: #3f3f46; }
.cab  { display: flex; align-items: center; gap: 10px; margin-bottom: 3px; }
.nome { color: #f4f4f5; font-size: 15px; font-weight: 600; }
.desc { font-size: 13px; color: #a1a1aa; }

.pill { font-size: 10px; text-transform: uppercase; letter-spacing: .4px;
        border-radius: 8px; padding: 1px 8px; }
.pill.ok   { color: #22c55e; border: 1px solid #22c55e; }
.pill.prox { color: #3b82f6; border: 1px solid #3b82f6; }
.pill.fut  { color: #71717a; border: 1px solid #3f3f46; }

.nota { font-size: 13px; line-height: 1.6; color: #71717a; margin-top: 26px;
        border-top: 1px solid #27272a; padding-top: 16px; }
</style>
"""

# As paginas de IA e Relatorios ainda nao tem funcionalidade. Em vez de
# item de menu que abre tela vazia -- pior que nao existir, sobretudo em
# demonstracao -- elas mostram o roadmap: o que entrega, o que falta e por
# que a ordem e essa. Honesto e util.
no(id="pg_ia_conteudo", type="ui-template", z="flow_monitor", group=G_IA,
   name="roadmap de IA", order=1, width="12", height="12",
   head="", format=ROADMAP_IA, storeOutMessages=False, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=880, wires=[[]])

no(id="pg_rel_conteudo", type="ui-template", z="flow_monitor", group=G_REL,
   name="roadmap de relatorios", order=1, width="12", height="12",
   head="", format=ROADMAP_REL, storeOutMessages=False, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=940, wires=[[]])

# width/height em 0 = automatico, quem dimensiona e o grupo. Fixar 12x16
# aqui colapsava o contêiner de rolagem interno da tabela para 38px: as
# linhas existiam no DOM e ficavam cortadas, dando cara de tela vazia.
LINHA_TEMPO = r"""
<template>
    <div class="lt">
        <div class="cab">
            <span class="tit">{{ janela }}</span>
            <span class="leg">
                <span class="pt" style="background:#f59e0b"></span> atencao
                <span class="pt" style="background:#ef4444"></span> critico
                <span class="pt" style="background:#71717a"></span> sem dados
            </span>
        </div>

        <div class="faixa" ref="faixa" @mouseleave="dica = null"
             :style="{ height: (18 + faixas * 14) + 'px' }">
            <!-- grade de horas -->
            <div v-for="m in marcas" :key="'m'+m.pct" class="marca"
                 :style="{ left: m.pct + '%' }">
                <span class="rot">{{ m.rot }}</span>
            </div>

            <!-- trilho -->
            <div v-for="k in faixas" :key="'t'+k" class="trilho"
                 :style="{ top: (2 + (k-1) * 14) + 'px' }"></div>

            <!-- eventos: barra quando tem duracao, tick quando e instantaneo -->
            <div v-for="(e, i) in eventos" :key="i"
                 class="evt" :class="{ aberto: e.aberto }"
                 :style="{ left: e.ini + '%', width: e.larg + '%',
                           top: (2 + e.faixa * 14) + 'px', background: e.cor }"
                 @mouseenter="mostrar(e, $event)">
            </div>

            <div v-if="!eventos.length" class="vazio">
                Nenhum evento nas ultimas 24 horas
            </div>
        </div>

        <!-- tooltip -->
        <div v-if="dica" class="dica" :style="{ left: dica.x + 'px' }">
            <div class="d-l1">
                <span :style="{ color: dica.cor }">{{ dica.simb }}</span>
                <b>{{ dica.ativo }}</b>
                <span v-if="dica.parte" class="d-parte">› {{ dica.parte }}</span>
                <span class="d-tempo">{{ dica.quando }} · {{ dica.duracao }}</span>
            </div>
            <div class="d-mot">{{ dica.motivos }}</div>
        </div>
    </div>
</template>

<script>
export default {
    data () { return { eventos: [], marcas: [], janela: '', faixas: 1, dica: null } },
    methods: {
        mostrar (e, ev) {
            const f = this.$refs.faixa.getBoundingClientRect();
            // Prende o tooltip dentro da faixa, senao ele escapa nas pontas.
            const x = Math.min(Math.max(ev.clientX - f.left - 150, 0), f.width - 320);
            this.dica = Object.assign({}, e, { x: x });
        }
    },
    watch: {
        msg: {
            immediate: true,
            handler (m) {
                const p = (m && m.payload) || {};
                if (!p.eventos) { return; }
                this.eventos = p.eventos;
                this.marcas = p.marcas || [];
                this.janela = p.janela || '';
                this.faixas = p.faixas || 1;
            }
        }
    }
}
</script>

<style scoped>
.lt   { position: relative; }
.cab  { display: flex; justify-content: space-between; align-items: baseline;
        margin-bottom: 6px; }
.tit  { font-size: 11px; text-transform: uppercase; letter-spacing: .4px;
        color: #71717a; }
.leg  { font-size: 11px; color: #71717a; }
.pt   { display: inline-block; width: 8px; height: 8px; border-radius: 2px;
        margin: 0 4px 0 12px; vertical-align: 0; }

.faixa   { position: relative; min-height: 32px; }
.trilho  { position: absolute; left: 0; right: 0; height: 10px;
           background: #1c1c1f; border: 1px solid #27272a; border-radius: 3px; }

.marca   { position: absolute; top: 0; bottom: 16px; width: 1px;
           background: #27272a; }
.rot     { position: absolute; bottom: -14px; left: 3px; font-size: 10px;
           color: #52525b; white-space: nowrap; }

/* Evento com duracao vira barra; instantaneo tem largura minima e vira
   tick. Assim "piscou uma vez" e "esta ha 3 horas" nao parecem iguais. */
.evt     { position: absolute; height: 12px; border-radius: 2px;
           min-width: 3px; cursor: pointer; opacity: .85;
           transition: opacity .15s, transform .15s; }
.evt:hover { opacity: 1; transform: scaleY(1.35); }
/* Evento ainda aberto ganha contorno claro: e o que exige acao agora. */
.evt.aberto { box-shadow: 0 0 0 1px #f4f4f5; }

.vazio { position: absolute; top: 12px; left: 12px; font-size: 12px;
         color: #52525b; }

.dica  { position: absolute; top: -2px; z-index: 20; min-width: 300px;
         max-width: 460px; background: #1e1e22; border: 1px solid #3f3f46;
         border-radius: 8px; padding: 7px 12px;
         box-shadow: 0 6px 18px rgba(0,0,0,.55); pointer-events: none; }
.d-l1    { font-size: 12px; color: #f4f4f5; white-space: nowrap; }
.d-l1 b  { font-weight: 600; margin-left: 4px; }
.d-parte { color: #a1a1aa; margin-left: 4px; }
.d-tempo { color: #71717a; font-size: 11px; margin-left: 10px; }
.d-mot   { color: #a1a1aa; font-size: 12px; margin-top: 3px; line-height: 1.35; }
</style>
"""

no(id="linha_tempo", type="ui-template", z="flow_monitor", group=G_LINHA,
   name="linha do tempo de eventos", order=1, width="0", height="0",
   head="", format=LINHA_TEMPO, storeOutMessages=True, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=1000, wires=[[]])

no(id="tabela_planta", type="ui-table", z="flow_monitor", group=G_ATIVOS_TAB,
   name="todos os ativos", label="", order=1, width="0", height="0",
   maxrows=0, passthru=False, autocols=True, columns=[],
   mobileBreakpoint="", mobileBreakpointType="none",
   showSearch=True, deselect=True,
   action="replace", selectionType="none", className="",
   x=640, y=300, wires=[[]])

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
   order=1, width="12", height="4", name="resumo", label="",
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
        <div v-for="t in tiles" :key="t.nome" class="tile"
             :class="{ vazio: t.texto === '--' || t.texto === 'FALHA' }">
            <div class="rot">{{ t.nome }}</div>
            <div class="val">
                {{ t.texto }}<span v-if="t.un" class="un">{{ t.un }}</span>
                <span class="tend" :style="{ color: t.tend.cor }">{{ t.tend.simb }}</span>
            </div>
            <div class="trilho">
                <div class="preenche" :style="{ width: t.pct + '%', background: t.cor }"></div>
            </div>
            <div class="estado" :style="{ color: t.cor }">{{ t.simb }} {{ t.rotulo }}</div>
            <svg v-if="t.spark && t.spark.length" class="spark" viewBox="0 0 100 30" preserveAspectRatio="none">
                <polyline fill="none" stroke="#52525b" stroke-width="2"
                          :points="sparkPoints(t.spark)" />
                <polyline fill="none" :stroke="t.cor" stroke-width="2.5"
                          :points="sparkPoints(t.spark)" />
            </svg>
        </div>
    </div>
</template>

<script>
export default {
    data () { return { tiles: [] } },
    methods: {
        sparkPoints (arr) {
            if (!arr || arr.length < 2) { return ''; }
            const min = Math.min(...arr), max = Math.max(...arr);
            const rng = (max === min) ? 1 : (max - min);
            const step = 100 / (arr.length - 1);
            return arr.map((v, i) => {
                const x = i * step;
                const y = 30 - ((v - min) / rng) * 28 - 1;
                return x.toFixed(1) + ',' + y.toFixed(1);
            }).join(' ');
        }
    },
    watch: {
        msg: {
            immediate: true,
            handler (m) { if (m && m.payload) { this.tiles = m.payload } }
        }
    }
}
</script>

<style scoped>
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
.tile  { background: #151518; border: 1px solid #3f3f46; border-radius: 10px;
         padding: 14px; transition: background .2s ease; }
.tile:hover { background: #1e1e22; }
.tile.vazio { opacity: .85; }
.rot   { font-size: 11px; color: #71717a; text-transform: uppercase;
         letter-spacing: .5px; margin-bottom: 4px; }
.val   { font-size: 28px; line-height: 1.15; color: #f4f4f5;
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.un    { font-size: 13px; color: #a1a1aa; margin-left: 4px; }
.tend  { font-size: 14px; margin-left: 6px; }
.trilho   { height: 4px; background: #27272a; border-radius: 2px; margin: 8px 0 5px; overflow: hidden; }
.preenche { height: 100%; border-radius: 2px; transition: width .4s ease, background .3s ease; }
.estado   { font-size: 11px; font-weight: 600; text-transform: uppercase;
            letter-spacing: .4px; }
.spark { width: 100%; height: 30px; margin-top: 8px; display: block; }
</style>
"""

no(id="stat_tiles", type="ui-template", z="flow_monitor", group=G_TILES,
   name="stat tiles do ativo", order=1, width="6", height="5",
   head="", format=STAT_TILES, storeOutMessages=True, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=420, wires=[[]])


ALARMES_KPI = r"""
<template>
    <div class="kpi-bar">
        <div class="kpi total">
            <div class="rot">Eventos</div>
            <div class="val">{{ kpi.total }}</div>
        </div>
        <div class="kpi abertos">
            <div class="rot">Abertos</div>
            <div class="val">{{ kpi.abertos }}</div>
        </div>
        <div class="kpi crit">
            <div class="rot">Críticos</div>
            <div class="val">{{ kpi.critico }}</div>
        </div>
        <div class="kpi atn">
            <div class="rot">Atenção</div>
            <div class="val">{{ kpi.atencao }}</div>
        </div>
        <div class="kpi off">
            <div class="rot">Sem dados</div>
            <div class="val">{{ kpi.sem_dados }}</div>
        </div>
    </div>
</template>

<script>
export default {
    data () { return { kpi: { total:0, abertos:0, critico:0, atencao:0, sem_dados:0 } } },
    watch: {
        msg: {
            immediate: true,
            handler (m) { if (m && m.payload) { this.kpi = m.payload } }
        }
    }
}
</script>

<style scoped>
.kpi-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 12px; }
.kpi { background: #151518; border: 1px solid #3f3f46; border-radius: 10px; padding: 12px 14px; text-align: center; }
.kpi .rot { font-size: 11px; color: #71717a; text-transform: uppercase; letter-spacing: .4px; margin-bottom: 4px; }
.kpi .val { font-size: 26px; font-weight: 600; color: #f4f4f5; }
.kpi.crit .val { color: #ef4444; }
.kpi.atn .val { color: #f59e0b; }
.kpi.off .val { color: #71717a; }
.kpi.abertos .val { color: #ef4444; }
</style>
"""

no(id="alarmes_kpi", type="ui-template", z="flow_monitor", group=G_ALARMES_KPI,
   name="KPI de alarmes", order=1, width="12", height="2",
   head="", format=ALARMES_KPI, storeOutMessages=True, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=540, wires=[[]])


ALARMES_LISTA = r"""
<template>
    <div class="tela">
        <div v-if="!eventos.length" class="vazio">
            Nenhum alarme registrado ainda. Quando um ativo entrar em atenção,
            crítico ou ficar sem dados, o evento aparece aqui.
        </div>
        <div v-else class="lista">
            <div v-for="(e, i) in eventos" :key="i" class="evt" :class="e.estadoCls">
                <div class="cab">
                    <span class="badge" :style="{ background: e.cor, color: '#fff' }">{{ e.estado }}</span>
                    <span class="hora">{{ e.inicio }}</span>
                    <span class="dur">{{ e.duracao }}</span>
                </div>
                <div class="ativo">
                    {{ e.ativo }}<span v-if="e.parte"> › {{ e.parte }}</span>
                </div>
                <div class="motivo">{{ e.motivos }}</div>
            </div>
        </div>
        <button v-if="eventos.length" class="limpar" @click="limpar">Limpar histórico</button>
    </div>
</template>

<script>
export default {
    data () { return { eventos: [] } },
    methods: {
        limpar () { this.send({ payload: 'limpar' }) }
    },
    watch: {
        msg: {
            immediate: true,
            handler (m) {
                if (m && Array.isArray(m.payload)) {
                    this.eventos = m.payload.map(e => Object.assign({}, e, {
                        estadoCls: e.cor === '#ef4444' ? 'crit' :
                                   e.cor === '#f59e0b' ? 'atn' : 'off'
                    }));
                }
            }
        }
    }
}
</script>

<style scoped>
.tela { color: #a1a1aa; font-size: 14px; }
.vazio { color: #71717a; border: 1px dashed #3f3f46; border-radius: 10px; padding: 20px; text-align: center; }
.lista { display: flex; flex-direction: column; gap: 10px; }
.evt { background: #151518; border: 1px solid #3f3f46; border-left: 4px solid #71717a;
       border-radius: 10px; padding: 12px 14px; transition: background .2s ease; }
.evt:hover { background: #1e1e22; }
.evt.crit { border-left-color: #ef4444; }
.evt.atn  { border-left-color: #f59e0b; }
.evt.off  { border-left-color: #71717a; }
.cab { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.badge { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .4px;
         border-radius: 8px; padding: 2px 8px; }
.hora { font-size: 12px; color: #71717a; }
.dur  { font-size: 12px; color: #52525b; margin-left: auto; }
.ativo { font-size: 15px; color: #f4f4f5; font-weight: 500; margin-bottom: 3px; }
.ativo span { color: #a1a1aa; font-weight: 400; }
.motivo { font-size: 13px; color: #a1a1aa; line-height: 1.35; }
.limpar { margin-top: 14px; background: transparent; color: #a1a1aa; border: 1px solid #3f3f46;
          border-radius: 6px; padding: 8px 16px; cursor: pointer; font-size: 13px; }
.limpar:hover { color: #ef4444; border-color: #ef4444; }
</style>
"""

no(id="alarmes_lista", type="ui-template", z="flow_monitor", group=G_ALARMES_LISTA,
   name="lista de alarmes", order=1, width="12", height="14",
   head="", format=ALARMES_LISTA, storeOutMessages=True, passthru=False,
   resendOnRefresh=True, templateScope="local", className="",
   x=640, y=580, wires=[["limpar_alarmes"]])

no(id="limpar_alarmes", type="function", z="flow_monitor", name="limpar alarmes",
   outputs=0, timeout=0, noerr=0, initialize="", finalize="", libs=[], x=860, y=580, wires=[],
   func=r"""
// Botao "limpar historico" na tela de alarmes: zera a fila em memoria.
flow.set('historico_alarmes', []);
""")


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


grafico("tend_temp", G_TEND_T, "Temperatura",  "°C", "", "", largura=12)
grafico("tend_vib",  G_TEND_V, "Vibracao RMS", "g",  "0", "", largura=12)
grafico("tend_corr", G_TEND_C, "Corrente",     "A",  "0", "", largura=12)

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

    # Injeta a logo no codigo do no de funcao. Fica so aqui: o corpo da
    # funcao acima usa um marcador, para o gerador seguir legivel.
    for _n in flows:
        if _n.get("id") == "montar_painel":
            _n["func"] = _n["func"].replace("__LOGO_LOCKUP__", LOGO_LOCKUP)
    with open(destino, "w", encoding="utf-8", newline="\n") as f:
        json.dump(flows, f, indent=4, ensure_ascii=False)
        f.write("\n")
    print(f"{len(flows)} nos -> {destino}")
