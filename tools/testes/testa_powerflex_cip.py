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
ok(pf.modo_envio("127.0.0.1") is False, "e memoriza o modo que funcionou")
diretos = [p for p in drv.pedidos if not p[4]]
ok(len(diretos) >= 7, "pedidos seguintes vao direto, sem nova tentativa")

print("\n=== 4. Drive que ACEITA Unconnected Send ===")
drv = DrivePF525(PARAMS, aceita_ucmm_send=True).subir()
pf, d = ler(drv)
ok(d.get("corrente_a") == 12.34, "le pelo envelope 0x52")
ok(pf.modo_envio("127.0.0.1") is True, "modo com Unconnected Send memorizado")

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
ok(pf.PADRAO.sem_objeto_falha, "e para de insistir no objeto que nao existe")

print("\n=== 7. Tabela de falhas (520-UM001, Drive Error Codes) ===")
pf_t = sys.modules[next(k for k in sys.modules if k.startswith("pf525_"))]
for cod, trecho in ((3, "alimentação"), (42, "U e W"), (43, "V e W"),
                    (63, "software"), (9, "módulo de controle"), (15, "carga")):
    t = pf_t.traduzir_falha(cod) or ""
    ok(trecho in t, f"F{cod} -> ...{trecho}...", f"-> {t}")
ok(pf_t.traduzir_falha(0) is None, "F0 = sem falha")
ok("ver manual" in pf_t.traduzir_falha(99), "codigo desconhecido nao vira 'sem falha'")

print("\n=== 8. Multi-Drive: drive 0 + dois encadeados pela RS-485 ===")
import json as _json, tempfile as _tmp, threading as _th, time as _time

no = DrivePF525({**PARAMS, 7: 0}).subir()
# drive 1 a 40 Hz / 7,80 A; drive 2 DESARMADO por F12 (sobrecorrente)
no.encadeados[1] = DrivePF525({1: 4000, 3: 780, 4: 2533, 5: 531, 6: 3, 7: 0})
no.encadeados[2] = DrivePF525({1: 0, 3: 0, 4: 0, 5: 532, 6: 0, 7: 12}, trip=1)

def _cfg(itens):
    f = _tmp.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    _json.dump({"inversores": itens}, f); f.close()
    return f.name

itens = [
    {"device_id": "u11", "ip": "127.0.0.1", "porta": no.porta, "drive": 0, "nome": "Exaustor 1", "tag": "U11"},
    {"device_id": "u12", "ip": "127.0.0.1", "porta": no.porta, "drive": 1, "nome": "Exaustor 2", "tag": "U12"},
    {"device_id": "u13", "ip": "127.0.0.1", "porta": no.porta, "drive": 2, "nome": "Bomba de recirculacao", "tag": "U13"},
]
pf = carregar_sidecar(no, PF525_INVERSORES=_cfg(itens))
invs = pf.carregar_inversores()
ok(len(invs) == 3 and len(pf.agrupar_por_no(invs)) == 1,
   "tres drives no mesmo IP = um no, uma sessao")
ok(invs[0].intervalo_s == 1.0 and invs[1].intervalo_s == 5.0,
   "encadeados lidos mais devagar por padrao (RS-485 de 19,2 kbps)",
   f"-> {[i.intervalo_s for i in invs]}")

with pf.abrir_drive("127.0.0.1", no.porta) as conn:
    L = {i.device_id: pf.ler_inversor(conn, i) for i in invs}
ok(L["u11"]["corrente_a"] == 12.34, "drive 0 lido", f"-> {L['u11']['corrente_a']}")
ok(L["u12"]["corrente_a"] == 7.8 and L["u12"]["frequencia_hz"] == 40.0,
   "drive 1 lido (nao e copia do drive 0)", f"-> {L['u12']['corrente_a']} A")
insts = {p[2] for p in no.pedidos if p[1] == 0x0F}
ok({17408 + 3, 18432 + 3} <= insts,
   "drive 1 pela instancia 17408+n, drive 2 pela 18432+n (manual, Ap. C)")
ok(L["u13"]["falha"]["codigo"] == 12 and L["u12"]["falha"]["codigo"] == 0
   and L["u11"]["falha"]["codigo"] == 0,
   "falha ativa so no drive 2, nao contamina os outros")
ok(any(p[1] == 0x97 and p[2] == 18432 for p in no.pedidos),
   "falha ativa do drive 2 lida na base 18432 do objeto 0x97")
ok(L["u12"]["origem"] == {"no": "127.0.0.1", "drive": 1, "nome": "Exaustor 2", "tag": "U12"},
   "origem vai no pacote: o cadastro sabe qual drive e qual", f"-> {L['u12']['origem']}")

# Com o sidecar RODANDO, o drive 2 e desligado.
class _CliFalso:
    def __init__(self): self.msgs = []
    def publish(self, t, p, qos=0, retain=False): self.msgs.append((t, p, retain))
no.encadeados[2].ligado = False
for i in invs:
    i.intervalo_s = 0.2
cli, parar = _CliFalso(), _th.Event()
t = _th.Thread(target=pf.atender_no, args=("127.0.0.1", no.porta, invs, cli, parar), daemon=True)
t.start(); _time.sleep(1.6); parar.set(); t.join(5)
pub = lambda dev: [m for m in cli.msgs if m[0] == f"monitoramento/{dev}/inversor"]
ok(len(pub("u11")) >= 3 and len(pub("u12")) >= 3,
   "com o drive 2 desligado, os drives 0 e 1 continuam publicando",
   f"-> {len(pub('u11'))} e {len(pub('u12'))} pacotes")
ok(("monitoramento/u13/status", "offline", True) in cli.msgs and not pub("u13"),
   "o drive 2 vira 'offline' no painel, e so ele")
ok(("monitoramento/u11/status", "online", True) in cli.msgs,
   "os que respondem sao marcados 'online'")

# Erros de digitacao no arquivo que o painel nao denunciaria
for rot, ruim in (("device_id repetido", [itens[0], {**itens[1], "device_id": "u11"}]),
                  ("drive fora de 0..4", [{**itens[0], "drive": 5}]),
                  ("mesmo drive duas vezes", [itens[0], {**itens[0], "device_id": "outro"}])):
    os.environ["PF525_INVERSORES"] = _cfg(ruim)
    try:
        pf.carregar_inversores(); barrou = False
    except SystemExit:
        barrou = True
    ok(barrou, f"arquivo com {rot} e recusado na partida")
os.environ.pop("PF525_INVERSORES", None)

print(f"\nRESULTADO: {'todas as verificacoes passaram.' if not falhas else f'{falhas} falha(s).'}")
sys.exit(1 if falhas else 0)
