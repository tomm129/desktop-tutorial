"""Testa o serviço único de inversores (integracoes/inversores).

O painel vai escrever a lista de inversores e o serviço a aplica sozinho.
Este teste cobre as duas pontas disso sem painel nenhum:

  1. a validação -- o que o formulário vai mostrar como erro;
  2. PowerFlex (com Multi-Drive) e Danfoss lidos AO MESMO TEMPO, dos
     simuladores, pela configuração em arquivo;
  3. a configuração mudando com o serviço no ar: quem entra passa a
     publicar, quem sai vira offline, sem reiniciar nada;
  4. item inválido não derruba os outros;
  5. sem arquivo (gateway recém-instalado), o serviço não fica reaplicando.

    pip install pycomm3 pymodbus
    python tools/testes/testa_servico_inversores.py
"""
import importlib.util
import json
import logging
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
falhas = 0


def ok(cond, nome, extra=""):
    global falhas
    if not cond:
        falhas += 1
    print(f"  [{'OK ' if cond else 'FALHA'}] {nome}{('  ' + extra) if extra else ''}")


try:
    import pycomm3  # noqa: F401
    import pymodbus  # noqa: F401
except ImportError as e:
    sys.exit(f"PULADO: falta {e.name} (pip install pycomm3 pymodbus)")

sys.path.insert(0, str(RAIZ / "tools" / "simuladores"))
from drive_powerflex import DrivePF525  # noqa: E402
from drive_danfoss import DriveDanfoss  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "servico_inversores", RAIZ / "integracoes" / "inversores" / "servico_inversores.py")
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)
logging.getLogger("inversores").setLevel(logging.ERROR)
CAT = srv.carregar_catalogo()


def pf(iid, ip, pos=0, porta=44818, **extra):
    return {"id": iid, "modelo": "pf525", "conexao": {"tipo": "cip", "ip": ip,
            "posicao": pos, "porta": porta}, **extra}


def rtu(iid, end, porta="/dev/ttyUSB0", modelo="danfoss_fc51", **c):
    return {"id": iid, "modelo": modelo, "conexao": {"tipo": "rtu", "porta_serial": porta,
            "endereco": end, **c}}


def erros_de(itens):
    return {e["id"]: e["erro"] for e in srv.validar({"inversores": itens}, CAT)[1]}


# =====================================================================
print("\n=== 1. Validação: o que o formulário vai recusar ===")
casos = [
    ("id repetido", [pf("a", "10.0.0.1"), pf("a", "10.0.0.2")], "a", "repetido"),
    ("modelo desconhecido", [{"id": "x", "modelo": "abb_acs", "conexao": {}}], "x", "desconhecido"),
    ("FC 51 por TCP (ele so tem RS-485)",
     [{"id": "x", "modelo": "danfoss_fc51", "conexao": {"tipo": "tcp", "ip": "10.0.0.1"}}], "x", "rtu"),
    ("IP invalido", [pf("x", "10.0.0.300")], "x", "IP"),
    ("posicao 5 no no", [pf("x", "10.0.0.1", 5)], "x", "0 a 4"),
    ("mesmo drive duas vezes", [pf("a", "10.0.0.1", 1), pf("b", "10.0.0.1", 1)], "b", "a"),
    ("mesmo endereco no mesmo barramento", [rtu("a", 3), rtu("b", 3)], "b", "endereço 3"),
    ("velocidade diferente no mesmo barramento",
     [rtu("a", 1, baud=9600), rtu("b", 2, baud=19200)], "b", "mesma velocidade"),
    ("endereco 0", [rtu("x", 0)], "x", "1 a 247"),
]
for rot, itens, quem, trecho in casos:
    e = erros_de(itens)
    ok(quem in e and trecho in e[quem], f"recusa: {rot}", f"-> {e.get(quem)}")

