#!/usr/bin/env python3
"""Telemetria do inversor PowerFlex 525 via EtherNet/IP -> MQTT.

O drive já mede corrente, tensão, frequência e barramento CC — tudo
calibrado de fábrica — e ainda guarda o histórico de falhas. Este sidecar
lê esses parâmetros por mensageria CIP explícita e publica em

    monitoramento/<DEVICE_ID>/inversor

O Node-RED consome esse tópico e alimenta o painel, mantendo todo o
barramento em MQTT.

Payload:

    {
      "ts": 1730800000000,
      "corrente_a": 12.34,
      "tensao_v": 220.5,
      "dc_bus_v": 311.0,
      "frequencia_hz": 60.0,
      "rodando": true,
      "falha": {"codigo": 0, "texto": null},          <- falha ATIVA
      "ultima_falha": {"codigo": 7, "texto": "..."},  <- histórico (b007)
      "status_bruto": 3
    }

⚠️  NÃO VALIDADO EM HARDWARE — mas conferido contra os manuais oficiais:
    520-UM001 (parâmetros b001–b007, escalas, tabela de falhas) e
    520COM-UM001 (objetos CIP do adaptador EtherNet/IP embarcado). Rode
    primeiro com --bancada e confira contra o teclado do drive.

Uso:
    python powerflex_mqtt.py              # serviço: lê e publica em MQTT
    python powerflex_mqtt.py --bancada    # lê tudo uma vez e mostra; sem MQTT

Vários drives, inclusive os encadeados em Multi-Drive atrás de um 525 (mesmo
IP, posição 1 a 4 no nó): liste-os num JSON e aponte PF525_INVERSORES para
ele. Sem a lista, lê o único drive das variáveis de ambiente, como sempre.
Veja o README, seção "Vários inversores e Multi-Drive".

Config por variáveis de ambiente (veja config.example.env).
Dependências em requirements.txt (pycomm3, paho-mqtt).
"""
import json
import logging
import os
import sys
import time

# pycomm3 e paho são importados SÓ na hora de usar, não aqui em cima: com um
# import de topo que falha, este arquivo não pode nem ser carregado sem as
# bibliotecas -- e a lógica pura (escalas, tabela de falhas, decisão de falha
# ativa) fica impossível de testar. Mesma lição do sidecar do Danfoss.

# ------------------------------------------------------------------- Config
PLC_IP    = os.getenv("PF525_IP", "192.168.1.10")
DEVICE_ID = os.getenv("PF525_DEVICE_ID", "powerflex-01")

# Objeto CIP de parâmetros (520COM-UM001, Apêndice C):
#   0x0F Parameter Object     -> valor no ATRIBUTO 1
#   0x93 DPI Parameter Object -> valor no ATRIBUTO 9
# Nos dois a instância é o número do parâmetro (b003 -> 3). A versão
# anterior deixava trocar a classe para 0x93 mas continuava pedindo o
# atributo 1 -- que na 0x93 é "Write Protect Password". Leria outro dado,
# sem erro nenhum.
CLASSE = int(os.getenv("PF525_CLASSE", "0x0F"), 0)
ATRIBUTO_VALOR = {0x0F: 1, 0x93: 9}.get(CLASSE)
if ATRIBUTO_VALOR is None:
    sys.exit(f"PF525_CLASSE={CLASSE:#04x} não suportada: use 0x0F ou 0x93")

# DPI Fault Object, atributo de CLASSE 4 "Fault Trip Instance Read":
# "Fault that tripped the device" (520COM-UM001). É daqui que sai se há
# falha ATIVA -- ver ler_inversor.
CLASSE_FALHA = 0x97
ATRIB_FALHA_ATIVA = 4

# Como a mensagem vai ao drive. O adaptador embarcado não é um roteador, e
# a documentação não deixa claro se ele aceita Unconnected Send (0x52)
# endereçado a si mesmo. 'auto' tenta com e, se o drive recusar, sem --
# e guarda o que funcionou. 'sim'/'nao' fixam um dos dois.
MODO_UCMM = os.getenv("PF525_UNCONNECTED_SEND", "auto").lower()

