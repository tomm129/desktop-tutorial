#!/usr/bin/env python3
"""Serviço de inversores do InsightX — um só, para todas as marcas.

Lê a lista de inversores que o PAINEL escreve (menu Inversores) e mantém a
leitura de cada um, publicando no mesmo contrato MQTT de sempre:

    monitoramento/<id>/inversor     telemetria
    monitoramento/<id>/status       online / offline

Substitui os dois sidecars avulsos (powerflex525, danfoss_vlt), que
continuam existindo como DRIVERS: a conversa com cada marca, já conferida
contra os manuais e testada contra os simuladores, é a deles.

    python servico_inversores.py                 # serviço
    python servico_inversores.py --validar       # só confere o arquivo e sai

O arquivo é relido sozinho quando muda — cadastrar um inversor no painel
não exige reiniciar nada. Um item inválido é ignorado e reportado; nunca
derruba o serviço nem os outros inversores.

Garantia de projeto: este serviço só LÊ. Nenhum caminho de código escreve
parâmetro, dá partida ou muda referência num drive.

Configuração (variáveis de ambiente, preenchidas pelo setup_orangepi.sh):
    INVERSORES_ARQ   caminho da lista (padrão /opt/iot/dados/inversores.json)
    MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS
"""
import importlib.util
import ipaddress
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ_INTEG = AQUI.parent

ARQ_PADRAO = os.getenv("INVERSORES_ARQ", "/opt/iot/dados/inversores.json")
TOPICO_ESTADO = "insightx/gateway/inversores/estado"
RELEITURA_S = 2.0

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("inversores")


def carregar_catalogo(arq=AQUI / "catalogo.json"):
    with open(arq, encoding="utf-8") as f:
        return json.load(f)


def _carregar_driver(nome, arquivo):
    spec = importlib.util.spec_from_file_location(nome, arquivo)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Os drivers são carregados sob demanda: sem inversor Danfoss cadastrado, o
# pymodbus nem precisa estar instalado, e vice-versa.
_drivers = {}


def driver(nome):
    if nome not in _drivers:
        arq = {"powerflex": RAIZ_INTEG / "powerflex525" / "powerflex_mqtt.py",
               "danfoss": RAIZ_INTEG / "danfoss_vlt" / "danfoss_mqtt.py"}[nome]
        _drivers[nome] = _carregar_driver(f"driver_{nome}", arq)
    return _drivers[nome]


# =====================================================================
#  Validação
# =====================================================================
def _ip_valido(v):
    try:
        ipaddress.IPv4Address(str(v))
        return True
    except (ValueError, TypeError):
        return False


def _inteiro(v, mn, mx):
    return isinstance(v, int) and not isinstance(v, bool) and mn <= v <= mx


