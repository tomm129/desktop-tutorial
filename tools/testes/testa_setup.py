#!/usr/bin/env python3
"""Confere o setup do gateway sem precisar de um Orange Pi.

O setup_orangepi.sh so roda de verdade numa placa, e a placa nem sempre
esta a mao. Mas boa parte do que pode quebrar nele da para pegar aqui:

  - sintaxe dos dois scripts (bash -n);
  - os trechos de Python EMBUTIDOS no setup (heredoc <<'PY'): o bash -n nao
    os enxerga. Um deles ficou com erro de sintaxe de 06/08 a 24/09 -- e
    com 'set -e' o setup parava ali, sem instalar o resto;
  - o patch do settings.js do Node-RED, rodado contra um settings.js de
    verdade: tem de continuar carregavel e nao duplicar ao rodar de novo;
  - todo tipo de no do flows.json tem de ter o modulo instalado ANTES do
    primeiro start do Node-RED. Com UM tipo faltando o Node-RED nao
    inicia fluxo nenhum;
  - o servico de inversores pode abrir a porta serial (grupo dialout).

Uso:
    python tools/testes/testa_setup.py
"""
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SETUP = RAIZ / "scripts" / "setup_orangepi.sh"
VERIFICA = RAIZ / "scripts" / "verifica_instalacao.sh"
FLOWS = RAIZ / "nodered" / "flows.json"
CATALOGO = RAIZ / "integracoes" / "inversores" / "catalogo.json"

falhas = 0


def ok(cond, nome, extra=""):
    global falhas
    if not cond:
        falhas += 1
    print(f"  [{'OK ' if cond else 'FALHA'}] {nome}{('  ' + extra) if extra else ''}")


def funcao_bash(texto, nome):
    """Corpo de uma funcao do script: de 'nome() {' ate o '}' da coluna 0."""
    m = re.search(rf"^{nome}\(\) \{{\n(.*?)^\}}", texto, re.S | re.M)
    return m.group(1) if m else ""


setup = io.open(SETUP, encoding="utf-8").read()

# =====================================================================
print("\n=== 1. Sintaxe dos scripts ===")
bash = shutil.which("bash")
if bash:
    for s in (SETUP, VERIFICA):
        r = subprocess.run([bash, "-n", str(s)], capture_output=True, text=True)
        ok(r.returncode == 0, f"bash -n {s.name}", r.stderr.strip()[:200])
else:
    print("  (bash nao encontrado -- pulando bash -n)")
ok(b"\r" not in SETUP.read_bytes() and b"\r" not in VERIFICA.read_bytes(),
   "scripts com LF (CRLF mata o bash com $'\\r': command not found)")

# =====================================================================
print("\n=== 2. Python embutido no setup ===")
blocos = re.findall(r"python3 - [^\n]*<<'(\w+)'\n(.*?)\n\1\n", setup, re.S)
ok(len(blocos) >= 1, "achou os trechos de Python embutidos", f"-> {len(blocos)}")
for i, (_, codigo) in enumerate(blocos, 1):
    try:
        compile(codigo, f"<setup bloco {i}>", "exec")
        ok(True, f"bloco {i} compila")
    except SyntaxError as e:
        ok(False, f"bloco {i} compila", f"-> linha {e.lineno}: {e.msg}")

