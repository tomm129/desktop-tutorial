"""Testa o sidecar Danfoss contra um drive SIMULADO, por Modbus TCP de verdade.

O testa_inversores.py cobre a logica pura (endereco, largura, alarme). Este
cobre o que ele nao alcanca: a CONVERSA Modbus -- a chamada do pymodbus
(que trocou 'unit=' por 'slave=' e depois por 'device_id='), a contagem de
registradores pedida para cada largura e o enderecamento de ponta a ponta.

O drive simulado e montado a partir do manual, nao do codigo: cada
parametro existe SO nos registradores que o manual diz que ele ocupa (um
para 16 bits, dois para 32). Pedir registrador a mais cai em endereco
inexistente e devolve excecao -- como num drive real. Foi assim que o bug
dos parametros de 16 bits lidos como 32 teria aparecido aqui.

Limite honesto: o simulador e o sidecar partem da MESMA leitura do manual.
Este teste prova coerencia e encanamento; so a bancada com um drive real
prova que a leitura do manual esta certa.

    pip install pymodbus
    python tools/testes/testa_danfoss_modbus.py
"""
import importlib.util
import os
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PORTA = 15020
falhas = 0


def ok(cond, nome, extra=""):
    global falhas
    if not cond:
        falhas += 1
    print(f"  [{'OK ' if cond else 'FALHA'}] {nome}{('  ' + extra) if extra else ''}")


try:
    import pymodbus
    from pymodbus.server import StartTcpServer, ServerStop
    from pymodbus.datastore import ModbusServerContext, ModbusSparseDataBlock
    try:
        from pymodbus.datastore import ModbusDeviceContext as _Ctx   # >= 3.10
    except ImportError:
        from pymodbus.datastore import ModbusSlaveContext as _Ctx    # < 3.10
except ImportError:
    sys.exit("PULADO: falta o pymodbus (pip install pymodbus)")


# --- Estado do drive simulado -------------------------------------------
# Um FC 302 rodando, freando (torque negativo), com dois alarmes ativos.
# Valores BRUTOS, ja na forma que o manual diz que o drive transmite.
def u32(v):
    v &= 0xFFFFFFFF
    return [v >> 16, v & 0xFFFF]


def u16(v):
    return [v & 0xFFFF]


ALARMES_ATIVOS = (1 << 5) | (1 << 31)       # sobrecorrente + freio mecanico
DRIVE = {
    1613: u16(456),          # 45,6 Hz        Uint16 -1
    1614: u32(1234),         # 12,34 A        Int32  -2
    1612: u16(3800),         # 380,0 V        Uint16 -1
    1630: u16(537),          # 537 V          Uint16  0
    1610: u32(550),          # 5,50 kW        Int32   1 (x10 W)
    1618: u16(42),           # 42 %           Uint8
    1634: u16(38),           # 38 °C          Uint8 100
    1603: u16(0x0F07),       # status         V2
    1690: u32(ALARMES_ATIVOS),
    1617: u32(1480),         # 1480 rpm       Int32 67
    1616: u16(-50),          # -5,0 Nm        Int16 -1 (frenando)
}


def montar_servidor(drive):
    """Cada parametro ocupa SO os registradores do seu tipo, no endereco
    (PNU x 10) - 1 do telegrama. O resto do mapa nao existe."""
    regs = {}
    for pnu, palavras in drive.items():
        for i, w in enumerate(palavras):
            regs[pnu * 10 - 1 + i] = w
    bloco = ModbusSparseDataBlock(regs)
    try:
        dev = _Ctx(hr=bloco)
    except TypeError:
        dev = _Ctx(hr=bloco, zero_mode=True)
    try:
        return ModbusServerContext(devices=dev, single=True)
    except TypeError:
        return ModbusServerContext(slaves=dev, single=True)


def subir(drive):
    ctx = montar_servidor(drive)
    t = threading.Thread(
        target=lambda: StartTcpServer(context=ctx, address=("127.0.0.1", PORTA)),
        daemon=True)
    t.start()
    time.sleep(1.5)
    return t


