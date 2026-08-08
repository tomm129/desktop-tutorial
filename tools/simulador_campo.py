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


def ler_cadastro(caminho):
    """Le dados/ativos.json e devolve a lista de dispositivos a simular.

    Serve para testar o painel sob escala sem ter de duplicar a planta aqui:
    o cadastro e a fonte de verdade do que existe, e o simulador passa a
    seguir ele em vez de ter a planta fixa no codigo.

    Devolve [(device_id, inversor_id ou None, indice)] -- o indice da a cada
    dispositivo uma "personalidade" propria, para as series nao ficarem
    empilhadas no grafico.
    """
    with open(caminho, encoding="utf-8") as f:
        cad = json.load(f)
    saida = []
    for ativo in sorted(k for k in cad if not k.startswith("_")):
        for parte in sorted((cad[ativo].get("partes") or {})):
            p = cad[ativo]["partes"][parte]
            if p.get("esp32"):
                saida.append((p["esp32"], p.get("inversor"), len(saida)))
    return saida


def bloco_vibracao(vib_g, vel_mm_s, crista, fs_media=371.4, fs_dp=0.6):
    """Monta o bloco 'vibracao' no formato que o firmware publica.

    A velocidade NAO e derivada do rms_g por um fator fixo de proposito: no
    aparelho real ela sai de uma integracao com passa-alta, e depende de EM
    QUE frequencia a energia esta -- a mesma aceleracao a 30 Hz e a 90 Hz da
    velocidades bem diferentes. Simular por regra de tres daria ao painel um
    dado com correlacao perfeita, que nao existe em campo e esconderia
    exatamente os casos que a velocidade serve para separar.
    """
    return {
        "rms_g": round(vib_g, 3),
        "pico_g": round(vib_g * crista, 3),
        "crista": round(crista, 2),
        "vel_mm_s": round(vel_mm_s, 2),
        "eixo_x_g": round(random.gauss(0.02, 0.01), 2),
        "eixo_y_g": round(random.gauss(0.01, 0.01), 2),
        "eixo_z_g": round(random.gauss(1.00, 0.01), 2),
        "fs_hz": round(random.gauss(fs_media, fs_dp), 1),
    }