PORTA_CIP = int(os.getenv("PF525_PORTA", "44818"))
INTERVALO_S = float(os.getenv("PF525_INTERVALO_S", "1.0"))

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

TOPIC_INVERSOR = f"monitoramento/{DEVICE_ID}/inversor"
TOPIC_STATUS = f"monitoramento/{DEVICE_ID}/status"

# ---------------------------------------------------------------------------
#  Parâmetros lidos — grupo b (Basic Display), só leitura.
#
#  Escalas conferidas no 520-UM001 (campo "Display" de cada parâmetro):
#    b001 Output Freq     0.01 Hz
#    b003 Output Current  0.01 A
#    b004 Output Voltage  0.1 V
#    b005 DC Bus Voltage  1 V DC   <- a versão anterior usava 0.1: um
#                                     barramento de 311 V aparecia como 31,1
#    b006 Drive Status    dígitos (Running, Forward, Accel, Decel, Safety)
#    b007 Fault 1 Code    o código da falha MAIS RECENTE -- é HISTÓRICO,
#                         não quer dizer que haja falha agora
# ---------------------------------------------------------------------------
def _escala(nome, padrao):
    return float(os.getenv(f"PF525_ESCALA_{nome}", padrao))


PARAMETROS = {
    # campo no JSON      instância  escala                casas
    "frequencia_hz": (1, _escala("FREQ", "0.01"), 2),
    "corrente_a":    (3, _escala("CORRENTE", "0.01"), 2),
    "tensao_v":      (4, _escala("TENSAO", "0.1"), 1),
    "dc_bus_v":      (5, _escala("DCBUS", "1.0"), 1),
    "status_bruto":  (6, 1.0, 0),
    "ultima_falha":  (7, 1.0, 0),
}

# Abaixo desta frequência de saída consideramos o motor parado.
FREQ_PARADO_HZ = float(os.getenv("PF525_FREQ_PARADO_HZ", "0.1"))

LOG_BRUTO = os.getenv("PF525_LOG_BRUTO", "") not in ("", "0", "false", "False")

