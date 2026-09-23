"""Testa o sidecar do PowerFlex 525 contra um drive SIMULADO, por EtherNet/IP.

O drive simulado e a ferramenta tools/simuladores/drive_powerflex.py: um
servidor EtherNet/IP minimo que responde ao que o pycomm3 realmente manda --
RegisterSession, SendRRData com Get_Attribute_Single, e o envelope
Unconnected Send (0x52).

O que o drive simulado reproduz, do manual (520COM-UM001, Apendice C):
  * Parameter Object 0x0F: instancia = numero do parametro, valor no atrib. 1
  * DPI Parameter Object 0x93: mesma instancia, valor no atributo 9
  * DPI Fault Object 0x97: atributo de classe 4 = Fault Trip Instance
E dos parametros (520-UM001): b005 em volts inteiros, b007 = falha MAIS
RECENTE, que continua la depois do rearme.

Dois modos de drive, porque e o que o manual nao esclarece: um que aceita
Unconnected Send e um que o recusa (um adaptador que nao e roteador). O
sidecar tem de funcionar com os dois.

Limite honesto: o simulador e o sidecar partem da mesma leitura do manual e
do protocolo. Isto prova coerencia e encanamento, nao que o drive real se
comporta assim -- isso so a bancada prova.

    pip install pycomm3
    python tools/testes/testa_powerflex_cip.py
"""
import importlib.util
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
falhas = 0


def ok(cond, nome, extra=""):
    global falhas
    if not cond:
        falhas += 1
    print(f"  [{'OK ' if cond else 'FALHA'}] {nome}{('  ' + extra) if extra else ''}")


import logging
try:
    import pycomm3
    logging.getLogger('pycomm3').setLevel(logging.WARNING)
except ImportError:
    sys.exit("PULADO: falta o pycomm3 (pip install pycomm3)")


# O drive simulado mora em tools/simuladores/ -- e a MESMA ferramenta que se
# usa a mao. Uma versao so: o que o teste garante e o que voce roda.
sys.path.insert(0, str(RAIZ / "tools" / "simuladores"))
from drive_powerflex import DrivePF525  # noqa: E402