# =====================================================================
print("\n=== 3. Patch do httpStatic contra um settings.js de verdade ===")
patch = next((c for _, c in blocos if "httpStatic" in c), None)
ok(patch is not None, "achou o bloco que configura o httpStatic")
# Como o settings.js padrao comeca: o httpStatic aparece COMENTADO, que e
# justamente o caso que um grep solto confundia com "ja configurado".
SETTINGS = """/**
 * Node-RED Settings
 */
module.exports = {
    flowFile: 'flows.json',
    uiPort: process.env.PORT || 1880,
    //httpStatic: '/home/nol/node-red-static/', //single static source
    // httpStatic: [ {path: '/a/', root: '/b/'} ],
    functionTimeout: 0,
}
"""
if patch:
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "settings.js"
        arq.write_text(SETTINGS, encoding="utf-8")
        fotos = "/home/usuario/iot-monitoramento/dados/fotos"
        roda = lambda: subprocess.run([sys.executable, "-c", patch, str(arq), fotos],
                                      capture_output=True, text=True)
        r1 = roda()
        ok(r1.returncode == 0, "o patch roda", (r1.stderr or r1.stdout).strip()[-200:])
        depois = arq.read_text(encoding="utf-8")
        r2 = roda()
        ok(arq.read_text(encoding="utf-8") == depois,
           "rodar de novo nao muda nada (setup idempotente)")
        ativos = re.findall(r"^\s*httpStatic\s*:", depois, re.M)
        ok(len(ativos) == 1, "exatamente um httpStatic ativo", f"-> {len(ativos)}")
        node = shutil.which("node")
        if node:
            js = ("const s=require(process.argv[1]);"
                  "process.stdout.write(JSON.stringify(s.httpStatic ?? null))")
            r = subprocess.run([node, "-e", js, str(arq)], capture_output=True, text=True)
            ok(r.returncode == 0, "settings.js continua carregavel pelo Node",
               r.stderr.strip()[-200:])
            if r.returncode == 0:
                hs = json.loads(r.stdout)
                ok(hs == [{"path": fotos, "root": "/fotos/"}],
                   "fotos servidas em /fotos/", f"-> {hs}")

# =====================================================================
print("\n=== 4. Todo tipo de no do fluxo tem o modulo instalado a tempo ===")
NUCLEO = {"tab", "inject", "debug", "function", "change", "switch", "json",
          "file", "file in", "mqtt in", "mqtt out", "mqtt-broker", "delay",
          "trigger", "template", "http in", "http response", "http request",
          "catch", "status", "complete", "link in", "link out", "link call",
          "comment", "split", "join", "exec", "range", "csv", "rbe", "filter"}
MODULO = {"@flowfuse/node-red-dashboard": lambda t: t.startswith("ui-"),
          "node-red-contrib-postgresql": lambda t: t in ("postgresql", "postgreSQLConfig")}
tipos = {n["type"] for n in json.loads(FLOWS.read_text(encoding="utf-8"))}
nodered = funcao_bash(setup, "instalar_nodered")
ok(bool(nodered), "achou a funcao instalar_nodered")
# Tudo tem de estar instalado ANTES do primeiro start ('enable --now'):
# um modulo que chega com o Node-RED no ar so carrega no proximo reinicio.
antes_start = nodered.split("systemctl enable --now nodered")[0]
for t in sorted(tipos - NUCLEO):
    mod = next((m for m, casa in MODULO.items() if casa(t)), None)
    if mod is None:
        ok(False, f"tipo '{t}' tem modulo conhecido", "-> acrescente em MODULO neste teste")
        continue
    ok(f"npm install --no-fund --no-audit {mod}" in antes_start,
       f"'{t}' -> {mod} instalado no passo do Node-RED, antes do start")

# =====================================================================
print("\n=== 5. Servico de inversores ===")
catalogo = json.loads(CATALOGO.read_text(encoding="utf-8"))
tem_rtu = any("rtu" in m["conexoes"] for m in catalogo["modelos"].values())
inv = funcao_bash(setup, "instalar_inversores")
if tem_rtu:
    ok("SupplementaryGroups=dialout" in inv,
       "servico entra no grupo dialout (porta serial do RS-485)")
ok("INVERSORES_ARQ=${DESTINO_IOT}/dados/inversores.json" in inv,
   "config.env aponta para a lista que o painel grava")
ok("lsb_release -cs)" not in setup.replace("lsb_release -cs 2>/dev/null", ""),
   "codinome da distro nao depende so do lsb_release (ausente em imagem minimal)")

print()
print("RESULTADO: todas as verificacoes passaram." if not falhas
      else f"RESULTADO: {falhas} falha(s).")
sys.exit(1 if falhas else 0)
