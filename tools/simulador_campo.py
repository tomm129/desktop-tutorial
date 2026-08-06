#!/usr/bin/env python3
"""Simula os dispositivos de campo publicando no MQTT.

Serve para mexer no dashboard sem precisar do ESP32, do inversor nem da
maquina rodando -- inclusive para ver como a tela reage a alarme, a falha
de sensor e a dispositivo mudo, que sao justamente os casos dificeis de
reproduzir de proposito no hardware real.

Uso:
    python tools/simulador_campo.py                    # 2 ativos, tudo normal
    python tools/simulador_campo.py --ativos 3
    python tools/simulador_campo.py --cenario alarme   # vibracao subindo
    python tools/simulador_campo.py --cenario falha    # sensor de temp morto
    python tools/simulador_campo.py --cenario mudo     # para de publicar

    python tools/simulador_campo.py --host 192.168.3.20 --user monitoramento --pass segredo

Ctrl-C encerra publicando 'offline' no status, como faria o LWT.
"""
import argparse
import json
import math
import random
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Falta o paho-mqtt. Instale com: pip install paho-mqtt")

BASE = "monitoramento"


def cliente(host, porta, usuario, senha):
    """Conecta ao broker, aceitando paho 1.x e 2.x."""
    try:                      # paho 2.x exige a versao da API de callback
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                          client_id="simulador-campo")
    except AttributeError:    # paho 1.x
        cli = mqtt.Client(client_id="simulador-campo")

    if usuario:
        cli.username_pw_set(usuario, senha)
    cli.connect(host, porta, keepalive=60)
    cli.loop_start()
    return cli


def telemetria(dev, t, cenario, indice):
    """Monta um pacote de telemetria com cara de leitura real."""
    # Cada ativo tem sua propria "personalidade" para as linhas nao ficarem
    # sobrepostas no grafico.
    fase = indice * 1.7
    base_temp = 42.0 + indice * 6.0
    base_vib = 0.12 + indice * 0.04

    temp = base_temp + 3.0 * math.sin(t / 40.0 + fase) + random.gauss(0, 0.4)
    vib = base_vib + 0.03 * math.sin(t / 11.0 + fase) + abs(random.gauss(0, 0.012))

    if cenario == "alarme" and indice == 0:
        # Sobe devagar ate cruzar atencao (0,5 g) e depois critico (1,0 g),
        # para dar para ver a tela mudando de faixa.
        vib += min(1.4, t / 60.0)
        temp += min(40.0, t / 6.0)

    if cenario == "falha" and indice == 0:
        temp = None           # sensor de temperatura sem resposta

    pacote = {
        "device_id": dev,
        "ts": int(t * 1000),
        "temperatura_c": None if temp is None else round(temp, 1),
        "vibracao": {
            "rms_g": round(vib, 3),
            "pico_g": round(vib * random.uniform(2.5, 4.0), 3),
            "eixo_x_g": round(random.gauss(0.02, 0.01), 2),
            "eixo_y_g": round(random.gauss(0.01, 0.01), 2),
            "eixo_z_g": round(random.gauss(1.00, 0.01), 2),
            "fs_hz": round(random.gauss(371.4, 0.6), 1),
        },
        "rede": {
            "rssi_dbm": int(random.gauss(-61, 3)),
            "uptime_s": int(t),
        },
    }
    return pacote


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--porta", type=int, default=1883)
    ap.add_argument("--user", default="", help="usuario MQTT")
    ap.add_argument("--senha", default="", help="senha MQTT")
    ap.add_argument("--ativos", type=int, default=2, help="quantos ESP32 simular")
    ap.add_argument("--intervalo", type=float, default=2.0, help="segundos entre pacotes")
    ap.add_argument("--cenario", default="normal",
                    choices=["normal", "alarme", "falha", "mudo"])
    ap.add_argument("--duracao", type=float, default=0,
                    help="segundos (0 = ate o Ctrl-C)")
    a = ap.parse_args()

    devs = [f"motor-{i + 1:02d}" for i in range(a.ativos)]
    inversor = "powerflex-01"

    cli = cliente(a.host, a.porta, a.user, a.senha)
    print(f"conectado em {a.host}:{a.porta}")
    print(f"ativos: {', '.join(devs)} + {inversor}")
    print(f"cenario: {a.cenario}\n")

    for d in devs:
        cli.publish(f"{BASE}/{d}/status", "online", qos=1, retain=True)
    cli.publish(f"{BASE}/{inversor}/status", "online", qos=1, retain=True)

    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            if a.duracao and t > a.duracao:
                break

            # No cenario "mudo", o primeiro ativo para de publicar aos 15s --
            # o painel deve marcar SEM DADOS sozinho, sem ninguem avisar.
            for i, d in enumerate(devs):
                if a.cenario == "mudo" and i == 0 and t > 15:
                    continue
                cli.publish(f"{BASE}/{d}/telemetria",
                            json.dumps(telemetria(d, t, a.cenario, i)), qos=0)

            corrente = 7.4 + 1.2 * math.sin(t / 25.0) + random.gauss(0, 0.15)
            if a.cenario == "alarme":
                corrente += min(5.0, t / 22.0)
            cli.publish(f"{BASE}/{inversor}/corrente",
                        json.dumps({"corrente_a": round(corrente, 2),
                                    "ts": int(time.time() * 1000)}), qos=0)

            print(f"\r t={t:6.1f}s  publicado", end="", flush=True)
            time.sleep(a.intervalo)
    except KeyboardInterrupt:
        print("\nencerrando...")
    finally:
        for d in devs:
            cli.publish(f"{BASE}/{d}/status", "offline", qos=1, retain=True)
        cli.publish(f"{BASE}/{inversor}/status", "offline", qos=1, retain=True)
        time.sleep(0.4)
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
