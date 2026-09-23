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


# ------------------------------------------------------------------ CIP
_ucmm_escolhido = None       # descoberto no primeiro pedido que der certo
_sem_objeto_falha = False    # drive não respondeu ao 0x97: para de insistir


def _pedir(drive, classe, instancia, atributo, tipo, nome):
    """Get_Attribute_Single por mensageria desconectada (UCMM).

    O padrão do pycomm3 é connected=True, que dispara um Forward Open --
    esperado num rack Logix, mas o adaptador embarcado do PowerFlex 525 não
    é tag-based. Leitura pontual de parâmetro é o caso de uso de UCMM.
    """
    global _ucmm_escolhido
    from pycomm3 import Services

    if _ucmm_escolhido is not None:
        modos = [_ucmm_escolhido]
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
            resp = drive.generic_message(
                service=Services.get_attribute_single,
                class_code=classe, instance=instancia, attribute=atributo,
                data_type=tipo, name=nome,
                connected=False, unconnected_send=us,
            )
        finally:
            lg.setLevel(nivel)
        if resp:
            if _ucmm_escolhido is None:
                _ucmm_escolhido = us
                log.info("drive respondeu %s Unconnected Send",
                         "COM" if us else "SEM")
            return resp.value
        erro = resp.error
    raise RuntimeError(f"falha CIP em {nome} (classe {classe:#04x}): {erro}")


def ler_parametro(drive, instancia: int) -> int:
    """Lê um parâmetro do grupo b e devolve o valor bruto."""
    from pycomm3 import INT
    return _pedir(drive, CLASSE, instancia, ATRIBUTO_VALOR, INT,
                  f"b{instancia:03d}")


def ler_trip(drive):
    """Fault Trip Instance (0x97, instância 0, atributo 4); None se o
    drive não oferece o objeto."""
    global _sem_objeto_falha
    if _sem_objeto_falha:
        return None
    from pycomm3 import UINT
    try:
        return _pedir(drive, CLASSE_FALHA, 0, ATRIB_FALHA_ATIVA, UINT,
                      "fault_trip")
    except Exception as e:
        _sem_objeto_falha = True
        log.warning("drive não respondeu ao DPI Fault Object (%s): sem como "
                    "saber se há falha ATIVA. A última falha segue em "
                    "'ultima_falha'.", e)
        return None


def ler_inversor(drive) -> dict:
    """Lê todos os parâmetros e monta o pacote de telemetria."""
    bruto = {}
    dados = {}
    for campo, (instancia, escala, casas) in PARAMETROS.items():
        v = ler_parametro(drive, instancia)
        bruto[campo] = v
        dados[campo] = round(v * escala, casas) if casas else int(v)
    trip = ler_trip(drive)
    bruto["fault_trip"] = trip

    if LOG_BRUTO:
        log.info("bruto: %s", bruto)

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
    dados["ts"] = int(time.time() * 1000)
    return dados


def abrir_drive():
    from pycomm3 import CIPDriver
    # O pycomm3 aceita "ip:porta" no caminho; a porta só muda em teste.
    alvo = PLC_IP if PORTA_CIP == 44818 else f"{PLC_IP}:{PORTA_CIP}"
    return CIPDriver(alvo)


def conectar_mqtt():
    import paho.mqtt.client as mqtt
    try:                      # paho 2.x exige a versão da API de callback
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                          client_id=f"pf525-{DEVICE_ID}")
    except AttributeError:    # paho 1.x
        cli = mqtt.Client(client_id=f"pf525-{DEVICE_ID}")

    if MQTT_USER:
        cli.username_pw_set(MQTT_USER, MQTT_PASS)
    # LWT: se o gateway cair, o broker marca offline sozinho.
    cli.will_set(TOPIC_STATUS, "offline", qos=1, retain=True)
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    cli.loop_start()
    cli.publish(TOPIC_STATUS, "online", qos=1, retain=True)
    log.info("MQTT conectado em %s:%s; publicando em %s",
             MQTT_HOST, MQTT_PORT, TOPIC_INVERSOR)
    return cli


def bancada() -> None:
    """Lê tudo uma vez e mostra lado a lado com o parâmetro do teclado.

    Primeiro comando a rodar num drive novo. Não precisa de broker. O que
    se confere aqui não é se o programa roda: é se cada ESCALA bate com o
    display do drive, e se o drive responde ao objeto de falha.
    """
    print(f"\nPowerFlex 525 em {PLC_IP} — classe {CLASSE:#04x}, "
          f"atributo {ATRIBUTO_VALOR}\n")
    print(f"{'campo':<16} {'par.':>5} {'bruto':>8} {'com escala':>11}")
    print("-" * 44)
    with abrir_drive() as drive:
        for campo, (inst, escala, casas) in PARAMETROS.items():
            try:
                v = ler_parametro(drive, inst)
                esc = round(v * escala, casas) if casas else int(v)
                print(f"{campo:<16} b{inst:03d} {v:>8} {esc:>11}")
            except Exception as e:
                print(f"{campo:<16} b{inst:03d} {'ERRO':>8}   {e}")
        trip = ler_trip(drive)
    print(f"\nfalha ativa (Fault Trip Instance): "
          f"{'NÃO RESPONDEU' if trip is None else trip}")
    print(f"modo de envio que funcionou: "
          f"{'com' if _ucmm_escolhido else 'sem'} Unconnected Send")
    print("\nCompare cada linha com o teclado do drive. O b005 (barramento)")
    print("é o mais fácil: com o motor parado ele não flutua.")


def main() -> None:
    global _ucmm_escolhido, _sem_objeto_falha
    if "--bancada" in sys.argv:
        bancada()
        return

    cli = conectar_mqtt()
    falha_anterior = None
    try:
        while True:
            try:
                with abrir_drive() as drive:
                    log.info("Conectado ao PowerFlex 525 em %s", PLC_IP)
                    while True:
                        dados = ler_inversor(drive)
                        cli.publish(TOPIC_INVERSOR, json.dumps(dados), qos=0)

                        # Falha nova vai para o log uma vez, e não a cada
                        # ciclo -- senão o journal vira uma parede de texto.
                        cod = dados["falha"]["codigo"]
                        if cod != falha_anterior:
                            if cod:
                                log.warning("FALHA F%03d: %s", cod,
                                            dados["falha"]["texto"])
                            elif falha_anterior:
                                log.info("falha anterior sanada")
                            falha_anterior = cod

                        log.debug("%s", dados)
                        time.sleep(INTERVALO_S)
            except KeyboardInterrupt:
                raise
            except Exception as e:  # reconecta ao drive em qualquer erro EtherNet/IP
                log.warning("Erro na leitura EtherNet/IP (%s). Retentando em 5 s...", e)
                # Reconexão refaz a sondagem do modo de envio e do objeto de
                # falha: se o drive foi trocado ou reconfigurado, o que valia
                # antes pode não valer mais -- e ficar preso nele é silencioso.
                _ucmm_escolhido, _sem_objeto_falha = None, False
                time.sleep(5)
    except KeyboardInterrupt:
        log.info("Encerrando por solicitação do usuário.")
    finally:
        cli.publish(TOPIC_STATUS, "offline", qos=1, retain=True)
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