def carregar_sidecar(familia):
    os.environ.update(DANFOSS_TRANSPORTE="tcp", DANFOSS_IP="127.0.0.1",
                      DANFOSS_PORTA=str(PORTA), DANFOSS_UNIT="1",
                      DANFOSS_FAMILIA=familia)
    nome = f"danfoss_{familia}"
    spec = importlib.util.spec_from_file_location(
        nome, RAIZ / "integracoes" / "danfoss_vlt" / "danfoss_mqtt.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


# =====================================================================
print(f"\npymodbus {pymodbus.__version__}")

# O ajuste de endereco do datastore mudou entre versoes do pymodbus. Antes
# de testar o sidecar, prova que o SIMULADO responde onde o manual manda --
# senao uma falha aqui acusaria o sidecar pelo erro do simulador.
print("\n=== 0. O drive simulado responde no endereco do manual ===")
subir(DRIVE)
from pymodbus.client import ModbusTcpClient   # noqa: E402

c = ModbusTcpClient("127.0.0.1", port=PORTA)
c.connect()
r = None
for kw in ("device_id", "slave", "unit"):
    try:
        r = c.read_holding_registers(16139, count=2, **{kw: 1})
        break
    except TypeError:
        continue
c.close()
if r is None or r.isError():
    sys.exit("  simulador nao responde em 16139 -- ajuste o montar_servidor "
             "para esta versao do pymodbus antes de confiar no resto")
ok(list(r.registers) == u32(1234), "16-14 esta em 16139..16140",
   f"-> {list(r.registers)}")

print("\n=== 1. FC 302: leitura completa pelo sidecar ===")
d302 = carregar_sidecar("fc302")
cli = d302.abrir_cliente()
dados = d302.ler_inversor(cli)
cli.close()

esperado = {"frequencia_hz": 45.6, "corrente_a": 12.34, "tensao_v": 380.0,
            "dc_bus_v": 537.0, "potencia_kw": 5.5, "motor_termico_pct": 42,
            "dissipador_c": 38, "rpm": 1480, "torque_nm": -5.0}
for campo, v in esperado.items():
    ok(dados.get(campo) == v, f"{campo} = {v}", f"-> {dados.get(campo)}")

ok(dados["rodando"] is True, "rodando (frequencia > limiar)")
ok(dados["falha"]["codigo"] == 5, "codigo = menor bit ativo (5)",
   f"-> {dados['falha']['codigo']}")
txt = dados["falha"]["texto"] or ""
ok("Sobrecorrente (A13)" in txt and "(A63)" in txt,
   "os dois alarmes aparecem no texto", f"-> {txt}")
ok(dados["alarme_bruto"] == ALARMES_ATIVOS,
   "palavra crua vai sem sinal (bit 31 nao vira negativo)",
   f"-> {dados['alarme_bruto']}")
ok(not d302._indisponiveis, "nenhum parametro abandonado no FC 302")

print("\n=== 2. FC 51: sem 16-16 e 16-17, o resto chega inteiro ===")
# Um drive SEM torque e rpm, mesmo que o perfil erre e peca por eles.
PORTA += 1
fc51 = {k: v for k, v in DRIVE.items() if k not in (1616, 1617)}
subir(fc51)
d51 = carregar_sidecar("fc51")
cli = d51.abrir_cliente()
dados = d51.ler_inversor(cli)
cli.close()
ok(dados.get("corrente_a") == 12.34 and dados.get("frequencia_hz") == 45.6,
   "corrente e frequencia do FC 51")
ok("rpm" not in dados and "torque_nm" not in dados,
   "perfil fc51 nem pede 16-16/16-17")

# O erro de configuracao mais provavel: FC 51 declarado como fc302.
PORTA += 1
subir(fc51)
d_errado = carregar_sidecar("fc302")
cli = d_errado.abrir_cliente()
dados = d_errado.ler_inversor(cli)
cli.close()
ok(dados.get("corrente_a") == 12.34,
   "familia errada: a corrente chega mesmo assim")
ok({"rpm", "torque_nm"} <= d_errado._indisponiveis,
   "familia errada: rpm e torque abandonados, nao derrubam o ciclo",
   f"-> {sorted(d_errado._indisponiveis)}")

try:
    ServerStop()
except Exception:
    pass

print(f"\nRESULTADO: {'todas as verificacoes passaram.' if not falhas else f'{falhas} falha(s).'}")
sys.exit(1 if falhas else 0)
