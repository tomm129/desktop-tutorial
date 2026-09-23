#!/usr/bin/env python3
"""PowerFlex 525 SIMULADO — um drive falso que fala EtherNet/IP de verdade.

Serve para exercitar o sidecar (integracoes/powerflex525) e o painel sem
inversor nenhum. Responde ao que o pycomm3 realmente manda: RegisterSession,
SendRRData com Get_Attribute_Single e o envelope Unconnected Send (0x52).

    python tools/simuladores/drive_powerflex.py            # abre o painel web
    python tools/simuladores/drive_powerflex.py --sem-web  # só o drive

O painel de controle abre em http://localhost:8525/ — dá para trocar de
cenário, disparar falha, mexer em frequência e carga e ver, pedido a pedido,
o que o sidecar está lendo.

Manual completo: tools/simuladores/README.md

O que ele reproduz, e de onde veio (conferido nos manuais da Rockwell):
  * Parameter Object 0x0F: instância = nº do parâmetro, valor no atributo 1
  * DPI Parameter Object 0x93: mesma instância, valor no atributo 9
    (520COM-UM001, Apêndice C)
  * DPI Fault Object 0x97, atributo de classe 4 = Fault Trip Instance
  * b001 0,01 Hz · b003 0,01 A · b004 0,1 V · b005 1 V · b007 = falha MAIS
    RECENTE, que continua lá depois do rearme (520-UM001)

Não precisa de biblioteca nenhuma: socket, struct e http.server.

LIMITE: foi escrito a partir da MESMA leitura do manual que o sidecar. Prova
coerência e encanamento, não que o drive real se comporta assim.
"""
import argparse
import collections
import json
import math
import random
import socket
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SERVICO_GET_ATTR = 0x0E
SERVICO_UCMM_SEND = 0x52
ST_OK, ST_CAMINHO, ST_SERVICO, ST_ATRIBUTO, ST_OBJETO = 0x00, 0x05, 0x08, 0x14, 0x16
NOME_STATUS = {ST_OK: "ok", ST_CAMINHO: "caminho inválido",
               ST_SERVICO: "serviço recusado", ST_ATRIBUTO: "atributo inexistente",
               ST_OBJETO: "objeto inexistente"}

# Estados prontos. Valores BRUTOS, na forma que o drive transmite.
CENARIOS = {
    # motor a 45,6 Hz, 12,34 A, barramento 537 V; sem falha nenhuma. A tensao
    # de saida segue a relacao V/f: 380 V em 60 Hz -> ~289 V em 45,6 Hz.
    "normal":       dict(params={1: 4560, 3: 1234, 4: 2888, 5: 537, 6: 0b00011, 7: 0},
                         trip=0),
    # igual ao normal, mas com uma sobrecarga (F7) de ONTEM no b007, já
    # rearmada. O caso que a primeira versão do sidecar mostrava como
    # alarme eterno.
    "falha_antiga": dict(params={1: 4560, 3: 1234, 4: 2888, 5: 537, 6: 0b00011, 7: 7},
                         trip=0),
    # desarmado por falha de aterramento (F13): parado, sem corrente
    "falha":        dict(params={1: 0, 3: 0, 4: 0, 5: 541, 6: 0, 7: 13},
                         trip=1),
    # parado sem falha
    "parado":       dict(params={1: 0, 3: 0, 4: 0, 5: 541, 6: 0, 7: 0},
                         trip=0),
}

# Nomes de falha: a MESMA tabela do sidecar (uma fonte só). Se o sidecar não
# estiver ao lado, o painel mostra só o código.
def _tabela_falhas():
    try:
        import importlib.util
        arq = (Path(__file__).resolve().parents[2]
               / "integracoes" / "powerflex525" / "powerflex_mqtt.py")
        spec = importlib.util.spec_from_file_location("_pf_falhas", arq)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return dict(mod.FALHAS)
    except (Exception, SystemExit):     # o sidecar sai com sys.exit se a config for invalida
        return {}


