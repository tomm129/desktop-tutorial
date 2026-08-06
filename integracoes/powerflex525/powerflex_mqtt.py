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
      "falha": {"codigo": 0, "texto": null},
      "status_bruto": 3
    }

Config por variáveis de ambiente (veja config.example.env).
Dependências em requirements.txt (pycomm3, paho-mqtt).
"""
import json
import logging
import os
import time

from pycomm3 import CIPDriver, Services, INT
import paho.mqtt.client as mqtt

# ------------------------------------------------------------------- Config
PLC_IP    = os.getenv("PF525_IP", "192.168.1.10")
DEVICE_ID = os.getenv("PF525_DEVICE_ID", "powerflex-01")

# Classe CIP do objeto de parâmetros. 0x0F = Parameter Object (padrão); em
# alguns firmwares só o DPI Parameter Object (0x93) responde. Aceita "0x93"
# ou decimal — a base 0 do int() resolve as duas formas.
CLASSE = int(os.getenv("PF525_CLASSE", "0x0F"), 0)

INTERVALO_S = float(os.getenv("PF525_INTERVALO_S", "1.0"))

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

TOPIC_INVERSOR = f"monitoramento/{DEVICE_ID}/inversor"
TOPIC_STATUS = f"monitoramento/{DEVICE_ID}/status"

# ---------------------------------------------------------------------------
#  Parâmetros lidos
#
#  No PowerFlex 525 o grupo "b" (Basic Display) é só leitura e o número do
#  parâmetro é a própria instância CIP. As ESCALAS abaixo são o padrão da
#  família, mas variam com a faixa de potência do drive:
#
#      CONFIRME cada uma comparando com o valor no teclado do inversor.
#
#  O jeito rápido: rode com PF525_LOG_BRUTO=1, ponha o teclado no parâmetro
#  e veja se bruto × escala bate com o display.
# ---------------------------------------------------------------------------
def _escala(nome, padrao):
    return float(os.getenv(f"PF525_ESCALA_{nome}", padrao))


PARAMETROS = {
    # campo no JSON      instância  escala                casas
    "frequencia_hz": (1, _escala("FREQ", "0.01"), 2),
    "corrente_a":    (3, _escala("CORRENTE", "0.01"), 2),
    "tensao_v":      (4, _escala("TENSAO", "0.1"), 1),
    "dc_bus_v":      (5, _escala("DCBUS", "0.1"), 1),
    "status_bruto":  (6, 1.0, 0),
    "falha_codigo":  (7, 1.0, 0),
}

# Abaixo desta frequência de saída consideramos o motor parado.
FREQ_PARADO_HZ = float(os.getenv("PF525_FREQ_PARADO_HZ", "0.1"))

LOG_BRUTO = os.getenv("PF525_LOG_BRUTO", "") not in ("", "0", "false", "False")

# ---------------------------------------------------------------------------
#  Códigos de falha do PowerFlex 525 (manual 520-UM001).
#  Traduzir aqui, e não no Node-RED, mantém o significado junto de quem
#  conhece o equipamento — e o painel só exibe o que recebe.
# ---------------------------------------------------------------------------
FALHAS = {
    2:   "Entrada de parada externa (auxiliar)",
    3:   "Operação monofásica com carga excessiva",
    4:   "Subtensão no barramento CC",
    5:   "Sobretensão no barramento CC",
    6:   "Não conseguiu acelerar/desacelerar o motor",
    7:   "Sobrecarga eletrônica do motor",
    8:   "Temperatura do dissipador acima do limite",
    12:  "Sobrecorrente de hardware",
    13:  "Falha de aterramento",
    21:  "Perda de fase na saída",
    29:  "Perda de sinal na entrada analógica",
    33:  "Excesso de tentativas de rearme automático",
    38:  "Curto fase U para o terra",
    39:  "Curto fase V para o terra",
    40:  "Curto fase W para o terra",
    41:  "Curto entre fases U e V",
    42:  "Curto entre fases V e W",
    43:  "Curto entre fases U e W",
    48:  "Parâmetros restaurados para o padrão de fábrica",
    59:  "Entradas de segurança não habilitadas/configuradas",
    63:  "Limite de pino de cisalhamento excedido",
    64:  "Sobrecarga do drive",
    70:  "Falha na seção de potência",
    71:  "Comunicação Modbus/DSI interrompida",
    72:  "Comunicação da placa de rede interrompida",
    73:  "Comunicação do EtherNet/IP embarcado interrompida",
    81:  "Perda de comunicação com o mestre Modbus/DSI",
    94:  "Entrada Freeze-Fire inativa/aberta",
    100: "Memória de parâmetros corrompida",
    105: "Módulo de controle desconectado com o drive energizado",
    106: "Módulo de controle incompatível com o módulo de potência",
    109: "Módulo de controle montado em outro tipo de drive",
    110: "Falha da membrana do teclado",
    111: "Falha no hardware das entradas de segurança",
    114: "Falha do microprocessador",
    122: "Falha na seção de controle/IO",
    125: "Firmware corrompido ou incompatível",
    126: "Erro não recuperável de firmware/hardware",
    127: "Problema crítico de firmware (modo DSI de emergência)",
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pf525")


def ler_parametro(drive: CIPDriver, instancia: int) -> int:
    """Lê um parâmetro do grupo b via Parameter Object, retornando o bruto.

    Usa mensageria CIP *desconectada* (UCMM). O padrão do pycomm3 é
    ``connected=True``, que dispara um Forward Open antes da requisição —
    isso é o esperado num rack Logix, mas o adaptador EtherNet/IP embarcado
    do PowerFlex 525 não é tag-based e costuma recusar a abertura de
    conexão. Leitura pontual de parâmetro é justamente o caso de uso de
    UCMM.
    """
    resp = drive.generic_message(
        service=Services.get_attribute_single,
        class_code=CLASSE,         # 0x0F Parameter Object (ou 0x93 DPI)
        instance=instancia,        # número do parâmetro (b003 -> 3)
        attribute=1,               # atributo 1 = valor do parâmetro
        data_type=INT,             # inteiro 16 bits com sinal
        name=f"b{instancia:03d}",
        connected=False,           # UCMM: sem Forward Open
        unconnected_send=True,     # encapsula em Unconnected Send
    )
    if not resp:
        raise RuntimeError(
            f"Falha CIP ao ler b{instancia:03d} "
            f"(classe {CLASSE:#04x}): {resp.error}"
        )
    return resp.value


def ler_inversor(drive: CIPDriver) -> dict:
    """Lê todos os parâmetros e monta o pacote de telemetria."""
    bruto = {}
    dados = {}
    for campo, (instancia, escala, casas) in PARAMETROS.items():
        v = ler_parametro(drive, instancia)
        bruto[campo] = v
        dados[campo] = round(v * escala, casas) if casas else int(v)

    if LOG_BRUTO:
        log.info("bruto: %s", bruto)

    codigo = dados.pop("falha_codigo", 0)
    status = dados.pop("status_bruto", 0)

    # "Está rodando?" vem da FREQUÊNCIA DE SAÍDA, não do bit de status.
    #
    # O bit "Active"/"Running" do drive indica que ele recebeu comando de
    # marcha e não está em falha — e continua verdadeiro com a velocidade
    # em zero, ou seja, com o motor parado. Além disso o mapa de bits do
    # b006 varia entre versões de firmware. Frequência de saída acima de
    # zero é física, direta e não depende de interpretar protocolo.
    freq = dados.get("frequencia_hz", 0.0)
    dados["rodando"] = freq > FREQ_PARADO_HZ

    dados["falha"] = {
        "codigo": codigo,
        # Código desconhecido não vira "sem falha": vira falha sem tradução.
        "texto": (None if codigo == 0
                  else FALHAS.get(codigo, f"falha F{codigo:03d} (ver manual)")),
    }
    # O status cru vai junto de propósito: se você precisar dos bits, decodifique
    # contra o SEU manual em vez de confiar num mapa que pode não ser o seu.
    dados["status_bruto"] = status
    dados["ts"] = int(time.time() * 1000)
    return dados


def conectar_mqtt() -> mqtt.Client:
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


def main() -> None:
    cli = conectar_mqtt()
    falha_anterior = None
    try:
        while True:
            try:
                with CIPDriver(PLC_IP) as drive:
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
                time.sleep(5)
    except KeyboardInterrupt:
        log.info("Encerrando por solicitação do usuário.")
    finally:
        cli.publish(TOPIC_STATUS, "offline", qos=1, retain=True)
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
