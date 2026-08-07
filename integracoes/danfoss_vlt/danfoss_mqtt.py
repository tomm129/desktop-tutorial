#!/usr/bin/env python3
"""Sidecar de telemetria para inversores Danfoss VLT (série FC), via Modbus.

Publica EXATAMENTE o mesmo JSON que o sidecar do PowerFlex 525 — o painel
não sabe (nem precisa saber) a marca do inversor. É o contrato que está em
docs/arquitetura.md, e é ele que permite uma planta de marcas misturadas
aparecer numa tela só.

    monitoramento/<DEVICE_ID>/inversor

⚠️  NÃO VALIDADO EM HARDWARE. Escrito a partir da documentação oficial
    (Programming Guide FC 301/302 e o manual do Modbus TCP), sem nenhum
    Danfoss à mão. Rode primeiro com DANFOSS_LOG_BRUTO=1 e confira valor
    por valor contra o display do drive antes de confiar. Os pontos de
    dúvida estão marcados com "VERIFICAR" ao longo do arquivo.

Configuração por variável de ambiente (veja config.example.env):

    DANFOSS_TRANSPORTE   tcp | rtu
    DANFOSS_IP           IP do drive (transporte tcp)
    DANFOSS_PORTA        502
    DANFOSS_SERIAL       COM3 ou /dev/ttyUSB0 (transporte rtu)
    DANFOSS_BAUD         9600 | 19200 | 38400
    DANFOSS_UNIT         endereço do escravo (par. 8-31), padrão 1
    DANFOSS_MODO         parametro | pcd
"""
import json
import logging
import os
import sys
import time


# As dependências pesadas (paho-mqtt, pymodbus) são importadas SÓ na hora de
# usar, não aqui em cima.
#
# Não é preciosismo: com um `import` de topo que aborta, este arquivo não
# pode nem ser importado sem as bibliotecas instaladas — e aí o mapa de
# parâmetros, a conversão de endereço e a decodificação de alarme, que são
# lógica pura e sem dependência nenhuma, ficam impossíveis de testar. Foi
# exatamente o que aconteceu: a suíte pulava os testes deste módulo em
# silêncio, dando a impressão de que passavam.

# ---------------------------------------------------------------------------
#  Configuração
# ---------------------------------------------------------------------------
TRANSPORTE = os.getenv("DANFOSS_TRANSPORTE", "tcp").lower()
IP = os.getenv("DANFOSS_IP", "192.168.1.30")
PORTA = int(os.getenv("DANFOSS_PORTA", "502"))
SERIAL = os.getenv("DANFOSS_SERIAL", "/dev/ttyUSB0")
BAUD = int(os.getenv("DANFOSS_BAUD", "9600"))
UNIT = int(os.getenv("DANFOSS_UNIT", "1"))
MODO = os.getenv("DANFOSS_MODO", "parametro").lower()

INTERVALO_S = float(os.getenv("DANFOSS_INTERVALO_S", "1.0"))
LOG_BRUTO = os.getenv("DANFOSS_LOG_BRUTO", "0") == "1"

DEVICE_ID = os.getenv("DEVICE_ID", "danfoss-01")
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "")
MQTT_PASS = os.getenv("MQTT_PASS", "")
BASE = os.getenv("MQTT_BASE_TOPIC", "monitoramento")

TOPIC_INVERSOR = f"{BASE}/{DEVICE_ID}/inversor"
TOPIC_STATUS = f"{BASE}/{DEVICE_ID}/status"

FREQ_PARADO_HZ = float(os.getenv("DANFOSS_FREQ_PARADO_HZ", "0.5"))

# ---------------------------------------------------------------------------
#  Mapa de parâmetros — grupo 16 "Data Readouts"
#
#  Conferido contra o Programming Guide VLT AutomationDrive FC 301/302.
#  As escalas ("conversion index" na linguagem da Danfoss) são o ponto mais
#  provável de erro: elas variam entre famílias (FC 51 x FC 302 x FC 360).
#  Rode com DANFOSS_LOG_BRUTO=1 e compare com o display antes de confiar.
#
#  Um ganho sobre o PowerFlex: o Danfoss publica 16-17 Speed [RPM], a
#  VELOCIDADE REAL do eixo. Com ela o escorregamento é medido, não estimado
#  da plaqueta — o que torna exata a frequência 2·s·f que a sonda de MCSA
#  procura (ver tools/mcsa_sonda.py).
# ---------------------------------------------------------------------------
def _escala(nome, padrao):
    return float(os.getenv(f"DANFOSS_ESCALA_{nome}", padrao))