def validar(config, catalogo):
    """Confere a lista contra o catálogo e contra ela mesma.

    Devolve (validos, erros). 'erros' é uma lista de {id, erro}: o painel a
    mostra junto do inversor, para o erro aparecer onde foi cometido.

    Além do formato de cada item, pega os conflitos entre itens que o painel
    não teria como denunciar sozinho: mesmo id duas vezes, mesmo drive
    declarado duas vezes, mesmo endereço no mesmo barramento RS-485, e
    drives do mesmo barramento com baud ou paridade diferentes -- esse
    último é traiçoeiro, porque aparece como "às vezes funciona".
    """
    modelos = catalogo["modelos"]
    itens = (config or {}).get("inversores") or []
    validos, erros = [], []
    ids, posicoes, barramentos = set(), {}, {}

    for n, it in enumerate(itens, 1):
        iid = str((it or {}).get("id") or f"item {n}")

        def erro(msg):
            erros.append({"id": iid, "erro": msg})

        if not isinstance(it, dict) or not it.get("id"):
            erro("sem id")
            continue
        if it.get("habilitado") is False:
            continue                      # desligado no painel: não lê
        if iid in ids:
            erro("id repetido")
            continue
        m = modelos.get(it.get("modelo"))
        if not m:
            erro(f"modelo desconhecido: {it.get('modelo')!r}")
            continue
        c = it.get("conexao") or {}
        tipo = c.get("tipo")
        if tipo not in m["conexoes"]:
            erro(f"{m['nome']} não se conecta por {tipo!r} "
                 f"(aceita: {', '.join(m['conexoes'])})")
            continue

        if tipo == "cip":
            pos = c.get("posicao", 0)
            if not _ip_valido(c.get("ip")):
                erro(f"IP inválido: {c.get('ip')!r}"); continue
            if not _inteiro(pos, 0, 4):
                erro(f"posição no nó tem de ser 0 a 4, veio {pos!r}"); continue
            if pos and not m.get("multidrive"):
                erro(f"{m['nome']} não tem Multi-Drive: posição tem de ser 0"); continue
            chave = ("cip", c["ip"], int(c.get("porta", 44818)), pos)
            desc = f"{c['ip']} posição {pos}"
        elif tipo == "tcp":
            if not _ip_valido(c.get("ip")):
                erro(f"IP inválido: {c.get('ip')!r}"); continue
            if not _inteiro(c.get("porta", 502), 1, 65535):
                erro("porta TCP inválida"); continue
            if not _inteiro(c.get("endereco", 1), 1, 247):
                erro("endereço de escravo tem de ser 1 a 247"); continue
            chave = ("tcp", c["ip"], c.get("porta", 502), c.get("endereco", 1))
            desc = f"{c['ip']} endereço {c.get('endereco', 1)}"
        else:  # rtu
            ps = str(c.get("porta_serial") or "").strip()
            if not ps:
                erro("porta serial vazia"); continue
            if not _inteiro(c.get("endereco"), 1, 247):
                erro("endereço de escravo tem de ser 1 a 247"); continue
            if c.get("baud", 9600) not in (9600, 19200, 38400):
                erro("velocidade tem de ser 9600, 19200 ou 38400"); continue
            if c.get("paridade", "E") not in ("E", "O", "N"):
                erro("paridade tem de ser E, O ou N"); continue
            ajuste = (c.get("baud", 9600), c.get("paridade", "E"))
            if ps in barramentos and barramentos[ps][0] != ajuste:
                outro = barramentos[ps][1]
                erro(f"{ps} já está em {barramentos[ps][0][0]} {barramentos[ps][0][1]} "
                     f"(por causa de {outro}); todos os drives de um barramento "
                     f"têm de usar a mesma velocidade e paridade"); continue
            chave = ("rtu", ps, c["endereco"])
            desc = f"{ps} endereço {c['endereco']}"

        if chave in posicoes:
            erro(f"{desc} já é usado por {posicoes[chave]}")
            continue
        if tipo == "rtu":
            barramentos.setdefault(ps, (ajuste, iid))
        ids.add(iid)
        posicoes[chave] = iid
        validos.append(it)
    return validos, erros


# =====================================================================
#  Leitura
# =====================================================================
class Dispositivo:
    """Estado de leitura de um inversor configurado."""

    def __init__(self, it, modelo):
        self.id = it["id"]
        self.item = it
        self.modelo = modelo
        self.conexao = it["conexao"]
        self.nome = (it.get("nome") or "").strip()
        self.tag = (it.get("tag") or "").strip()
        pos = self.conexao.get("posicao", 0)
        padrao = 1.0 if (self.conexao["tipo"] != "cip" or not pos) else 5.0
        self.intervalo_s = float(it.get("intervalo_s") or padrao)
        self.proxima = 0.0
        self.online = None
        self.falha_anterior = None
        self.indisponiveis = set()     # Danfoss: parâmetros que este drive não tem

    @property
    def topic_inversor(self):
        return f"monitoramento/{self.id}/inversor"

    @property
    def topic_status(self):
        return f"monitoramento/{self.id}/status"


def chave_grupo(d):
    """Dispositivos que dividem uma conexão -- lidos em sequência, nunca em
    paralelo: um nó EtherNet/IP, um IP Modbus TCP, um barramento RS-485."""
    c = d.conexao
    if c["tipo"] == "cip":
        return ("cip", c["ip"], int(c.get("porta", 44818)))
    if c["tipo"] == "tcp":
        return ("tcp", c["ip"], int(c.get("porta", 502)))
    return ("rtu", c["porta_serial"], c.get("baud", 9600), c.get("paridade", "E"))