class DrivePF525:
    """O drive. Usado à mão (CLI e painel web) e pelos testes automáticos."""

    def __init__(self, params, trip=0, aceita_ucmm_send=True, tem_obj_falha=True):
        self.params = dict(params)      # {instância: valor bruto} -- o que é lido
        self.base = dict(params)        # valores "de repouso" em volta dos quais oscila
        self.trip = trip                # Fault Trip Instance (0 = sem falha)
        self.aceita_ucmm_send = aceita_ucmm_send
        self.tem_obj_falha = tem_obj_falha
        self.cenario = None
        self.ciclo = 0.0                # s; 0 = não alterna sozinho
        # Últimos pedidos (serviço, classe, inst, atrib, via_0x52): os testes
        # conferem o que o sidecar pediu. Limitado, porque a ferramenta pode
        # ficar ligada dias -- uma lista crescia dezenas de MB por dia.
        self.pedidos = collections.deque(maxlen=5000)
        self.recentes = collections.deque(maxlen=40)    # para o painel web
        self.historico = collections.deque(maxlen=240)  # (t, corrente A)
        self.total = 0
        self._tempos = collections.deque(maxlen=4000)   # para a taxa
        self.inicio = time.time()
        self.trava = threading.Lock()

    # ---- CIP -------------------------------------------------------
    @staticmethod
    def _caminho(p):
        """EPATH -> (classe, instância, atributo). Segmentos de 8 e 16 bits."""
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

    def _anotar(self, classe, inst, atrib, via, status, valor=None):
        self.recentes.append(dict(t=time.time(), classe=classe, inst=inst,
                                  atrib=atrib, via=via, status=status, valor=valor))

    def atender(self, mr, via_0x52=False):
        servico, palavras = mr[0], mr[1]
        caminho = mr[2:2 + 2 * palavras]
        corpo = mr[2 + 2 * palavras:]

        if servico == SERVICO_UCMM_SEND:
            if not self.aceita_ucmm_send:
                self._anotar(None, None, None, True, ST_SERVICO)
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
        self.total += 1
        self._tempos.append(time.time())

        with self.trava:
            if classe in (0x0F, 0x93):
                valor_no = 1 if classe == 0x0F else 9
                if inst not in self.params:
                    self._anotar(classe, inst, atrib, via_0x52, ST_OBJETO)
                    return self._resposta(servico, ST_OBJETO)
                if atrib != valor_no:
                    # O atributo existe mas NÃO é o valor (na 0x93, o 1 é a
                    # senha de proteção). Devolve outra coisa, como o drive.
                    self._anotar(classe, inst, atrib, via_0x52, ST_OK, 0)
                    return self._resposta(servico, ST_OK, struct.pack("<H", 0))
                v = self.params[inst]
                self._anotar(classe, inst, atrib, via_0x52, ST_OK, v)
                return self._resposta(servico, ST_OK, struct.pack("<h", v))
            if classe == 0x97 and self.tem_obj_falha:
                if inst == 0 and atrib == 4:
                    self._anotar(classe, inst, atrib, via_0x52, ST_OK, self.trip)
                    return self._resposta(servico, ST_OK,
                                          struct.pack("<H", self.trip))
                self._anotar(classe, inst, atrib, via_0x52, ST_ATRIBUTO)
                return self._resposta(servico, ST_ATRIBUTO)
        self._anotar(classe, inst, atrib, via_0x52, ST_OBJETO)
        return self._resposta(servico, ST_OBJETO)

    # ---- encapsulamento EtherNet/IP -----------------------------------
    def conversar(self, sock):
        sessao = 0x1234ABCD
        try:
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
                    i, mr = 8, b""
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
                else:                                 # comando não suportado
                    sock.sendall(struct.pack("<HHII8sI", cmd, 0, sessao, 1, ctx, 0))
        except (ConnectionError, OSError):
            return
        finally:
            sock.close()

    @staticmethod
    def _receber(sock, n):
        buf = b""
        while len(buf) < n:
            parte = sock.recv(n - len(buf))
            if not parte:
                return b""
            buf += parte
        return buf

    def subir(self, host="127.0.0.1", porta=0):
        """Começa a atender em segundo plano. porta=0 escolhe uma livre."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, porta))
        srv.listen(4)
        self.porta = srv.getsockname()[1]
        self.host = host

        def laco():
            while True:
                try:
                    c, _ = srv.accept()
                except OSError:
                    return
                threading.Thread(target=self.conversar, args=(c,), daemon=True).start()
        threading.Thread(target=laco, daemon=True).start()
        return self

    # ---- controle (CLI e painel web) ----------------------------------
    def aplicar(self, cenario):
        c = CENARIOS[cenario]
        with self.trava:
            self.params = dict(c["params"])
            self.base = dict(c["params"])
            self.trip = c["trip"]
        self.cenario = cenario

    def disparar(self, codigo):
        """Desarma o drive com a falha escolhida: para, zera corrente, e o
        código vai para o b007 -- como no drive real."""
        with self.trava:
            for p in (1, 3, 4):
                self.base[p] = self.params[p] = 0
            self.base[6] = self.params[6] = 0
            self.base[7] = self.params[7] = int(codigo)
            self.trip = 1
        self.cenario = "falha"

    def rearmar(self):
        """Limpa a falha ativa. O b007 CONTINUA com o código -- é histórico."""
        with self.trava:
            self.trip = 0
        self.cenario = "parado" if not self.base.get(1) else "normal"

    def ajustar(self, freq_hz=None, corrente_a=None):
        """Muda o ponto de operação. Frequência > 0 põe o motor girando."""
        with self.trava:
            if freq_hz is not None:
                self.base[1] = int(round(float(freq_hz) * 100))
                girando = self.base[1] > 0
                self.base[6] = 0b00011 if girando else 0
                # tensão acompanha a frequência (V/f): 380 V em 60 Hz
                self.base[4] = int(round(3800 * min(float(freq_hz), 60) / 60))
            if corrente_a is not None:
                self.base[3] = int(round(float(corrente_a) * 100))
            if not self.base.get(1):
                self.base[3] = 0
            self.params.update(self.base)
        if self.trip == 0:
            self.cenario = "normal" if self.base.get(1) else "parado"

    def animar(self):
        """Laço 'ao vivo': corrente e tensão oscilam como num motor de
        verdade, e o painel mostra movimento em vez de uma linha reta."""
        t0 = ultimo_ciclo = time.time()
        while True:
            time.sleep(0.5)
            agora = time.time()
            if self.ciclo and agora - ultimo_ciclo >= self.ciclo:
                if self.trip:
                    self.aplicar("normal")
                else:
                    self.aplicar("falha")
                ultimo_ciclo = agora
            with self.trava:
                b = self.base
                if b.get(1) and not self.trip:
                    onda = math.sin((agora - t0) / 7.0)
                    self.params[3] = int(b[3] * (1 + 0.04 * onda) + random.randint(-8, 8))
                    self.params[4] = int(b[4] + random.randint(-15, 15))
                    self.params[5] = int(b[5] + random.randint(-2, 2))
                self.historico.append((agora, self.params.get(3, 0) / 100))

    def estado(self):
        with self.trava:
            p = dict(self.params)
            trip = self.trip
        return dict(
            cenario=self.cenario, trip=trip,
            freq_hz=p.get(1, 0) / 100, corrente_a=p.get(3, 0) / 100,
            tensao_v=p.get(4, 0) / 10, dc_bus_v=p.get(5, 0),
            status=p.get(6, 0), ultima_falha=p.get(7, 0),
            base_freq_hz=self.base.get(1, 0) / 100,
            base_corrente_a=self.base.get(3, 0) / 100,
            aceita_ucmm_send=self.aceita_ucmm_send,
            tem_obj_falha=self.tem_obj_falha, ciclo=self.ciclo,
            total=self.total, uptime=time.time() - self.inicio,
            # taxa medida AQUI, nos ultimos 5 s: calculada no navegador, entre
            # duas atualizacoes, a primeira tela sempre mostrava 0/s
            taxa=sum(1 for t in list(self._tempos) if t > time.time() - 5) / 5,
            endereco=f"{self.host}:{self.porta}",
            historico=[[round(t, 2), c] for t, c in self.historico],
            recentes=list(self.recentes)[-14:][::-1],
        )


# =====================================================================
#  Painel web
# =====================================================================
PAGINA = Path(__file__).with_name("painel_powerflex.html")


def servir_painel(drv, host, porta, falhas):
    class Tratador(BaseHTTPRequestHandler):
        def log_message(self, *a):        # sem uma linha por requisição
            pass

        def _json(self, obj, codigo=200):
            corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                corpo = PAGINA.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
            elif self.path == "/api/estado":
                self._json(drv.estado())
            elif self.path == "/api/falhas":
                self._json({str(k): v for k, v in sorted(falhas.items())})
            else:
                self._json({"erro": "nao existe"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                corpo = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"erro": "json invalido"}, 400)
            try:
                if self.path == "/api/cenario":
                    drv.aplicar(corpo["nome"])
                elif self.path == "/api/disparar":
                    drv.disparar(int(corpo["codigo"]))
                elif self.path == "/api/rearmar":
                    drv.rearmar()
                elif self.path == "/api/ajustar":
                    drv.ajustar(corpo.get("freq_hz"), corpo.get("corrente_a"))
                elif self.path == "/api/opcoes":
                    if "aceita_ucmm_send" in corpo:
                        drv.aceita_ucmm_send = bool(corpo["aceita_ucmm_send"])
                    if "tem_obj_falha" in corpo:
                        drv.tem_obj_falha = bool(corpo["tem_obj_falha"])
                    if "ciclo" in corpo:
                        drv.ciclo = max(0.0, float(corpo["ciclo"]))
                else:
                    return self._json({"erro": "nao existe"}, 404)
            except (KeyError, ValueError) as e:
                return self._json({"erro": str(e)}, 400)
            self._json(drv.estado())

    srv = ThreadingHTTPServer((host, porta), Tratador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# =====================================================================
#  Uso à mão
# =====================================================================
def main():
    ap = argparse.ArgumentParser(
        description="PowerFlex 525 simulado (EtherNet/IP). Manual: tools/simuladores/README.md")
    ap.add_argument("--host", default="0.0.0.0",
                    help="interface de escuta (padrão: todas)")
    ap.add_argument("--porta", type=int, default=44818,
                    help="porta EtherNet/IP (padrão 44818, a do drive real)")
    ap.add_argument("--web", type=int, default=8525,
                    help="porta do painel de controle (padrão 8525)")
    ap.add_argument("--sem-web", action="store_true", help="não abre o painel")
    ap.add_argument("--cenario", choices=sorted(CENARIOS), default="normal")
    ap.add_argument("--ciclo", type=float, default=0,
                    help="alterna normal <-> falha a cada N segundos (0 = não)")
    ap.add_argument("--recusa-ucmm", action="store_true",
                    help="recusa o envelope Unconnected Send (adaptador que não roteia)")
    ap.add_argument("--sem-objeto-falha", action="store_true",
                    help="não oferece o DPI Fault Object (0x97)")
    a = ap.parse_args()
    # Linha a linha mesmo com a saída redirecionada para arquivo ou pipe.
    sys.stdout.reconfigure(line_buffering=True)

    drv = DrivePF525({}, aceita_ucmm_send=not a.recusa_ucmm,
                     tem_obj_falha=not a.sem_objeto_falha)
    drv.aplicar(a.cenario)
    drv.ciclo = a.ciclo
    try:
        drv.subir(a.host, a.porta)
    except OSError as e:
        sys.exit(f"não consegui abrir a porta {a.porta}: {e}\n"
                 f"(outra coisa usando? tente --porta 44819 e PF525_PORTA=44819)")
    threading.Thread(target=drv.animar, daemon=True).start()

    print(f"PowerFlex 525 simulado em {a.host}:{drv.porta}  —  cenário '{a.cenario}'")
    if not a.sem_web:
        try:
            servir_painel(drv, a.host, a.web, _tabela_falhas())
            print(f"  painel de controle:  http://localhost:{a.web}/")
        except OSError as e:
            print(f"  (painel web não abriu na porta {a.web}: {e} -- use --web outra)")
    print("  Ctrl-C encerra.\n")

    avisado = 0
    try:
        while True:
            time.sleep(1)
            if drv.total // 100 > avisado:
                avisado = drv.total // 100
                print(f"  {drv.total} leituras atendidas")
    except KeyboardInterrupt:
        print("\nencerrado.")


if __name__ == "__main__":
    main()