# O grupo 16 NÃO é o mesmo em toda a linha FC, e a diferença quebra código.
#
# Conferido nos guias de programação de cada família: o FC 51 Micro Drive
# NÃO tem 16-16 Torque nem 16-17 Speed [RPM] -- eles existem só no
# FC 301/302. Tentar lê-los num FC 51 devolve exceção de Modbus e derruba a
# leitura inteira, levando junto os parâmetros que existiam.
#
# Daí os perfis por família. E, como rede de segurança, qualquer parâmetro
# que falhe na leitura é abandonado em vez de derrubar o ciclo (ver
# ler_inversor) -- isso cobre também as famílias que ninguém testou.
FAMILIA = os.getenv("DANFOSS_FAMILIA", "fc302").lower()

# campo no JSON        PNU    escala                     casas
_COMUNS = {
    "frequencia_hz": (1613, _escala("FREQ", "0.1"), 2),
    "corrente_a":    (1614, _escala("CORRENTE", "0.01"), 2),
    "tensao_v":      (1612, _escala("TENSAO", "0.1"), 1),
    "dc_bus_v":      (1630, _escala("DCBUS", "1.0"), 1),
    "potencia_kw":   (1610, _escala("POTENCIA", "0.01"), 2),
    "motor_termico_pct": (1618, _escala("TERMICO", "1.0"), 0),
    "dissipador_c":  (1634, _escala("DISSIPADOR", "1.0"), 0),
    "status_bruto":  (1603, 1.0, 0),
    "alarme_palavra": (1690, 1.0, 0),
}

PERFIS = {
    # FC 301 / FC 302 AutomationDrive: grupo 16 completo.
    "fc302": dict(_COMUNS, **{
        # Velocidade REAL do eixo. Não é conforto: com ela o
        # escorregamento é medido em vez de estimado da plaqueta, e a
        # frequência 2·s·f que a sonda de MCSA procura deixa de ser
        # palpite (ver tools/mcsa_sonda.py).
        "rpm":       (1617, _escala("RPM", "1.0"), 0),
        "torque_nm": (1616, _escala("TORQUE", "0.1"), 1),
    }),
    # FC 51 Micro Drive: sem 16-16 e sem 16-17.
    "fc51": dict(_COMUNS),
}
PERFIS["fc301"] = PERFIS["fc302"]

PARAMETROS = PERFIS.get(FAMILIA, PERFIS["fc302"])