validos, e = srv.validar({"inversores": [
    pf("a", "10.0.0.1", 0), pf("b", "10.0.0.1", 1),       # mesmo no, posicoes diferentes
    rtu("c", 1), rtu("d", 2),                             # mesmo barramento, enderecos diferentes
    rtu("f", 1, porta="/dev/ttyUSB1", baud=19200),        # outro barramento, outra velocidade
    {**pf("g", "10.0.0.9"), "habilitado": False},         # desligado: nao le, nao e erro
]}, CAT)
ok(not e and [v["id"] for v in validos] == ["a", "b", "c", "d", "f"],
   "configuracao legitima passa inteira (e o desabilitado fica de fora)",
   f"-> {[v['id'] for v in validos]} erros={e}")


print("\n=== 1b. Os casos COMPARTILHADOS com o validador do painel (JS) ===")
# O painel valida com o mesmo conjunto de regras em JavaScript. Os dois
# testes leem este arquivo: se as regras divergirem, um deles quebra.
casos = json.loads((Path(__file__).parent / "casos_validacao_inversores.json")
                   .read_text(encoding="utf-8"))["casos"]
iguais = 0
for c in casos:
    v, e = srv.validar({"inversores": c["inversores"]}, CAT)
    ids = [x["id"] for x in v]
    erros = {x["id"]: x["erro"] for x in e}
    bate = (ids == c["validos"] and len(erros) == len(c["erros"])
            and all(t in erros.get(i, "") for i, t in c["erros"].items()))
    if bate:
        iguais += 1
    else:
        ok(False, f"caso compartilhado: {c['caso']}", f"-> {ids} {erros}")
ok(iguais == len(casos), f"validador do servico bate com os {len(casos)} casos compartilhados com o painel",
   f"-> {iguais}/{len(casos)}")


# =====================================================================
class CliFalso:
    def __init__(self):
        self.msgs, self.trava = [], threading.Lock()

    def publish(self, t, p, qos=0, retain=False):
        with self.trava:
            self.msgs.append((t, p, retain))

    def de(self, topico):
        with self.trava:
            return [p for t, p, _ in self.msgs if t == topico]


no = DrivePF525({1: 4560, 3: 1234, 4: 2888, 5: 537, 6: 3, 7: 0}).subir()
no.encadeados[1] = DrivePF525({1: 4000, 3: 780, 4: 2533, 5: 531, 6: 3, 7: 0})
no.encadeados[2] = DrivePF525({1: 3500, 3: 660, 4: 2216, 5: 532, 6: 3, 7: 0})
dan = DriveDanfoss("normal", "fc302").subir("127.0.0.1", 0)

pasta = Path(tempfile.mkdtemp())
arq = pasta / "inversores.json"


def gravar(itens):
    arq.write_text(json.dumps({"inversores": itens}), encoding="utf-8")
    time.sleep(0.05)


u11 = pf("u11", "127.0.0.1", 0, no.porta, nome="Exaustor 1", tag="U11", intervalo_s=0.3)
u12 = pf("u12", "127.0.0.1", 1, no.porta, nome="Exaustor 2", tag="U12", intervalo_s=0.3)
u13 = pf("u13", "127.0.0.1", 2, no.porta, nome="Bomba", tag="U13", intervalo_s=0.3)
fc = {"id": "fc1", "modelo": "danfoss_fc302", "nome": "Ventilador", "tag": "D1",
      "intervalo_s": 0.3,
      "conexao": {"tipo": "tcp", "ip": "127.0.0.1", "porta": dan.porta, "endereco": 1}}
ruim = pf("ruim", "999.1.1.1")

print("\n=== 2. PowerFlex (Multi-Drive) e Danfoss juntos, do arquivo ===")
gravar([u11, u12, fc, ruim])
cli = CliFalso()
servico = srv.Servico(arq, srv.Publicador(cli), CAT)
srv.RELEITURA_S = 0.3
parar = threading.Event()
t = threading.Thread(target=servico.rodar, args=(parar,), daemon=True)
t.start()
time.sleep(3)

def ultimo(iid):
    p = cli.de(f"monitoramento/{iid}/inversor")
    return json.loads(p[-1]) if p else None

