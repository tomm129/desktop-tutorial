#!/usr/bin/env python3
"""Leitura de corrente do inversor PowerFlex 525 via EtherNet/IP -> MQTT.

Lê o parâmetro b003 (Corrente de Saída, em Amperes) do drive usando
mensageria CIP explícita (Parameter Object, classe 0x0F) e publica em

    monitoramento/<DEVICE_ID>/corrente

como JSON: {"corrente_a": <valor>, "ts": <epoch_ms>}

O Node-RED consome esse tópico e alimenta o gauge de corrente — mantendo
todo o barramento em MQTT.

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

# Parâmetro a ler. b003 = Corrente de Saída (A) no PowerFlex 525 -> instância 3.
PARAM_INSTANCE = int(os.getenv("PF525_PARAM_INSTANCE", "3"))

# Escala do valor bruto -> Amperes. AJUSTE comparando com o display b003 do
# drive: muitas faixas usam 2 casas decimais (bruto/100 => escala 0.01).
ESCALA = float(os.getenv("PF525_ESCALA", "0.01"))

# Classe CIP do objeto de parâmetros. 0x0F = Parameter Object (padrão); em
# alguns firmwares só o DPI Parameter Object (0x93) responde. Aceita "0x93"
# ou decimal — a base 0 do int() resolve as duas formas.
CLASSE = int(os.getenv("PF525_CLASSE", "0x0F"), 0)

INTERVALO_S = float(os.getenv("PF525_INTERVALO_S", "1.0"))

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")

TOPIC_CORRENTE = f"monitoramento/{DEVICE_ID}/corrente"
TOPIC_STATUS = f"monitoramento/{DEVICE_ID}/status"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("pf525")


def ler_corrente(drive: CIPDriver) -> float:
    """Lê b003 (corrente de saída) via Parameter Object.

    Usa mensageria CIP *desconectada* (UCMM). O padrão do pycomm3 é
    ``connected=True``, que dispara um Forward Open antes da requisição — isso
    é o esperado num rack Logix, mas o adaptador EtherNet/IP embarcado do
    PowerFlex 525 não é tag-based e costuma recusar a abertura de conexão.
    Leitura pontual de parâmetro é justamente o caso de uso de UCMM.
    """
    resp = drive.generic_message(
        service=Services.get_attribute_single,
        class_code=CLASSE,         # 0x0F Parameter Object (ou 0x93 DPI)
        instance=PARAM_INSTANCE,   # número do parâmetro (b003 -> 3)
        attribute=1,               # atributo 1 = valor do parâmetro
        data_type=INT,             # inteiro 16 bits com sinal
        name="b003_output_current",
        connected=False,           # UCMM: sem Forward Open
        unconnected_send=True,     # encapsula em Unconnected Send
    )
    if not resp:
        raise RuntimeError(
            f"Falha CIP ao ler parâmetro {PARAM_INSTANCE} "
            f"(classe {CLASSE:#04x}): {resp.error}"
        )
    return resp.value * ESCALA


def conectar_mqtt() -> mqtt.Client:
    cli = mqtt.Client(client_id=f"pf525-{DEVICE_ID}")
    if MQTT_USER:
        cli.username_pw_set(MQTT_USER, MQTT_PASS)
    # LWT: se o gateway cair, o broker marca offline sozinho.
    cli.will_set(TOPIC_STATUS, "offline", qos=1, retain=True)
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    cli.loop_start()
    cli.publish(TOPIC_STATUS, "online", qos=1, retain=True)
    log.info("MQTT conectado em %s:%s; publicando em %s",
             MQTT_HOST, MQTT_PORT, TOPIC_CORRENTE)
    return cli


def main() -> None:
    cli = conectar_mqtt()
    try:
        while True:
            try:
                with CIPDriver(PLC_IP) as drive:
                    log.info("Conectado ao PowerFlex 525 em %s", PLC_IP)
                    while True:
                        corrente = ler_corrente(drive)
                        cli.publish(TOPIC_CORRENTE, json.dumps({
                            "corrente_a": round(corrente, 2),
                            "ts": int(time.time() * 1000),
                        }), qos=0)
                        log.debug("corrente = %.2f A", corrente)
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