# Alarmes do FC 301/302. A palavra 16-90 é um CAMPO DE BITS de 32 bits, e
# não um número de falha como no PowerFlex — vários alarmes podem estar
# ativos ao mesmo tempo. Índice = número do bit.
#
# VERIFICAR: a numeração muda entre famílias. Esta é a do FC 301/302.
ALARMES = {
    1:  "Falha de tensão de alimentação",
    2:  "Erro de tensão auxiliar",
    3:  "Sem motor",
    4:  "Falta de fase da rede",
    5:  "Tensão do barramento CC alta",
    6:  "Tensão do barramento CC baixa",
    7:  "Sobretensão do barramento CC",
    8:  "Subtensão do barramento CC",
    9:  "Sobrecarga do inversor",
    10: "Sobretemperatura do motor (ETR)",
    11: "Sobretemperatura do termistor do motor",
    12: "Limite de torque",
    13: "Sobrecorrente",
    14: "Falha de aterramento",
    15: "Falha de hardware",
    16: "Curto-circuito",
    17: "Timeout da palavra de controle",
    22: "Freio de içamento",
    25: "Resistor de frenagem em curto",
    26: "Limite de potência do resistor de frenagem",
    27: "Falha do chopper de frenagem",
    28: "Falha na verificação do freio",
    29: "Sobretemperatura do dissipador",
    30: "Falta da fase U do motor",
    31: "Falta da fase V do motor",
    32: "Falta da fase W do motor",
    33: "Falha de inrush",
    38: "Falha interna",
    47: "Falha na alimentação de 24 V",
    48: "Falha na alimentação de 1,8 V",
    50: "Falha de calibração do AMA",
    51: "Verificação Unom/Inom do AMA",
    59: "Limite de corrente",
    64: "Limite de tensão",
    69: "Sobretemperatura da placa de potência",
    80: "Drive inicializado no padrão",
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("danfoss")


# ---------------------------------------------------------------------------
#  Modbus
# ---------------------------------------------------------------------------
def endereco_de(pnu: int) -> int:
    """Converte número de parâmetro Danfoss (PNU) em endereço Modbus.

    A regra da Danfoss é: cada parâmetro ocupa DOIS registradores de 16 bits
    (os valores são de 32 bits, big-endian), e o endereço do primeiro é

        registrador = (PNU × 10) − 1

    Exemplo: 16-14 Motor current -> PNU 1614 -> registrador 16139, lendo 2.

    VERIFICAR NA BANCADA. Não consegui confirmar esta fórmula no PDF oficial
    que baixei (era o manual da placa Modbus TCP, que trata do mecanismo PCD
    e não do acesso direto a parâmetro). Ela é a regra citada nos manuais de
    Modbus RTU da linha VLT, mas há famílias — a FC 51 Micro Drive em
    particular — que usam mapeamento próprio.

    Se os valores saírem sem sentido, use o modo 'pcd' (ver ler_pcd) ou o
    utilitário de descoberta: python danfoss_mqtt.py --varrer 1614
    """
    return pnu * 10 - 1


def abrir_cliente():
    try:
        from pymodbus.client import ModbusTcpClient, ModbusSerialClient
    except ImportError:
        sys.exit("Falta o pymodbus. Instale com: pip install pymodbus")

    if TRANSPORTE == "rtu":
        # A Danfoss usa 8 bits, paridade PAR, 1 stop bit por padrão
        # (par. 8-32/8-33). Se o drive foi reconfigurado, ajuste aqui.
        cli = ModbusSerialClient(port=SERIAL, baudrate=BAUD,
                                 bytesize=8, parity="E", stopbits=1,
                                 timeout=1.0)
        alvo = f"{SERIAL} @ {BAUD} 8E1, unit {UNIT}"
    else:
        cli = ModbusTcpClient(IP, port=PORTA, timeout=2.0)
        alvo = f"{IP}:{PORTA}, unit {UNIT}"

    if not cli.connect():
        raise ConnectionError(f"nao conectou em {alvo}")
    log.info("Modbus conectado: %s", alvo)
    return cli


def _ler_registradores(cli, endereco, quantidade):
    """Lê registradores holding, tolerando as duas assinaturas do pymodbus.

    O pymodbus 3.x trocou 'unit=' por 'slave=' e depois por 'device_id='.
    Como o Orange Pi pode ter qualquer versão do repositório da distro,
    tentamos as variantes em vez de fixar uma e quebrar na instalação.
    """
    ultimo_erro = None
    for kw in ("device_id", "slave", "unit"):
        try:
            r = cli.read_holding_registers(endereco, count=quantidade,
                                           **{kw: UNIT})
            return r
        except TypeError as e:
            ultimo_erro = e
            continue
    raise RuntimeError(f"pymodbus incompativel: {ultimo_erro}")


def ler_parametro(cli, pnu: int) -> int:
    """Lê um parâmetro de 32 bits (2 registradores, big-endian)."""
    r = _ler_registradores(cli, endereco_de(pnu), 2)
    if r is None or (hasattr(r, "isError") and r.isError()):
        raise IOError(f"erro lendo PNU {pnu}")
    alto, baixo = r.registers[0], r.registers[1]
    valor = (alto << 16) | baixo
    # Complemento de dois: torque e velocidade são com sinal (motor pode
    # girar ao contrário ou frenar). Ler sem sinal transformaria −5 Nm num
    # número gigante e o painel mostraria torque absurdo em vez de negativo.
    if valor >= 0x80000000:
        valor -= 0x100000000
    return valor


def ler_pcd(cli) -> list:
    """Lê o bloco de Process Data (registradores 2910-2919).

    Este é o caminho RÁPIDO: uma única transação Modbus devolve até 10
    parâmetros, contra uma ida-e-volta por parâmetro no modo 'parametro'.

    Exige configurar o drive antes: o parâmetro 12-22 [Process Data Config
    Read] define QUAIS parâmetros aparecem nesses registradores, na ordem.
    Sem essa configuração, o bloco devolve lixo ou zeros — e nada avisa.
    Por isso o modo padrão continua sendo 'parametro'.

    Vale muito para a sonda de MCSA (tools/mcsa_sonda.py): com uma leitura
    só por amostra, a taxa sobe o suficiente para procurar a modulação em
    2·s·f, coisa que no PowerFlex a mensageria explícita não permite.
    """
    r = _ler_registradores(cli, 2910, 10)
    if r is None or (hasattr(r, "isError") and r.isError()):
        raise IOError("erro lendo o bloco PCD 2910-2919")
    return list(r.registers)


# ---------------------------------------------------------------------------
#  Telemetria
# ---------------------------------------------------------------------------
def decodificar_alarmes(palavra: int) -> tuple:
    """Traduz a palavra de alarme (campo de bits) em (codigo, texto).

    A diferença de modelo em relação ao PowerFlex é real: lá o drive entrega
    UM número de falha; aqui entrega um campo de bits onde vários alarmes
    convivem. Para manter o mesmo contrato JSON, reportamos o menor bit
    ativo como 'codigo' e juntamos todos os textos — assim o painel continua
    funcionando sem saber a marca, e nenhum alarme fica escondido.
    """
    if not palavra:
        return 0, None
    ativos = [b for b in range(32) if palavra & (1 << b)]
    if not ativos:
        return 0, None
    textos = [ALARMES.get(b, f"alarme bit {b} (ver manual)") for b in ativos]
    return ativos[0], " | ".join(textos)


# Parâmetros que o drive recusou. Um por família/firmware; depois de
# descoberto, para de ser pedido — não adianta insistir a cada ciclo.
_indisponiveis = set()

# Sem estes o pacote não serve para nada: se um deles falhar, é problema de
# comunicação ou de mapeamento, e tem de estourar para o laço reconectar em
# vez de publicar telemetria pela metade como se estivesse tudo bem.
ESSENCIAIS = {"frequencia_hz", "corrente_a"}


def ler_inversor(cli) -> dict:
    bruto = {}
    dados = {}
    for campo, (pnu, escala, casas) in PARAMETROS.items():
        if campo in _indisponiveis:
            continue
        try:
            v = ler_parametro(cli, pnu)
        except Exception as e:
            if campo in ESSENCIAIS:
                raise
            # Parâmetro que esta família não tem. Registra uma vez e segue:
            # perder o torque não é motivo para perder a corrente também.
            _indisponiveis.add(campo)
            log.warning("parâmetro %s (PNU %d) indisponível neste drive (%s) "
                        "— seguindo sem ele", campo, pnu, e)
            continue
        bruto[campo] = v
        dados[campo] = round(v * escala, casas) if casas else int(v)

    if LOG_BRUTO:
        log.info("bruto: %s", bruto)

    palavra = int(dados.pop("alarme_palavra", 0))
    status = int(dados.pop("status_bruto", 0))
    codigo, texto = decodificar_alarmes(palavra)

    # Mesma decisão do sidecar do PowerFlex, e pelo mesmo motivo: "rodando"
    # sai da FREQUÊNCIA DE SAÍDA, não de um bit de status. O bit continua
    # verdadeiro com o motor parado em zero Hz, e o mapa de bits muda entre
    # firmwares. Frequência acima de zero é física, não interpretação.
    dados["rodando"] = dados.get("frequencia_hz", 0.0) > FREQ_PARADO_HZ

    dados["falha"] = {"codigo": codigo, "texto": texto}
    dados["status_bruto"] = status
    # A palavra crua vai junto: se precisar dos bits, decodifique contra o
    # SEU manual em vez de confiar num mapa que pode não ser o da sua família.
    dados["alarme_bruto"] = palavra
    dados["ts"] = int(time.time() * 1000)
    return dados


def conectar_mqtt():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        sys.exit("Falta o paho-mqtt. Instale com: pip install paho-mqtt")

    try:                      # paho 2.x exige a versão da API de callback
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                          client_id=f"danfoss-{DEVICE_ID}")
    except AttributeError:    # paho 1.x
        cli = mqtt.Client(client_id=f"danfoss-{DEVICE_ID}")

    if MQTT_USER:
        cli.username_pw_set(MQTT_USER, MQTT_PASS)
    cli.will_set(TOPIC_STATUS, "offline", qos=1, retain=True)
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    cli.loop_start()
    cli.publish(TOPIC_STATUS, "online", qos=1, retain=True)
    log.info("MQTT conectado em %s:%s; publicando em %s",
             MQTT_HOST, MQTT_PORT, TOPIC_INVERSOR)
    return cli