d11, d12, dfc = ultimo("u11"), ultimo("u12"), ultimo("fc1")
ok(d11 and d11["corrente_a"] > 10, "PowerFlex drive 0 publicando", f"-> {d11 and d11['corrente_a']}")
ok(d12 and abs(d12["corrente_a"] - 7.8) < 0.5 and d12["frequencia_hz"] == 40.0,
   "PowerFlex drive 1 (encadeado) com os PROPRIOS valores", f"-> {d12 and d12['corrente_a']}")
ok(dfc and dfc["frequencia_hz"] == 45.6 and "rpm" in dfc,
   "Danfoss FC 302 publicando, com rpm", f"-> {dfc and dfc.get('frequencia_hz')}")
ok(d12 and d12["origem"] == {"modelo": "pf525", "nome": "Exaustor 2", "tag": "U12",
                             "no": "127.0.0.1", "drive": 1},
   "origem do PowerFlex traz modelo e posicao", f"-> {d12 and d12['origem']}")
ok(dfc and dfc["origem"].get("modelo") == "danfoss_fc302" and dfc["origem"].get("endereco") == 1,
   "origem do Danfoss traz modelo e endereco", f"-> {dfc and dfc['origem']}")
est = json.loads(cli.de(srv.TOPICO_ESTADO)[-1])
ok(est["ativos"] == ["fc1", "u11", "u12"] and est["erros"][0]["id"] == "ruim",
   "estado publicado: o que foi aplicado e o que foi recusado",
   f"-> ativos={est['ativos']} erros={[e['id'] for e in est['erros']]}")
ok(not cli.de("monitoramento/ruim/inversor"), "o item invalido nao derruba os outros")

print("\n=== 3. A configuracao muda com o servico no ar ===")
n_antes = len(cli.de(srv.TOPICO_ESTADO))
gravar([u11, u12, u13])                         # sai o Danfoss, entra o drive 2
time.sleep(3)
ok(len(cli.de(srv.TOPICO_ESTADO)) > n_antes, "percebeu a mudanca sozinho, sem reiniciar")
ok(cli.de("monitoramento/u13/inversor"), "o drive que entrou passou a publicar")
ok("offline" in cli.de("monitoramento/fc1/status"),
   "o que saiu da lista vira 'offline' (nao fica 'online' retido)")
n_fc = len(cli.de("monitoramento/fc1/inversor"))
time.sleep(1)
ok(len(cli.de("monitoramento/fc1/inversor")) == n_fc, "e para de ser lido")

print("\n=== 4. Arquivo corrompido no meio da escrita ===")
arq.write_text('{"inversores": [ {"id": "u11", ', encoding="utf-8")
time.sleep(1.5)
n = len(cli.de("monitoramento/u11/inversor"))
time.sleep(1)
ok(len(cli.de("monitoramento/u11/inversor")) > n,
   "mantem a configuracao anterior rodando")
est = json.loads(cli.de(srv.TOPICO_ESTADO)[-1])
ok(est.get("ok") is False and "ilegivel" in est.get("erro_arquivo", "").replace("í", "i"),
   "e avisa o painel que o arquivo esta ilegivel", f"-> {est.get('erro_arquivo')}")
parar.set(); t.join(10)
ok(("monitoramento/u11/status", "offline", True) in cli.msgs,
   "ao parar o servico, os inversores viram 'offline'")

print("\n=== 5. Gateway recem-instalado, sem arquivo ===")
cli2 = CliFalso()
s2 = srv.Servico(pasta / "nao_existe.json", srv.Publicador(cli2), CAT)
p2 = threading.Event()
t2 = threading.Thread(target=s2.rodar, args=(p2,), daemon=True)
t2.start(); time.sleep(2); p2.set(); t2.join(5)
n = len(cli2.de(srv.TOPICO_ESTADO))
ok(n == 1, "aplica a lista vazia UMA vez, e nao a cada releitura", f"-> {n} vezes")

print(f"\nRESULTADO: {'todas as verificacoes passaram.' if not falhas else f'{falhas} falha(s).'}")
sys.exit(1 if falhas else 0)
