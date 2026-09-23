#!/usr/bin/env python3
"""Danfoss VLT SIMULADO (FC 51 / FC 301 / FC 302) — Modbus TCP de verdade.

Serve para exercitar o sidecar (integracoes/danfoss_vlt) e o painel sem
inversor nenhum. É um servidor Modbus TCP com os registradores nos
endereços que o manual da Danfoss define.

    python tools/simuladores/drive_danfoss.py                     # FC 302 rodando
    python tools/simuladores/drive_danfoss.py --familia fc51      # sem 16-16/16-17
    python tools/simuladores/drive_danfoss.py --cenario falha     # dois alarmes
    python tools/simuladores/drive_danfoss.py --ciclo 30          # alterna a cada 30 s

Manual completo: tools/simuladores/README.md

O que ele reproduz, e de onde veio:
  * endereço = (PNU × 10) − 1                    (FC 51 Design Guide, §8.9.1)
  * cada parâmetro existe SÓ nos registradores do seu tipo: 1 para 16 bits,
    2 para 32. Pedir registrador a mais dá a exceção 02 (endereço
    inválido), como no drive real.
  * tipos e escalas da lista de parâmetros do FC 301/302 Programming Guide
  * palavra de alarme 16-90 com o mapa de bits da tabela "Alarm Word"
  * responde só ao endereço de escravo configurado (8-31); pedido para
    outro endereço fica sem resposta e o cliente dá timeout -- o sintoma
    real de DANFOSS_UNIT errado.

Por que um servidor próprio, e não o do pymodbus: a primeira versão usava o
datastore do pymodbus, e a 3.15 tirou dele a escrita com o servidor no ar
(o modo "ao vivo" quebrou com AttributeError); a 4.0 vai trocar a API de
novo. Modbus TCP com a função 03 cabe em umas 40 linhas, não depende de
nada e o comportamento de erro fica sob controle.

Só Modbus TCP: para o sidecar ler daqui, use DANFOSS_TRANSPORTE=tcp. O drive
de bancada real (FC 51) fala RTU pela RS-485 -- o protocolo acima da camada
física é o mesmo.

LIMITE: foi escrito a partir da MESMA leitura do manual que o sidecar. Prova
coerência e encanamento, não que o drive real se comporta assim.
"""
import argparse
import collections
import math
import random
import socket
import struct
import sys
import threading
import time

FC_LER_HOLDING = 0x03
EXC_FUNCAO, EXC_ENDERECO, EXC_VALOR = 0x01, 0x02, 0x03


def u32(v):
    v &= 0xFFFFFFFF
    return [v >> 16, v & 0xFFFF]


def u16(v):
    return [v & 0xFFFF]


# Palavra de alarme 16-90 (bits, NÃO números de alarme):
BIT_SOBRECORRENTE = 1 << 5      # A13
BIT_FREIO_MEC = 1 << 31         # A63


def estado(freq_dhz, corrente_ca, tensao_dv, dc_v, pot_ckw, termico,
           dissip, status, alarme, rpm, torque_dnm):
    """Monta o mapa PNU -> palavras, com a largura de cada tipo."""
    return {
        1613: u16(freq_dhz),        # 0,1 Hz   Uint16
        1614: u32(corrente_ca),     # 0,01 A   Int32
        1612: u16(tensao_dv),       # 0,1 V    Uint16
        1630: u16(dc_v),            # 1 V      Uint16
        1610: u32(pot_ckw),         # 0,01 kW  Int32
        1618: u16(termico),         # %        Uint8
        1634: u16(dissip),          # °C       Uint8
        1603: u16(status),          # V2
        1690: u32(alarme),          # Uint32
        1617: u32(rpm),             # rpm      Int32  (só FC 301/302)
        1616: u16(torque_dnm),      # 0,1 Nm   Int16  (só FC 301/302)
    }


CENARIOS = {
    # 45,6 Hz, 12,34 A, 5,5 kW, 1480 rpm, 36 Nm. Tensão pela relação V/f:
    # 380 V em 50 Hz (base europeia da Danfoss) -> ~347 V em 45,6 Hz.
    "normal": dict(freq_dhz=456, corrente_ca=1234, tensao_dv=3466, dc_v=537,
                   pot_ckw=550, termico=42, dissip=38, status=0x0F07,
                   alarme=0, rpm=1480, torque_dnm=360),
    # frenando: torque NEGATIVO -- o caso que a leitura como 32 bits quebrava
    "frenando": dict(freq_dhz=300, corrente_ca=820, tensao_dv=2280, dc_v=598,
                     pot_ckw=-120, termico=40, dissip=39, status=0x0F07,
                     alarme=0, rpm=880, torque_dnm=-50),
    # desarmado com DOIS alarmes: sobrecorrente e freio mecânico (bit 31,
    # que não pode virar número negativo)
    "falha": dict(freq_dhz=0, corrente_ca=0, tensao_dv=0, dc_v=541, pot_ckw=0,
                  termico=55, dissip=41, status=0x0208,
                  alarme=BIT_SOBRECORRENTE | BIT_FREIO_MEC, rpm=0, torque_dnm=0),
    "parado": dict(freq_dhz=0, corrente_ca=0, tensao_dv=0, dc_v=541, pot_ckw=0,
                   termico=30, dissip=31, status=0x0603, alarme=0, rpm=0,
                   torque_dnm=0),
}