class Publicador:
    """Tudo que sai para o MQTT passa por aqui (e é trocado nos testes)."""

    def __init__(self, cli):
        self.cli = cli

    def status(self, d, online, erro=None):
        if d.online == online:
            return
        d.online = online
        self.cli.publish(d.topic_status, "online" if online else "offline",
                         qos=1, retain=True)
        if online:
            log.info("%s respondendo", d.id)
        else:
            log.warning("%s sem resposta%s", d.id, f" ({erro})" if erro else "")

    def dados(self, d, dados):
        self.cli.publish(d.topic_inversor, json.dumps(dados), qos=0)
        self.status(d, True)
        cod = (dados.get("falha") or {}).get("codigo")
        if cod != d.falha_anterior:
            if cod:
                log.warning("%s FALHA %s: %s", d.id, cod, dados["falha"].get("texto"))
            elif d.falha_anterior:
                log.info("%s falha anterior sanada", d.id)
            d.falha_anterior = cod

    def estado(self, resumo):
        self.cli.publish(TOPICO_ESTADO, json.dumps(resumo), qos=1, retain=True)


def _origem(d):
    c = d.conexao
    o = {"modelo": d.item["modelo"], "nome": d.nome, "tag": d.tag}
    if c["tipo"] == "rtu":
        o.update(barramento=c["porta_serial"], endereco=c["endereco"])
    else:
        o["no"] = c["ip"]
        if c["tipo"] == "cip":
            o["drive"] = c.get("posicao", 0)
        else:
            o["endereco"] = c.get("endereco", 1)
    return o


def _laco_grupo(chave, disps, pub, parar, abrir, ler, fechar):
    """Laço genérico de um grupo: abre a conexão, lê cada dispositivo no seu
    intervalo, isola falhas individuais, reconecta se o grupo inteiro cai."""
    while not parar.is_set():
        conn = None
        try:
            conn = abrir()
            log.info("conectado: %s (%s)", chave[1], ", ".join(d.id for d in disps))
            falhas = 0
            while not parar.is_set():
                agora = time.monotonic()
                for d in disps:
                    if agora < d.proxima:
                        continue
                    d.proxima = agora + d.intervalo_s
                    try:
                        dados = ler(conn, d)
                    except Exception as e:
                        pub.status(d, False, e)
                        falhas += 1
                        if falhas >= len(disps) or getattr(e, "derruba_grupo", False):
                            raise
                        continue
                    falhas = 0
                    dados["origem"] = _origem(d)
                    pub.dados(d, dados)
                espera = min(d.proxima for d in disps) - time.monotonic()
                parar.wait(max(0.05, espera))
        except Exception as e:
            log.warning("%s: %s. Reconectando em 5 s...", chave[1], e)
            for d in disps:
                pub.status(d, False, e)
                d.proxima = 0.0
            parar.wait(5)
        finally:
            if conn is not None:
                try:
                    fechar(conn)
                except Exception:
                    pass


def rodar_grupo(chave, disps, pub, parar):
    tipo = chave[0]
    if tipo == "cip":
        pf = driver("powerflex")
        # Estado do driver por drive (modo de envio por nó, objeto de falha).
        invs = {d.id: pf.Inversor(d.id, chave[1], d.conexao.get("posicao", 0), chave[2],
                                  d.intervalo_s, d.nome, d.tag, d.item["modelo"])
                for d in disps}

        def abrir():
            c = pf.abrir_drive(chave[1], chave[2]); c.open(); return c

        def ler(conn, d):
            try:
                return pf.ler_inversor(conn, invs[d.id])
            except Exception as e:
                # o drive 0 é o adaptador do nó: se ele não responde, a
                # sessão é que está ruim
                if d.conexao.get("posicao", 0) == 0:
                    e.derruba_grupo = True
                raise

        def fechar(conn):
            pf._modo_ucmm.pop(chave[1], None)
            for i in invs.values():
                i.sem_objeto_falha = False
            conn.close()

        _laco_grupo(chave, disps, pub, parar, abrir, ler, fechar)
        return

    df = driver("danfoss")
    familia = {d.id: d.modelo.get("familia") for d in disps}
    if tipo == "tcp":
        abrir = lambda: df.abrir_cliente("tcp", ip=chave[1], porta=chave[2])
    else:
        abrir = lambda: df.abrir_cliente("rtu", serial=chave[1], baud=chave[2],
                                         paridade=chave[3])

    def ler(conn, d):
        return df.ler_inversor(conn, familia[d.id], d.conexao.get("endereco", 1),
                               d.indisponiveis)

    _laco_grupo(chave, disps, pub, parar, abrir, ler, lambda c: c.close())


