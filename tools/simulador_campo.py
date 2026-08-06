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

# =====================================================================
#  Planta de demonstracao (--demo)
#
#  Uma planta industrial plausivel para apresentar o sistema sem hardware:
#  caldeira, ETE, torre de resfriamento e transporte. Cada equipamento tem
#  uma condicao propria, escolhida para que UMA tela mostre os quatro
#  estados que o painel sabe representar -- normal, atencao, critico e
#  falha de inversor -- em vez de so o caso feliz.
#
#  Os valores sao SIMULADOS. Servem para demonstrar o comportamento da
#  interface, nao para representar medicoes reais de nenhuma planta.
# =====================================================================
PLANTA_DEMO = [
    # (device_id, inversor_id, temp_base, vib_base, corrente_base, condicao)
    ("caldeira-bomba",   "pf-caldeira-01", 52.0, 0.18,  9.8, "normal"),
    ("caldeira-vent",    "pf-caldeira-02", 61.5, 0.24, 12.1, "atencao_temp"),

    ("ete-soprador-1",   "pf-ete-01",      48.0, 0.21, 15.2, "normal"),
    ("ete-soprador-2",   "pf-ete-02",      55.0, 1.24, 16.8, "critico_vib"),

    ("torre-ventilador", "pf-torre-01",    44.0, 0.31, 11.4, "falha_drive"),
    ("torre-bomba",      "pf-torre-02",    46.5, 0.16,  7.9, "normal"),

    ("transp-motor-1",   "pf-transp-01",   43.0, 0.14,  6.8, "normal"),
    ("transp-motor-2",   None,             45.0, 0.19, None, "normal"),
]


def demo_valores(cfg, t, i):
    """Gera as leituras de um equipamento da planta de demonstracao."""
    dev, inv, tb, vb, cb, cond = cfg
    fase = i * 1.3

    temp = tb + 2.0 * math.sin(t / 45.0 + fase) + random.gauss(0, 0.3)
    vib = vb + 0.02 * math.sin(t / 13.0 + fase) + abs(random.gauss(0, 0.008))
    corr = None if cb is None else (
        cb + cb * 0.05 * math.sin(t / 30.0 + fase) + random.gauss(0, 0.08))

    # Falha de inversor entra aos 15s, para dar tempo de a tela montar.
    falha = 8 if (cond == "falha_drive" and t > 15) else 0

    # Motor parado tem corrente e frequencia zero -- e nao e alarme.
    parado = (cond == "parado")
    freq = 0.0 if parado else 60.0 + random.gauss(0, 0.04)
    if parado and corr is not None:
        corr = 0.0

    return temp, vib, corr, freq, falha


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


FALHAS_DEMO = {8: "Temperatura do dissipador acima do limite"}