class DriveDanfoss:
    """O drive. Usado à mão (CLI abaixo) e pelos testes automáticos."""

    def __init__(self, cenario="normal", familia="fc302", regs=None, unidade=1):
        self.familia = familia
        self.unidade = unidade
        self.registros = {}                 # endereço Modbus -> palavra
        self.trava = threading.Lock()
        self.pedidos = collections.deque(maxlen=5000)   # (unidade, endereço, qtd, ok)
        self.total = 0
        self.cenario = cenario
        mapa = regs if regs is not None else self._mapa(cenario)
        for pnu, palavras in mapa.items():
            self.escrever(pnu, palavras)

    def _mapa(self, cenario):
        m = estado(**CENARIOS[cenario])
        if self.familia == "fc51":          # o FC 51 não tem 16-16 nem 16-17
            m.pop(1616), m.pop(1617)
        return m

    def escrever(self, pnu, palavras):
        with self.trava:
            for i, w in enumerate(palavras):
                self.registros[pnu * 10 - 1 + i] = w & 0xFFFF

    def aplicar(self, cenario):
        for pnu, palavras in self._mapa(cenario).items():
            self.escrever(pnu, palavras)
        self.cenario = cenario

    # ---- Modbus ------------------------------------------------------
    def atender(self, unidade, pdu):
        """PDU de pedido -> PDU de resposta, ou None (não responde)."""
        if unidade != self.unidade:
            return None                     # outro escravo: silêncio, como na RS-485
        fc = pdu[0]
        if fc != FC_LER_HOLDING:
            return bytes([fc | 0x80, EXC_FUNCAO])
        if len(pdu) < 5:
            return bytes([fc | 0x80, EXC_VALOR])
        inicio, qtd = struct.unpack(">HH", pdu[1:5])
        if not 1 <= qtd <= 125:
            return bytes([fc | 0x80, EXC_VALOR])
        with self.trava:
            enderecos = range(inicio, inicio + qtd)
            ok = all(e in self.registros for e in enderecos)
            self.pedidos.append((unidade, inicio, qtd, ok))
            self.total += 1
            if not ok:
                return bytes([fc | 0x80, EXC_ENDERECO])
            palavras = [self.registros[e] for e in enderecos]
        return bytes([fc, 2 * qtd]) + struct.pack(f">{qtd}H", *palavras)

    def conversar(self, sock):
        try:
            while True:
                cab = self._receber(sock, 7)            # MBAP
                if not cab:
                    return
                transacao, protocolo, tam, unidade = struct.unpack(">HHHB", cab)
                pdu = self._receber(sock, tam - 1)
                if not pdu or protocolo != 0:
                    return
                resp = self.atender(unidade, pdu)
                if resp is None:
                    continue
                sock.sendall(struct.pack(">HHHB", transacao, 0, len(resp) + 1, unidade)
                             + resp)
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

    def subir(self, host="127.0.0.1", porta=5020):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, porta))
        srv.listen(4)
        self.porta = srv.getsockname()[1]
        self._srv = srv

        def laco():
            while True:
                try:
                    c, _ = srv.accept()
                except OSError:
                    return
                threading.Thread(target=self.conversar, args=(c,), daemon=True).start()
        threading.Thread(target=laco, daemon=True).start()
        return self


def main():
    ap = argparse.ArgumentParser(
        description="Danfoss VLT simulado (Modbus TCP). Manual: tools/simuladores/README.md")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--porta", type=int, default=5020,
                    help="porta Modbus TCP (padrão 5020; a 502 exige privilégio no Linux)")
    ap.add_argument("--unidade", type=int, default=1,
                    help="endereço do escravo, como o par. 8-31 (padrão 1)")
    ap.add_argument("--familia", choices=("fc302", "fc301", "fc51"), default="fc302")
    ap.add_argument("--cenario", choices=sorted(CENARIOS), default="normal")
    ap.add_argument("--ciclo", type=float, default=0,
                    help="alterna normal <-> falha a cada N segundos (0 = não)")
    a = ap.parse_args()
    # Linha a linha mesmo com a saída redirecionada para arquivo ou pipe.
    sys.stdout.reconfigure(line_buffering=True)

    familia = "fc302" if a.familia == "fc301" else a.familia
    drv = DriveDanfoss(a.cenario, familia, unidade=a.unidade)
    try:
        drv.subir(a.host, a.porta)
    except OSError as e:
        sys.exit(f"não consegui abrir a porta {a.porta}: {e}")
    print(f"Danfoss {a.familia.upper()} simulado em {a.host}:{drv.porta} (Modbus TCP, "
          f"unidade {a.unidade})  —  cenário '{a.cenario}'")
    if familia == "fc51":
        print("  sem 16-16 Torque e 16-17 Speed, como o FC 51 real")
    if a.ciclo:
        print(f"  alternando normal <-> falha a cada {a.ciclo:g} s")
    print("  Ctrl-C encerra.\n")

    t0 = ultimo = time.time()
    avisado = 0
    try:
        while True:
            time.sleep(0.5)
            agora = time.time()
            if a.ciclo and agora - ultimo >= a.ciclo:
                drv.aplicar("falha" if drv.cenario != "falha" else "normal")
                ultimo = agora
                print(f"  [{time.strftime('%H:%M:%S')}] cenário -> {drv.cenario}")
            c = CENARIOS[drv.cenario]
            if c["freq_dhz"]:
                # corrente e tensão oscilam, como num motor de verdade
                onda = math.sin((agora - t0) / 7.0)
                drv.escrever(1614, u32(int(c["corrente_ca"] * (1 + 0.04 * onda)
                                           + random.randint(-8, 8))))
                drv.escrever(1612, u16(c["tensao_dv"] + random.randint(-15, 15)))
            if drv.total // 100 > avisado:
                avisado = drv.total // 100
                erros = sum(1 for p in drv.pedidos if not p[3])
                print(f"  {drv.total} leituras atendidas"
                      + (f" ({erros} com endereço inválido)" if erros else ""))
    except KeyboardInterrupt:
        print("\nencerrado.")


if __name__ == "__main__":
    main()