def varrer(pnu_alvo: int) -> None:
    """Ajuda a descobrir o mapeamento certo quando a fórmula não bate.

    Lê uma faixa de registradores em torno do endereço calculado e mostra o
    que há em cada um. Ponha o display do drive no parâmetro em questão e
    procure o valor: é assim que se acha o offset da sua família sem
    adivinhar.
    """
    cli = abrir_cliente()
    base = endereco_de(pnu_alvo)
    print(f"\nPNU {pnu_alvo} -> endereco calculado {base}")
    print("varrendo de -6 a +6 em volta:\n")
    for d in range(-6, 7):
        end = base + d
        try:
            r = _ler_registradores(cli, end, 2)
            if r is None or (hasattr(r, "isError") and r.isError()):
                print(f"  {end:6d}  erro")
                continue
            a, b = r.registers[0], r.registers[1]
            v32 = (a << 16) | b
            marca = "  <== calculado" if d == 0 else ""
            print(f"  {end:6d}  16b={a:6d}  32b={v32:12d}{marca}")
        except Exception as e:
            print(f"  {end:6d}  {e}")
    cli.close()


def bancada() -> None:
    """Lê tudo uma vez e imprime lado a lado com o parâmetro do display.

    É o primeiro comando a rodar num drive novo. Não precisa de MQTT nem de
    broker: conecta, lê, mostra, sai. Ponha o display do drive em cada
    parâmetro da coluna esquerda e compare com o valor da direita.

    O que se está conferindo aqui não é se o programa roda — é se a ESCALA
    e o MAPEAMENTO DE REGISTRADOR estão certos para esta família. São os
    dois pontos onde a documentação da Danfoss varia entre modelos, e onde
    um erro passa despercebido porque o número continua parecendo
    plausível: 123,0 A em vez de 12,30 A ainda é "um número de corrente".
    """
    print(f"\nfamília configurada: {FAMILIA}")
    print(f"parâmetros do perfil: {len(PARAMETROS)}\n")
    cli = abrir_cliente()
    print(f"{'campo':<22} {'PNU':>6} {'registrador':>12} "
          f"{'bruto':>12} {'com escala':>12}")
    print("-" * 68)
    for campo, (pnu, escala, casas) in PARAMETROS.items():
        grupo = f"{pnu // 100}-{pnu % 100:02d}"
        try:
            v = ler_parametro(cli, pnu)
            escalado = round(v * escala, casas) if casas else int(v)
            print(f"{campo:<22} {grupo:>6} {endereco_de(pnu):>12} "
                  f"{v:>12} {escalado:>12}")
        except Exception as e:
            print(f"{campo:<22} {grupo:>6} {endereco_de(pnu):>12} "
                  f"{'ERRO':>12}   {e}")
    cli.close()
    print("\nConfira cada linha contra o display do drive.")
    print("Se o BRUTO for 1230 e o display marcar 12,3 A -> escala 0.01 (ok).")
    print("Se vier erro ou lixo em tudo -> o mapeamento de registrador desta")
    print("família é outro: rode  --varrer 1614  para achá-lo.")


def main() -> None:
    if "--bancada" in sys.argv:
        bancada()
        return
    if "--varrer" in sys.argv:
        i = sys.argv.index("--varrer")
        varrer(int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 1614)
        return

    cli = conectar_mqtt()
    falha_anterior = None
    try:
        while True:
            modbus = None
            try:
                modbus = abrir_cliente()
                while True:
                    dados = ler_inversor(modbus)
                    cli.publish(TOPIC_INVERSOR, json.dumps(dados), qos=0)

                    cod = dados["falha"]["codigo"]
                    if cod != falha_anterior:
                        if cod:
                            log.warning("ALARME: %s", dados["falha"]["texto"])
                        elif falha_anterior:
                            log.info("alarme anterior sanado")
                        falha_anterior = cod

                    log.debug("%s", dados)
                    time.sleep(INTERVALO_S)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log.warning("Erro no Modbus (%s). Retentando em 5 s...", e)
                time.sleep(5)
            finally:
                if modbus is not None:
                    try:
                        modbus.close()
                    except Exception:
                        pass
    except KeyboardInterrupt:
        log.info("Encerrando por solicitação do usuário.")
    finally:
        cli.publish(TOPIC_STATUS, "offline", qos=1, retain=True)
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