# =====================================================================
#  O serviço
# =====================================================================
class Servico:
    def __init__(self, arquivo, pub, catalogo=None):
        self.arquivo = Path(arquivo)
        self.pub = pub
        self.catalogo = catalogo or carregar_catalogo()
        self._assinatura = None
        self._aplicado = False         # distingue "nunca aplicou" de "arquivo não existe"
        self._fios = []
        self._parar_grupos = None
        self.disps = {}

    def _ler_arquivo(self):
        if not self.arquivo.exists():
            return {"inversores": []}, None
        try:
            return json.loads(self.arquivo.read_text(encoding="utf-8")), None
        except (OSError, ValueError) as e:
            return None, f"arquivo ilegível: {e}"

    def aplicar_se_mudou(self):
        """Relê o arquivo se ele mudou e reorganiza os grupos. True se aplicou."""
        try:
            st = self.arquivo.stat()
            assinatura = (st.st_mtime_ns, st.st_size)
        except FileNotFoundError:
            assinatura = None
        # Sem o arquivo, a assinatura é None -- e None == None. Sem o
        # '_aplicado', um gateway recém-instalado (ainda sem inversor
        # cadastrado) reaplicaria a lista vazia a cada 2 s, para sempre.
        if self._aplicado and assinatura == self._assinatura:
            return False
        self._assinatura = assinatura
        self._aplicado = True

        config, erro_arq = self._ler_arquivo()
        if config is None:
            # Arquivo corrompido (meia escrita?): mantém o que estava rodando.
            log.error("%s -- mantendo a configuração anterior", erro_arq)
            self.pub.estado({"ts": int(time.time() * 1000), "ok": False,
                             "erro_arquivo": erro_arq})
            return False

        validos, erros = validar(config, self.catalogo)
        for e in erros:
            log.warning("inversor %s ignorado: %s", e["id"], e["erro"])

        self._parar_todos()
        antigos = set(self.disps)
        self.disps = {it["id"]: Dispositivo(it, self.catalogo["modelos"][it["modelo"]])
                      for it in validos}
        # Quem saiu da lista vira offline no painel, em vez de ficar
        # "online" retido no broker para sempre.
        for iid in antigos - set(self.disps):
            self.pub.cli.publish(f"monitoramento/{iid}/status", "offline",
                                 qos=1, retain=True)

        grupos = {}
        for d in self.disps.values():
            grupos.setdefault(chave_grupo(d), []).append(d)
        self._parar_grupos = threading.Event()
        self._fios = [threading.Thread(target=rodar_grupo,
                                       args=(ch, ds, self.pub, self._parar_grupos),
                                       daemon=True, name=f"grupo-{ch[1]}")
                      for ch, ds in grupos.items()]
        for f in self._fios:
            f.start()
        log.info("configuração aplicada: %d inversor(es) em %d conexão(ões), "
                 "%d recusado(s)", len(self.disps), len(grupos), len(erros))
        self.pub.estado({"ts": int(time.time() * 1000), "ok": not erros,
                         "ativos": sorted(self.disps), "erros": erros})
        return True

    def _parar_todos(self):
        if self._parar_grupos is not None:
            self._parar_grupos.set()
            for f in self._fios:
                f.join(timeout=10)
        self._fios = []

    def rodar(self, parar):
        while not parar.is_set():
            self.aplicar_se_mudou()
            parar.wait(RELEITURA_S)
        self._parar_todos()
        for d in self.disps.values():
            self.pub.cli.publish(d.topic_status, "offline", qos=1, retain=True)


def conectar_mqtt():
    import paho.mqtt.client as mqtt
    try:
        cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="insightx-inversores")
    except AttributeError:
        cli = mqtt.Client(client_id="insightx-inversores")
    if os.getenv("MQTT_USER"):
        cli.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS", ""))
    cli.connect(os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")),
                keepalive=60)
    cli.loop_start()
    return cli


def main():
    if "--validar" in sys.argv:
        cfg = json.loads(Path(ARQ_PADRAO).read_text(encoding="utf-8"))
        validos, erros = validar(cfg, carregar_catalogo())
        print(f"{len(validos)} válido(s), {len(erros)} com erro")
        for e in erros:
            print(f"  {e['id']}: {e['erro']}")
        sys.exit(1 if erros else 0)

    import signal
    parar = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    cli = conectar_mqtt()
    log.info("lendo a configuração de %s", ARQ_PADRAO)
    try:
        Servico(ARQ_PADRAO, Publicador(cli)).rodar(parar)
    except KeyboardInterrupt:
        pass
    finally:
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    main()
