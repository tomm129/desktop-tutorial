"""Testa o sidecar do PowerFlex 525 contra um drive SIMULADO, por EtherNet/IP.

Nao existe um simulador CIP pronto tao simples quanto o servidor do
pymodbus, entao este arquivo traz um: um servidor EtherNet/IP minimo que
responde ao que o pycomm3 realmente manda -- RegisterSession, SendRRData com
Get_Attribute_Single, e o envelope Unconnected Send (0x52).

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
import socket
import struct
import sys
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


import logging
try:
    import pycomm3
    logging.getLogger('pycomm3').setLevel(logging.WARNING)
except ImportError:
    sys.exit("PULADO: falta o pycomm3 (pip install pycomm3)")


# =====================================================================
#  Drive simulado
# =====================================================================
SERVICO_GET_ATTR = 0x0E
SERVICO_UCMM_SEND = 0x52
ST_OK, ST_CAMINHO, ST_SERVICO, ST_ATRIBUTO, ST_OBJETO = 0x00, 0x05, 0x08, 0x14, 0x16


class DrivePF525:
    def __init__(self, params, trip=0, aceita_ucmm_send=True, tem_obj_falha=True):
        self.params = params            # {instancia: valor bruto INT}
        self.trip = trip                # Fault Trip Instance (0 = sem falha)
        self.aceita_ucmm_send = aceita_ucmm_send
        self.tem_obj_falha = tem_obj_falha
        self.pedidos = []               # (servico, classe, inst, atrib, via_0x52)

    # ---- CIP -------------------------------------------------------
    @staticmethod
    def _caminho(p):
        """EPATH -> (classe, instancia, atributo). Segmentos 8 e 16 bits."""
        classe = inst = atrib = None
        i = 0
        while i < len(p):
            seg = p[i]
            if seg in (0x20, 0x24, 0x30):
                v = p[i + 1]; i += 2
            elif seg in (0x21, 0x25, 0x31):
                v = struct.unpack_from("<H", p, i + 2)[0]; i += 4
            else:
                return None
            if seg in (0x20, 0x21):
                classe = v
            elif seg in (0x24, 0x25):
                inst = v
            else:
                atrib = v
        return classe, inst, atrib

    @staticmethod
    def _resposta(servico, status, dados=b""):
        return bytes([servico | 0x80, 0, status, 0]) + dados

    def atender(self, mr, via_0x52=False):
        servico, palavras = mr[0], mr[1]
        caminho = mr[2:2 + 2 * palavras]
        corpo = mr[2 + 2 * palavras:]

        if servico == SERVICO_UCMM_SEND:
            if not self.aceita_ucmm_send:
                return self._resposta(servico, ST_SERVICO)
            tam = struct.unpack_from("<H", corpo, 2)[0]
            return self.atender(corpo[4:4 + tam], via_0x52=True)

        if servico != SERVICO_GET_ATTR:
            return self._resposta(servico, ST_SERVICO)
        cia = self._caminho(caminho)
        if cia is None:
            return self._resposta(servico, ST_CAMINHO)
        classe, inst, atrib = cia
        self.pedidos.append((servico, classe, inst, atrib, via_0x52))

        if classe in (0x0F, 0x93):
            valor_no = 1 if classe == 0x0F else 9
            if inst not in self.params:
                return self._resposta(servico, ST_OBJETO)
            if atrib != valor_no:
                # Atributo existe mas NAO e o valor (na 0x93, o 1 e a senha
                # de protecao). Devolve outra coisa, como o drive faria.
                return self._resposta(servico, ST_OK, struct.pack("<H", 0))
            return self._resposta(servico, ST_OK,
                                  struct.pack("<h", self.params[inst]))
        if classe == 0x97 and self.tem_obj_falha:
            if inst == 0 and atrib == 4:
                return self._resposta(servico, ST_OK, struct.pack("<H", self.trip))
            return self._resposta(servico, ST_ATRIBUTO)
        return self._resposta(servico, ST_OBJETO)

    # ---- encapsulamento EtherNet/IP -----------------------------------
    def conversar(self, sock):
        sessao = 0x1234ABCD
        while True:
            cab = self._receber(sock, 24)
            if not cab:
                return
            cmd, tam, _sess, _st, ctx, _op = struct.unpack("<HHII8sI", cab)
            dados = self._receber(sock, tam) if tam else b""
            if cmd == 0x65:                       # RegisterSession
                sock.sendall(struct.pack("<HHII8sI", 0x65, 4, sessao, 0, ctx, 0)
                             + dados[:4])
            elif cmd == 0x66:                     # UnRegisterSession
                return
            elif cmd == 0x6F:                     # SendRRData
                # interface(4) timeout(2) contagem(2) + itens
                i = 8
                mr = b""
                for _ in range(struct.unpack_from("<H", dados, 6)[0]):
                    tipo, n = struct.unpack_from("<HH", dados, i)
                    if tipo == 0x00B2:
                        mr = dados[i + 4:i + 4 + n]
                    i += 4 + n
                resp = self.atender(mr)
                cpf = (struct.pack("<IHH", 0, 0, 2) + struct.pack("<HH", 0, 0)
                       + struct.pack("<HH", 0x00B2, len(resp)) + resp)
                sock.sendall(struct.pack("<HHII8sI", 0x6F, len(cpf), sessao, 0,
                                         ctx, 0) + cpf)
            else:                                 # comando nao suportado
                sock.sendall(struct.pack("<HHII8sI", cmd, 0, sessao, 1, ctx, 0))

    @staticmethod
    def _receber(sock, n):
        buf = b""
        while len(buf) < n:
            parte = sock.recv(n - len(buf))
            if not parte:
                return b""
            buf += parte
        return buf

    def subir(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        self.porta = srv.getsockname()[1]

        def laco():
            while True:
                try:
                    c, _ = srv.accept()
                except OSError:
                    return
                threading.Thread(target=self.conversar, args=(c,), daemon=True).start()
        threading.Thread(target=laco, daemon=True).start()
        return self


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