# ---------------------------------------------------------------------------
#  Códigos de falha — transcritos da tabela "Drive Error Codes" do
#  520-UM001 (registrador 2101H). A versão anterior tinha quatro traduções
#  erradas (F3, F42, F43, F63) e oito códigos faltando.
# ---------------------------------------------------------------------------
FALHAS = {
    2:   "Entrada auxiliar (parada externa)",
    3:   "Perda de alimentação",
    4:   "Subtensão no barramento CC",
    5:   "Sobretensão no barramento CC",
    6:   "Motor travado",
    7:   "Sobrecarga do motor",
    8:   "Sobretemperatura do dissipador",
    9:   "Sobretemperatura do módulo de controle",
    12:  "Sobrecorrente de hardware (300%)",
    13:  "Falha de aterramento",
    15:  "Perda de carga",
    21:  "Perda de fase na saída",
    29:  "Perda de sinal na entrada analógica",
    33:  "Excesso de tentativas de rearme automático",
    38:  "Curto da fase U para o terra",
    39:  "Curto da fase V para o terra",
    40:  "Curto da fase W para o terra",
    41:  "Curto entre as fases U e V",
    42:  "Curto entre as fases U e W",
    43:  "Curto entre as fases V e W",
    48:  "Parâmetros restaurados para o padrão",
    59:  "Circuito de segurança aberto",
    63:  "Sobrecorrente por software",
    64:  "Sobrecarga do drive",
    70:  "Falha da unidade de potência",
    71:  "Perda da rede DSI",
    72:  "Perda da rede da placa opcional",
    73:  "Perda da rede do EtherNet/IP embarcado",
    80:  "Falha no autoajuste (AutoTune)",
    81:  "Perda de comunicação DSI",
    82:  "Perda de comunicação da placa opcional",
    83:  "Perda de comunicação do EtherNet/IP embarcado",
    91:  "Perda do encoder",
    94:  "Perda de função (entrada Freeze-Fire)",
    100: "Erro de checksum dos parâmetros",
    101: "Armazenamento externo",
    105: "Erro de conexão do módulo de controle",
    106: "Módulos de controle e potência incompatíveis",
    107: "Módulo de controle/potência não reconhecido",
    109: "Módulos de controle e potência trocados",
    110: "Membrana do teclado",
    111: "Hardware de segurança",
    114: "Falha do microprocessador",
    122: "Falha da placa de I/O",
    125: "Atualização de firmware necessária",
    126: "Erro não recuperável",
    127: "Atualização de firmware DSI necessária",
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pf525")
# O pycomm3 registra CADA mensagem em INFO ("Sending generic message",
# "completed"): 14 linhas por ciclo de 1 s, mais de um milhão por dia no
# journal -- num cartão SD, que é o ponto frágil do gateway. Erros de
# verdade chegam a este sidecar como exceção e são logados aqui.
logging.getLogger("pycomm3").setLevel(logging.WARNING)


def traduzir_falha(codigo: int):
    """Código -> texto. Código desconhecido não vira 'sem falha'."""
    if not codigo:
        return None
    return FALHAS.get(codigo, f"falha F{codigo:03d} (ver manual)")


def montar_falhas(trip, ultima: int) -> tuple:
    """Decide a falha ATIVA e a ÚLTIMA falha, separadamente.

    b007 guarda a falha mais recente e continua com ela depois que a falha
    é rearmada. A versão anterior publicava b007 como falha atual: uma
    falha da semana passada deixava o painel em alarme para sempre.

    'trip' é o Fault Trip Instance do DPI Fault Object: diferente de zero
    enquanto o drive está desarmado por falha. Nesse caso a falha que
    desarmou é justamente a mais recente, b007. Se o drive não respondeu
    ao objeto de falha (trip is None), não se AFIRMA falha nenhuma: um
    alarme falso permanente é pior que nenhum, e a última falha continua
    visível em 'ultima_falha'.
    """
    ultima_d = {"codigo": ultima, "texto": traduzir_falha(ultima)}
    if trip:
        ativa = dict(ultima_d)
    else:
        ativa = {"codigo": 0, "texto": None}
    return ativa, ultima_d


# ---------------------------------------------------------------------------
#  Multi-Drive (520COM-UM001, Capítulo 7 e Apêndice C)
#
#  Até QUATRO drives se penduram pela RS-485 (DSI) atrás do PowerFlex 525
#  que está na rede EtherNet/IP. O nó inteiro tem um IP só; o drive k é
#  alcançado somando uma base à instância do objeto:
#
#      drive 0  parâmetro n  -> instância n
#      drive 1  parâmetro n  -> instância 17408 + n   (0x4400)
#      drive 2  parâmetro n  -> instância 18432 + n   (0x4800)
#      drive 3  parâmetro n  -> instância 19456 + n   (0x4C00)
#      drive 4  parâmetro n  -> instância 20480 + n   (0x5000)
#
#  A instância "0" de cada faixa (a própria base) é a "Class (Drive k)", e
#  é por ela que se chega aos atributos de classe do drive k -- entre eles o
#  Fault Trip Instance do DPI Fault Object.
#
#  Antes disto o sidecar lia só o drive 0: num painel montado em Multi-Drive,
#  o InsightX mostrava o primeiro inversor de cada grupo e os outros ficavam
#  invisíveis.
# ---------------------------------------------------------------------------
BASE_MULTIDRIVE = {0: 0, 1: 17408, 2: 18432, 3: 19456, 4: 20480}

# A RS-485 do Multi-Drive é FIXA em 19,2 kbps e é o mesmo fio que o CLP usa
# para comandar os drives; o manual dá +24 ms de atraso de controle por
# drive encadeado. Mensagem explícita disputa esse fio. Por isso os drives
# encadeados são lidos mais devagar que o drive 0, que está na Ethernet.
INTERVALO_ENCADEADO_S = float(os.getenv("PF525_INTERVALO_ENCADEADO_S", "5.0"))


class Inversor:
    """Um drive a ler: onde está (IP, posição no nó) e quem ele é no painel."""

    def __init__(self, device_id, ip, drive=0, porta=44818, intervalo_s=None,
                 nome=None, tag=None):
        if drive not in BASE_MULTIDRIVE:
            raise ValueError(f"{device_id}: 'drive' tem de ser 0 a 4, veio {drive!r}")
        self.device_id = str(device_id)
        self.ip = str(ip)
        self.drive = int(drive)
        self.porta = int(porta)
        # Só para identificar no cadastro do painel: com vários drives atrás
        # do mesmo IP, sem isto não se sabe qual é qual na hora de atribuir.
        self.nome = (nome or "").strip()
        self.tag = (tag or "").strip()
        self.intervalo_s = float(intervalo_s if intervalo_s is not None else
                                 (INTERVALO_S if self.drive == 0
                                  else INTERVALO_ENCADEADO_S))
        self.topic_inversor = f"monitoramento/{self.device_id}/inversor"
        self.topic_status = f"monitoramento/{self.device_id}/status"
        self.sem_objeto_falha = False   # não respondeu ao 0x97: para de insistir
        self.online = None              # último status publicado
        self.falha_anterior = None
        self.proxima = 0.0

    def inst_param(self, pnu):
        return BASE_MULTIDRIVE[self.drive] + pnu

    def inst_trip(self):
        return BASE_MULTIDRIVE[self.drive]

    @property
    def rotulo(self):
        pos = "" if self.drive == 0 else f" · drive {self.drive} (DSI)"
        return f"{self.device_id} [{self.ip}{pos}]"


# O drive das variáveis de ambiente: é o que roda quando não há lista.
PADRAO = Inversor(DEVICE_ID, PLC_IP, int(os.getenv("PF525_DRIVE", "0")), PORTA_CIP,
                  nome=os.getenv("PF525_NOME"), tag=os.getenv("PF525_TAG"))


def carregar_inversores():
    """A lista de drives: o arquivo em PF525_INVERSORES, ou só o PADRAO.

    Formato (veja inversores.example.json):
        {"inversores": [
            {"device_id": "pf-linha1-m1", "ip": "192.168.1.20", "drive": 0},
            {"device_id": "pf-linha1-m2", "ip": "192.168.1.20", "drive": 1}
        ]}
    """
    arq = os.getenv("PF525_INVERSORES", "").strip()
    if not arq:
        return [PADRAO]
    try:
        with open(arq, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:
        sys.exit(f"PF525_INVERSORES={arq}: não consegui ler ({e})")

    itens = cfg.get("inversores") if isinstance(cfg, dict) else cfg
    if not itens:
        sys.exit(f"{arq}: lista de inversores vazia")
    invs, vistos, posicoes = [], set(), set()
    for n, it in enumerate(itens, 1):
        try:
            inv = Inversor(it["device_id"], it["ip"], it.get("drive", 0),
                           it.get("porta", PORTA_CIP), it.get("intervalo_s"),
                           it.get("nome"), it.get("tag"))
        except KeyError as e:
            sys.exit(f"{arq}: o item {n} não tem o campo {e}")
        except (TypeError, ValueError) as e:
            sys.exit(f"{arq}: item {n}: {e}")
        # Dois erros de digitação que o painel não denunciaria: o mesmo id
        # para dois drives (um sobrescreve o outro na tela) e o mesmo drive
        # declarado duas vezes (lido em dobro, pesando na RS-485).
        if inv.device_id in vistos:
            sys.exit(f"{arq}: device_id repetido: {inv.device_id}")
        pos = (inv.ip, inv.porta, inv.drive)
        if pos in posicoes:
            sys.exit(f"{arq}: {inv.ip} drive {inv.drive} aparece duas vezes")
        vistos.add(inv.device_id)
        posicoes.add(pos)
        invs.append(inv)
    return invs


def agrupar_por_no(invs):
    """{(ip, porta): [inversores]} -- um nó EtherNet/IP, uma sessão."""
    nos = {}
    for inv in invs:
        nos.setdefault((inv.ip, inv.porta), []).append(inv)
    for lista in nos.values():
        lista.sort(key=lambda i: i.drive)
    return nos


# ------------------------------------------------------------------ CIP
_modo_ucmm = {}              # ip -> True/False: o modo de envio que funcionou


def modo_envio(ip=None):
    """O modo de envio descoberto para o nó (None = ainda não sondado)."""
    return _modo_ucmm.get(ip or PADRAO.ip)


def _pedir(conn, ip, classe, instancia, atributo, tipo, nome):
    """Get_Attribute_Single por mensageria desconectada (UCMM).

    O padrão do pycomm3 é connected=True, que dispara um Forward Open --
    esperado num rack Logix, mas o adaptador embarcado do PowerFlex 525 não
    é tag-based. Leitura pontual de parâmetro é o caso de uso de UCMM.

    O modo de envio (com ou sem Unconnected Send) é descoberto por NÓ: é o
    adaptador do drive 0 que aceita ou recusa o envelope, inclusive para os
    drives encadeados atrás dele.
    """
    from pycomm3 import Services

    if ip in _modo_ucmm:
        modos = [_modo_ucmm[ip]]
    elif MODO_UCMM in ("sim", "true", "1"):
        modos = [True]
    elif MODO_UCMM in ("nao", "não", "false", "0"):
        modos = [False]
    else:
        modos = [True, False]

    erro = None
    sondando = len(modos) > 1
    for us in modos:
        # Na sondagem, a recusa do primeiro modo é ESPERADA -- o pycomm3 a
        # loga como ERROR, e na bancada isso parece defeito. Silencia só
        # durante a sondagem; o resultado final é logado abaixo.
        lg = logging.getLogger("pycomm3")
        nivel = lg.level
        if sondando:
            lg.setLevel(logging.CRITICAL)
        try:
            resp = conn.generic_message(
                service=Services.get_attribute_single,
                class_code=classe, instance=instancia, attribute=atributo,
                data_type=tipo, name=nome,
                connected=False, unconnected_send=us,
            )
        finally:
            lg.setLevel(nivel)
        if resp:
            if ip not in _modo_ucmm:
                _modo_ucmm[ip] = us
                log.info("%s respondeu %s Unconnected Send", ip,
                         "COM" if us else "SEM")
            return resp.value
        erro = resp.error
    raise RuntimeError(f"falha CIP em {nome} (classe {classe:#04x}): {erro}")


def ler_parametro(conn, pnu: int, inv=None) -> int:
    """Lê o parâmetro 'pnu' do grupo b do drive 'inv' (bruto)."""
    from pycomm3 import INT
    inv = inv or PADRAO
    nome = f"b{pnu:03d}" + (f"@drive{inv.drive}" if inv.drive else "")
    return _pedir(conn, inv.ip, CLASSE, inv.inst_param(pnu), ATRIBUTO_VALOR,
                  INT, nome)


def ler_trip(conn, inv=None):
    """Fault Trip Instance do drive; None se ele não oferece o objeto."""
    from pycomm3 import UINT
    inv = inv or PADRAO
    if inv.sem_objeto_falha:
        return None
    try:
        return _pedir(conn, inv.ip, CLASSE_FALHA, inv.inst_trip(),
                      ATRIB_FALHA_ATIVA, UINT, f"fault_trip@drive{inv.drive}")
    except Exception as e:
        inv.sem_objeto_falha = True
        log.warning("%s não respondeu ao DPI Fault Object (%s): sem como "
                    "saber se há falha ATIVA. A última falha segue em "
                    "'ultima_falha'.", inv.rotulo, e)
        return None


def ler_inversor(conn, inv=None) -> dict:
    """Lê todos os parâmetros de um drive e monta o pacote de telemetria."""
    inv = inv or PADRAO
    bruto = {}
    dados = {}
    for campo, (pnu, escala, casas) in PARAMETROS.items():
        v = ler_parametro(conn, pnu, inv)
        bruto[campo] = v
        dados[campo] = round(v * escala, casas) if casas else int(v)
    trip = ler_trip(conn, inv)
    bruto["fault_trip"] = trip

    if LOG_BRUTO:
        log.info("%s bruto: %s", inv.rotulo, bruto)

    ultima = dados.pop("ultima_falha", 0)
    status = dados.pop("status_bruto", 0)

    # "Está rodando?" vem da FREQUÊNCIA DE SAÍDA, não do bit de status: o
    # bit Running continua ativo com o motor parado em 0 Hz, e o mapa de
    # bits do b006 varia com o firmware. Frequência acima de zero é física.
    freq = dados.get("frequencia_hz", 0.0)
    dados["rodando"] = freq > FREQ_PARADO_HZ

    dados["falha"], dados["ultima_falha"] = montar_falhas(trip, ultima)
    # O status cru vai junto de propósito: se precisar dos bits, decodifique
    # contra o SEU manual em vez de confiar num mapa que pode não ser o seu.
    dados["status_bruto"] = status
    # De onde o dado veio. O painel mostra isto na lista "Aguardando
    # cadastro" (IP · drive 2 (DSI) · nome) e já preenche a tag.
    dados["origem"] = {"no": inv.ip, "drive": inv.drive,
                       "nome": inv.nome, "tag": inv.tag}
    dados["ts"] = int(time.time() * 1000)
    return dados


def abrir_drive(ip=None, porta=None):
    from pycomm3 import CIPDriver
    ip = ip or PADRAO.ip
    porta = porta or PADRAO.porta
    # O pycomm3 aceita "ip:porta" no caminho; a porta só muda em teste.
    return CIPDriver(ip if porta == 44818 else f"{ip}:{porta}")


# ------------------------------------------------------------------ MQTT
def conectar_mqtt(invs):
    import paho.mqtt.client as mqtt
    nome = invs[0].device_id if len(invs) == 1 else "sidecar"
    try:                      # paho 2.x exige a versão da API de callback
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pf525-{nome}")
    except AttributeError:    # paho 1.x
        cli = mqtt.Client(client_id=f"pf525-{nome}")

    if MQTT_USER:
        cli.username_pw_set(MQTT_USER, MQTT_PASS)
    # LWT só com UM drive: o broker só guarda um testamento por conexão.
    # Com vários, um tópico de status "do sidecar" viraria um dispositivo
    # fantasma no painel (ele registra qualquer monitoramento/<id>/status).
    # Se o processo inteiro cair, o painel detecta pelo silêncio, como faz
    # com qualquer dispositivo mudo.
    if len(invs) == 1:
        cli.will_set(invs[0].topic_status, "offline", qos=1, retain=True)
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    cli.loop_start()
    log.info("MQTT conectado em %s:%s; %d inversor(es)", MQTT_HOST, MQTT_PORT,
             len(invs))
    return cli


def marcar(cli, inv, online, erro=None):
    """Publica online/offline do drive -- só quando o estado MUDA."""
    if inv.online == online:
        return
    inv.online = online
    cli.publish(inv.topic_status, "online" if online else "offline",
                qos=1, retain=True)
    if online:
        log.info("%s respondendo", inv.rotulo)
    else:
        log.warning("%s sem resposta%s", inv.rotulo, f" ({erro})" if erro else "")


def publicar(cli, inv, dados):
    cli.publish(inv.topic_inversor, json.dumps(dados), qos=0)
    marcar(cli, inv, True)
    # Falha nova vai para o log uma vez, e não a cada ciclo.
    cod = dados["falha"]["codigo"]
    if cod != inv.falha_anterior:
        if cod:
            log.warning("%s FALHA F%03d: %s", inv.rotulo, cod, dados["falha"]["texto"])
        elif inv.falha_anterior:
            log.info("%s falha anterior sanada", inv.rotulo)
        inv.falha_anterior = cod


def atender_no(ip, porta, invs, cli, parar):
    """Lê todos os drives de um nó EtherNet/IP numa sessão só.

    Drives do mesmo nó são lidos em sequência, nunca em paralelo: é o
    adaptador do drive 0 que repassa tudo pela RS-485, um de cada vez.
    """
    while not parar.is_set():
        try:
            with abrir_drive(ip, porta) as conn:
                log.info("conectado ao nó %s (drives %s)", ip,
                         ", ".join(str(i.drive) for i in invs))
                falhas_seguidas = 0
                while not parar.is_set():
                    agora = time.monotonic()
                    for inv in invs:
                        if agora < inv.proxima:
                            continue
                        inv.proxima = agora + inv.intervalo_s
                        try:
                            dados = ler_inversor(conn, inv)
                        except Exception as e:
                            # O drive 0 é o adaptador do nó: se ELE não
                            # responde, a sessão é que está ruim -- reconecta.
                            if inv.drive == 0:
                                raise
                            # Um encadeado desligado não derruba os outros.
                            marcar(cli, inv, False, e)
                            falhas_seguidas += 1
                            if falhas_seguidas >= len(invs):
                                raise RuntimeError("nenhum drive do nó responde")
                            continue
                        falhas_seguidas = 0
                        publicar(cli, inv, dados)
                    espera = min(i.proxima for i in invs) - time.monotonic()
                    parar.wait(max(0.05, espera))
        except Exception as e:
            log.warning("nó %s: %s. Reconectando em 5 s...", ip, e)
            for inv in invs:
                marcar(cli, inv, False, e)
                # Reconexão refaz a sondagem: se o drive foi trocado ou
                # reconfigurado, o que valia antes pode não valer mais.
                inv.sem_objeto_falha = False
                inv.proxima = 0.0
            _modo_ucmm.pop(ip, None)
            parar.wait(5)


def bancada(invs) -> None:
    """Lê tudo uma vez, drive por drive, e mostra. Sem broker.

    Primeiro comando a rodar num painel novo. O que se confere aqui não é se
    o programa roda: é se cada ESCALA bate com o display de cada drive, e se
    os drives encadeados respondem pelo nó.
    """
    print(f"\nclasse {CLASSE:#04x}, atributo {ATRIBUTO_VALOR}")
    for (ip, porta), lista in agrupar_por_no(invs).items():
        print(f"\n=== nó {ip}" + (f":{porta}" if porta != 44818 else "") + " ===")
        try:
            conn = abrir_drive(ip, porta)
            conn.open()
        except Exception as e:
            print(f"  não conectou: {e}")
            continue
        try:
            for inv in lista:
                print(f"\n  {inv.rotulo}")
                print(f"  {'campo':<16} {'par.':>5} {'instância':>9} {'bruto':>8} {'com escala':>11}")
                print("  " + "-" * 54)
                for campo, (pnu, escala, casas) in PARAMETROS.items():
                    try:
                        v = ler_parametro(conn, pnu, inv)
                        esc = round(v * escala, casas) if casas else int(v)
                        print(f"  {campo:<16} b{pnu:03d} {inv.inst_param(pnu):>9} "
                              f"{v:>8} {esc:>11}")
                    except Exception as e:
                        print(f"  {campo:<16} b{pnu:03d} {inv.inst_param(pnu):>9} "
                              f"{'ERRO':>8}   {e}")
                trip = ler_trip(conn, inv)
                print(f"  falha ativa (Fault Trip Instance): "
                      f"{'NÃO RESPONDEU' if trip is None else trip}")
        finally:
            conn.close()
        modo = modo_envio(ip)
        print(f"\n  modo de envio que funcionou: "
              f"{'—' if modo is None else ('com' if modo else 'sem')} Unconnected Send")
    print("\nCompare cada linha com o teclado de CADA drive. O b005 (barramento)")
    print("é o mais fácil: com o motor parado ele não flutua.")


def main() -> None:
    invs = carregar_inversores()
    if "--bancada" in sys.argv:
        bancada(invs)
        return

    # systemd para o serviço com SIGTERM; sem isto o Python sai sem rodar o
    # finally, e os drives ficariam "online" retidos no broker.
    import signal
    import threading
    parar = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())

    cli = conectar_mqtt(invs)
    nos = agrupar_por_no(invs)
    for (ip, porta), lista in nos.items():
        extra = [f"drive {i.drive}: {i.device_id} a cada {i.intervalo_s:g} s" for i in lista]
        log.info("nó %s -> %s", ip, "; ".join(extra))
    fios = [threading.Thread(target=atender_no, args=(ip, porta, lista, cli, parar),
                             daemon=True, name=f"no-{ip}")
            for (ip, porta), lista in nos.items()]
    for f in fios:
        f.start()
    try:
        while not parar.is_set():
            parar.wait(1)
    except KeyboardInterrupt:
        log.info("Encerrando por solicitação do usuário.")
    finally:
        parar.set()
        for f in fios:
            f.join(timeout=10)
        for inv in invs:
            cli.publish(inv.topic_status, "offline", qos=1, retain=True)
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