def telemetria(dev, t, cenario, indice):
    """Monta um pacote de telemetria com cara de leitura real."""
    # Cada ativo tem sua propria "personalidade" para as linhas nao ficarem
    # sobrepostas no grafico.
    fase = indice * 1.7
    base_temp = 42.0 + indice * 6.0
    base_vib = 0.12 + indice * 0.04
    # Comeca na zona A/B da ISO 20816 (limite A/B = 1,4; B/C = 2,8 mm/s),
    # que e onde uma maquina saudavel deve estar.
    base_vel = 1.1 + indice * 0.45

    temp = base_temp + 3.0 * math.sin(t / 40.0 + fase) + random.gauss(0, 0.4)
    vib = base_vib + 0.03 * math.sin(t / 11.0 + fase) + abs(random.gauss(0, 0.012))
    vel = base_vel + 0.25 * math.sin(t / 13.0 + fase) + abs(random.gauss(0, 0.06))
    crista = random.uniform(3.0, 4.2)          # faixa tipica de maquina sadia

    if cenario == "alarme" and indice == 0:
        # Sobe devagar ate cruzar atencao (2,8 mm/s) e depois critico
        # (4,5 mm/s), para dar para ver a tela mudando de faixa.
        vib += min(1.4, t / 60.0)
        vel += min(4.2, t / 22.0)
        temp += min(40.0, t / 6.0)
        # A crista sobe ANTES do RMS: e a assinatura de rolamento incipiente,
        # e o motivo de a medida existir.
        crista = min(7.5, crista + t / 30.0)

    if cenario == "falha" and indice == 0:
        temp = None           # sensor de temperatura sem resposta

    pacote = {
        "device_id": dev,
        "ts": int(t * 1000),
        "temperatura_c": None if temp is None else round(temp, 1),
        "vibracao": bloco_vibracao(vib, vel, crista),
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

        # A velocidade acompanha a condicao do ativo. So o 'critico_vib'
        # entra na zona D (>=4,5 mm/s) -- o 'atencao_temp' tem problema de
        # TEMPERATURA, e sua vibracao deve continuar saudavel, senao a demo
        # perde a graca de mostrar que as grandezas alarmam de forma
        # independente.
        # A faixa "normal" tem de caber na zona A/B de TODOS os portes desta
        # planta, e o teto e o motor pequeno, nao o grande: os motores do
        # Transporte tem 7,5 kW e carcaca 132, que a ISO 20816-3 nao cobre
        # (escopo comeca acima de 15 kW). No perfil de maquina pequena a
        # atencao ja entra em 1,8 mm/s.
        #
        # A versao anterior espalhava de 1,3 a 2,8 mm/s e punha os ativos
        # "normais" da demo em ATENCAO -- e o painel estava certo, porque
        # 2,8 mm/s num motor de 7,5 kW e atencao mesmo. Quem mentia era o
        # simulador.
        if cond == "critico_vib":
            vel = 5.2                            # zona D no grupo 2 rigido
            crista = random.uniform(6.0, 7.4)    # rolamento batendo
        else:
            vel = 0.85 + i * 0.07                # 0,85 a 1,34 mm/s
            crista = random.uniform(3.0, 4.2)
        vel += abs(random.gauss(0, 0.06))

        cli.publish(f"{BASE}/{dev}/telemetria", json.dumps({
            "device_id": dev,
            "ts": int(t * 1000),
            "temperatura_c": round(temp, 1),
            "vibracao": bloco_vibracao(vib, vel, crista, 371.4, 0.5),
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


def publicar_backfill(cli, devs, minutos, passo_s=5):
    """Despeja amostras 'recuperadas do buffer' como o ESP32 faz ao reconectar.

    Serve para ver na tela o que acontece depois de uma queda de comunicacao
    sem ter de derrubar a rede de verdade. Cada pacote leva buffer=true e
    atraso_ms -- o painel reconstroi o instante real subtraindo o atraso da
    hora atual, porque o ESP32 nao tem relogio de parede.

    O esperado no painel: as amostras entram no HISTORICO com o horario
    certo, a linha do tempo pinta o trecho como 'recuperado', e o estado ao
    vivo NAO muda -- mesmo que os valores recuperados sejam criticos.
    """
    total = int(minutos * 60 / passo_s)
    print(f"backfill: {total} amostras por dispositivo, "
          f"cobrindo {minutos:.0f} min para tras")

    for dev in devs:
        for k in range(total):
            # A mais antiga primeiro, como o firmware drena (ordem
            # cronologica -- senao a linha do tempo desenha ao contrario).
            atraso_ms = int((minutos * 60 - k * passo_s) * 1000)
            # Valores em degradacao durante a queda: e o caso que justifica
            # o buffer existir -- a maquina piorou enquanto ninguem via.
            frac = k / max(1, total - 1)
            vib = 0.20 + 0.9 * frac
            vel = 1.6 + 4.0 * frac
            crista = 3.4 + 3.6 * frac
            cli.publish(f"{BASE}/{dev}/telemetria", json.dumps({
                "device_id": dev,
                "ts": k * passo_s * 1000,
                "buffer": True,
                "atraso_ms": atraso_ms,
                "temperatura_c": round(48.0 + 22.0 * frac, 1),
                "vibracao": bloco_vibracao(vib, vel, crista),
            }), qos=0)
        print(f"  {dev}: {total} amostras enviadas")


def publicar_do_cadastro(cli, dispositivos, t):
    """Publica um ciclo para todos os dispositivos lidos do cadastro."""
    for dev, inv, i in dispositivos:
        fase = i * 0.7
        temp = 42.0 + (i % 7) * 3.0 + 2.5 * math.sin(t / 40.0 + fase) + random.gauss(0, 0.3)
        vib = 0.14 + (i % 5) * 0.03 + abs(random.gauss(0, 0.01))
        # Um em cada nove entra em zona critica, para a tela de escala ter
        # estados misturados em vez de um mar de verde.
        ruim = (i % 9 == 0)
        vel = (5.4 if ruim else 0.9 + (i % 6) * 0.08) + abs(random.gauss(0, 0.06))
        crista = random.uniform(6.0, 7.2) if ruim else random.uniform(3.0, 4.2)

        cli.publish(f"{BASE}/{dev}/telemetria", json.dumps({
            "device_id": dev,
            "ts": int(t * 1000),
            "temperatura_c": round(temp, 1),
            "vibracao": bloco_vibracao(vib, vel, crista),
            "rede": {"rssi_dbm": int(random.gauss(-62, 4)), "uptime_s": int(t)},
        }), qos=0)

        if not inv:
            continue
        corr = 8.0 + (i % 11) * 1.4 + random.gauss(0, 0.1)
        cli.publish(f"{BASE}/{inv}/inversor", json.dumps({
            "ts": int(time.time() * 1000),
            "corrente_a": round(corr, 2),
            "tensao_v": round(380.0 + random.gauss(0, 1.5), 1),
            "dc_bus_v": round(537.0 + random.gauss(0, 2.0), 1),
            "frequencia_hz": round(60.0 + random.gauss(0, 0.05), 2),
            "rodando": True,
            # Um inversor em falha, para o estado critico por drive aparecer.
            "falha": {"codigo": 8 if i == 3 and t > 15 else 0,
                      "texto": FALHAS_DEMO.get(8) if i == 3 and t > 15 else None},
            "status_bruto": 3,
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
    ap.add_argument("--do-cadastro", action="store_true",
                    help="le dados/ativos.json e simula TODOS os dispositivos "
                         "cadastrados (use com tools/gera_planta_teste.py "
                         "para testar o painel sob escala)")
    ap.add_argument("--backfill", type=float, default=0, metavar="MIN",
                    help="antes de comecar, despeja MIN minutos de amostras "
                         "'recuperadas do buffer' (simula a volta de uma "
                         "queda de comunicacao)")
    a = ap.parse_args()

    do_cadastro = None
    if a.do_cadastro:
        import os
        caminho = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "dados", "ativos.json")
        do_cadastro = ler_cadastro(caminho)
        devs = [d for d, _, _ in do_cadastro]
        inversores = [i for _, i, _ in do_cadastro if i]
        inversor = None
        print(f"lendo o cadastro: {len(devs)} ESP32 + {len(inversores)} inversores")
    elif a.demo:
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

    if a.backfill > 0:
        publicar_backfill(cli, devs, a.backfill)
        # Deixa o painel digerir a fila antes de comecar o fluxo ao vivo.
        time.sleep(1.0)
        print()

    t0 = time.time()
    try:
        while True:
            t = time.time() - t0
            if a.duracao and t > a.duracao:
                break

            if do_cadastro:
                publicar_do_cadastro(cli, do_cadastro, t)
                print(" t=%6.1fs  %d dispositivos publicando"
                      % (t, len(do_cadastro)), flush=True)
                time.sleep(a.intervalo)
                continue

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