def publicar_demo(cli, t):
    """Publica um ciclo inteiro da planta de demonstracao."""
    for i, cfg in enumerate(PLANTA_DEMO):
        dev, inv, _, _, _, cond = cfg
        temp, vib, corr, freq, falha = demo_valores(cfg, t, i)

        cli.publish(f"{BASE}/{dev}/telemetria", json.dumps({
            "device_id": dev,
            "ts": int(t * 1000),
            "temperatura_c": round(temp, 1),
            "vibracao": {
                "rms_g": round(vib, 3),
                "pico_g": round(vib * random.uniform(2.6, 3.8), 3),
                "eixo_x_g": round(random.gauss(0.02, 0.01), 2),
                "eixo_y_g": round(random.gauss(0.01, 0.01), 2),
                "eixo_z_g": round(random.gauss(1.00, 0.01), 2),
                "fs_hz": round(random.gauss(371.4, 0.5), 1),
            },
            "rede": {"rssi_dbm": int(random.gauss(-58, 3)),
                     "uptime_s": int(t)},
        }), qos=0)

        if not inv:
            continue
        cli.publish(f"{BASE}/{inv}/inversor", json.dumps({
            "ts": int(time.time() * 1000),
            "corrente_a": None if corr is None else round(corr, 2),
            "tensao_v": round(220.0 + random.gauss(0, 1.0), 1),
            "dc_bus_v": round(311.0 + random.gauss(0, 1.8), 1),
            "frequencia_hz": round(freq, 2),
            "rodando": freq > 0.1,
            "falha": {"codigo": falha, "texto": FALHAS_DEMO.get(falha)},
            "status_bruto": 3 if freq > 0.1 else 1,
        }), qos=0)


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
                    choices=["normal", "alarme", "falha", "mudo",
                             "parado", "falha_drive"])
    ap.add_argument("--duracao", type=float, default=0,
                    help="segundos (0 = ate o Ctrl-C)")
    ap.add_argument("--demo", action="store_true",
                    help="planta de demonstracao (caldeira, ETE, torre, "
                         "transporte) com estados variados")
    a = ap.parse_args()

    if a.demo:
        devs = [c[0] for c in PLANTA_DEMO]
        inversores = [c[1] for c in PLANTA_DEMO if c[1]]
        inversor = None
    else:
        devs = [f"motor-{i + 1:02d}" for i in range(a.ativos)]
        inversor = "powerflex-01"
        inversores = [inversor]

    cli = cliente(a.host, a.porta, a.user, a.senha)
    print(f"conectado em {a.host}:{a.porta}")
    print(f"equipamentos: {len(devs)} | inversores: {len(inversores)}")
    print(f"cenario: {'demo (planta de demonstracao)' if a.demo else a.cenario}\n")

    for d in devs + inversores:
        cli.publish(f"{BASE}/{d}/status", "online", qos=1, retain=True)

    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            if a.duracao and t > a.duracao:
                break

            if a.demo:
                publicar_demo(cli, t)
                print(" t=%6.1fs  publicado" % t, end="", flush=True)
                time.sleep(a.intervalo)
                continue

            # No cenario "mudo", o primeiro ativo para de publicar aos 15s --
            # o painel deve marcar SEM DADOS sozinho, sem ninguem avisar.
            for i, d in enumerate(devs):
                if a.cenario == "mudo" and i == 0 and t > 15:
                    continue
                cli.publish(f"{BASE}/{d}/telemetria",
                            json.dumps(telemetria(d, t, a.cenario, i)), qos=0)

            # --- inversor -------------------------------------------
            # No cenario "parado" o drive fica em 0 Hz: serve para ver se a
            # tela sabe distinguir "parado" de "sensor morto".
            parado = (a.cenario == "parado" and t > 20)
            freq = 0.0 if parado else 60.0 + random.gauss(0, 0.05)
            corrente = 0.0 if parado else (
                7.4 + 1.2 * math.sin(t / 25.0) + random.gauss(0, 0.15))
            if a.cenario == "alarme":
                corrente += min(5.0, t / 22.0)

            # No cenario "falha_drive", o inversor entra em F005 aos 20s.
            codigo = 5 if (a.cenario == "falha_drive" and t > 20) else 0
            textos = {5: "Sobretensao no barramento CC"}

            cli.publish(f"{BASE}/{inversor}/inversor", json.dumps({
                "ts": int(time.time() * 1000),
                "corrente_a": round(corrente, 2),
                "tensao_v": 0.0 if parado else round(220.0 + random.gauss(0, 1.2), 1),
                "dc_bus_v": round(311.0 + random.gauss(0, 2.0), 1),
                "frequencia_hz": round(freq, 2),
                "rodando": freq > 0.1,
                "falha": {"codigo": codigo, "texto": textos.get(codigo)},
                "status_bruto": 3 if freq > 0.1 else 1,
            }), qos=0)

            print(f"\r t={t:6.1f}s  publicado", end="", flush=True)
            time.sleep(a.intervalo)
    except KeyboardInterrupt:
        print("\nencerrando...")
    finally:
        for d in devs + inversores:
            cli.publish(f"{BASE}/{d}/status", "offline", qos=1, retain=True)
        time.sleep(0.4)
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