def carregar_sidecar(drive, **env):
    os.environ.update(PF525_IP="127.0.0.1", PF525_PORTA=str(drive.porta),
                      PF525_CLASSE="0x0F", PF525_UNCONNECTED_SEND="auto")
    os.environ.update(env)
    nome = f"pf525_{drive.porta}"
    spec = importlib.util.spec_from_file_location(
        nome, RAIZ / "integracoes" / "powerflex525" / "powerflex_mqtt.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


def ler(drive, **env):
    pf = carregar_sidecar(drive, **env)
    with pf.abrir_drive() as d:
        return pf, pf.ler_inversor(d)


# Motor rodando a 45,6 Hz, 12,34 A, 380 V, barramento 537 V. O b007 guarda
# uma sobrecarga (F7) de ONTEM, ja rearmada.
PARAMS = {1: 4560, 3: 1234, 4: 3800, 5: 537, 6: 0b00011, 7: 7}

print(f"\npycomm3 {pycomm3.__version__}")

# =====================================================================
print("\n=== 1. Leitura completa, drive sem falha ativa ===")
drv = DrivePF525(PARAMS, trip=0).subir()
pf, d = ler(drv)
esperado = {"frequencia_hz": 45.6, "corrente_a": 12.34, "tensao_v": 380.0,
            "dc_bus_v": 537.0}
for campo, v in esperado.items():
    ok(d.get(campo) == v, f"{campo} = {v}", f"-> {d.get(campo)}")
ok(d["dc_bus_v"] > 100,
   "b005 em volts inteiros (a escala antiga dava 53,7 V)")
ok(d["rodando"] is True, "rodando")
ok(d["falha"]["codigo"] == 0,
   "falha de ONTEM no b007 NAO vira falha ativa", f"-> {d['falha']}")
ok(d["ultima_falha"]["codigo"] == 7 and "Sobrecarga do motor" in d["ultima_falha"]["texto"],
   "mas continua visivel em ultima_falha", f"-> {d['ultima_falha']}")
lidas = {p[2] for p in drv.pedidos if p[1] == 0x0F}
ok(lidas == {1, 3, 4, 5, 6, 7}, "leu b001, b003..b007 na classe 0x0F",
   f"-> {sorted(lidas)}")
ok(all(p[3] == 1 for p in drv.pedidos if p[1] == 0x0F),
   "classe 0x0F: valor no atributo 1")

print("\n=== 2. Drive desarmado por falha ===")
params_falha = {**PARAMS, 1: 0, 3: 0, 7: 13}   # F13 aterramento
drv = DrivePF525(params_falha, trip=1).subir()
_, d = ler(drv)
ok(d["falha"]["codigo"] == 13 and "aterramento" in d["falha"]["texto"],
   "falha ativa = a mais recente (F13)", f"-> {d['falha']}")
ok(d["rodando"] is False, "parado")

print("\n=== 3. Drive que RECUSA Unconnected Send ===")
drv = DrivePF525(PARAMS, aceita_ucmm_send=False).subir()
pf, d = ler(drv)
ok(d.get("corrente_a") == 12.34, "modo auto cai para envio direto e le",
   f"-> {d.get('corrente_a')}")
ok(pf._ucmm_escolhido is False, "e memoriza o modo que funcionou")
diretos = [p for p in drv.pedidos if not p[4]]
ok(len(diretos) >= 7, "pedidos seguintes vao direto, sem nova tentativa")

print("\n=== 4. Drive que ACEITA Unconnected Send ===")
drv = DrivePF525(PARAMS, aceita_ucmm_send=True).subir()
pf, d = ler(drv)
ok(d.get("corrente_a") == 12.34, "le pelo envelope 0x52")
ok(pf._ucmm_escolhido is True, "modo com Unconnected Send memorizado")

print("\n=== 5. Classe DPI 0x93: valor no atributo 9 ===")
drv = DrivePF525(PARAMS).subir()
_, d = ler(drv, PF525_CLASSE="0x93")
ok(d.get("corrente_a") == 12.34, "corrente certa pela classe 0x93",
   f"-> {d.get('corrente_a')}")
ok(all(p[3] == 9 for p in drv.pedidos if p[1] == 0x93),
   "pediu o atributo 9 (o 1 e a senha de protecao)")

print("\n=== 6. Drive sem DPI Fault Object ===")
drv = DrivePF525({**PARAMS, 7: 13}, trip=1, tem_obj_falha=False).subir()
pf, d = ler(drv)
ok(d.get("corrente_a") == 12.34, "o resto da leitura chega")
ok(d["falha"]["codigo"] == 0,
   "sem saber se ha falha ativa, nao AFIRMA falha (evita alarme eterno)")
ok(d["ultima_falha"]["codigo"] == 13, "a ultima falha continua visivel")
ok(pf._sem_objeto_falha, "e para de insistir no objeto que nao existe")

print("\n=== 7. Tabela de falhas (520-UM001, Drive Error Codes) ===")
pf_t = sys.modules[next(k for k in sys.modules if k.startswith("pf525_"))]
for cod, trecho in ((3, "alimentação"), (42, "U e W"), (43, "V e W"),
                    (63, "software"), (9, "módulo de controle"), (15, "carga")):
    t = pf_t.traduzir_falha(cod) or ""
    ok(trecho in t, f"F{cod} -> ...{trecho}...", f"-> {t}")
ok(pf_t.traduzir_falha(0) is None, "F0 = sem falha")
ok("ver manual" in pf_t.traduzir_falha(99), "codigo desconhecido nao vira 'sem falha'")

print(f"\nRESULTADO: {'todas as verificacoes passaram.' if not falhas else f'{falhas} falha(s).'}")
sys.exit(1 if falhas else 0)
