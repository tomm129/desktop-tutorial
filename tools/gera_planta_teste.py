#!/usr/bin/env python3
"""Gera um cadastro grande para testar o painel sob escala.

Existe para responder "o que quebra quando a planta cresce?" ANTES de
descobrir isso num cliente. Escreve dados/ativos.json com N ativos e faz
backup do que estava lá.

    python tools/gera_planta_teste.py 24          # 24 ativos
    python tools/gera_planta_teste.py --restaurar # devolve o backup

Depois rode o simulador lendo esse cadastro:

    python tools/simulador_campo.py --do-cadastro --intervalo 2
"""
import argparse
import json
import os
import random
import shutil
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CADASTRO = os.path.join(RAIZ, "dados", "ativos.json")
BACKUP = os.path.join(RAIZ, "dados", "ativos.json.antes-do-teste")

# Nomes plausíveis de planta, para a tela não virar "Ativo 1..24" — nomes
# reais têm comprimentos diferentes, e é justamente a variação de largura
# que quebra layout.
FAMILIAS = [
    ("Caldeira", ["Bomba de alimentacao", "Ventilador de tiragem",
                  "Bomba de condensado"], "Casa de Caldeiras"),
    ("ETE — Tanque de Aeracao", ["Soprador 1", "Soprador 2"],
     "Estacao de Tratamento"),
    ("Torre de Resfriamento", ["Ventilador", "Bomba de recirculacao"],
     "Cobertura — Utilidades"),
    ("Transportador de Correia", ["Motor 1", "Motor 2"], "Galpao 2"),
    ("Compressor de Ar", ["Motor principal", "Ventilador do pos-resfriador"],
     "Central de Ar Comprimido"),
    ("Exaustor de Processo", ["Motor"], "Linha 3"),
    ("Moinho de Martelos", ["Motor principal", "Alimentador"], "Moagem"),
    ("Bomba de Processo", ["Motor"], "Area 40"),
    ("Elevador de Canecas", ["Motor do elevador"], "Torre de Elevacao"),
    ("Peneira Vibratoria", ["Vibrador 1", "Vibrador 2"], "Classificacao"),
]

# Carcaças reais, com alturas de eixo que caem em grupos ISO diferentes --
# é isso que exercita a derivação de limites por plaqueta.
PORTES = [
    (5, "112M", 9.5), (7.5, "132S/M", 13.4), (11, "132M", 21.5),
    (15, "160M", 28.4), (22, "180L", 40.5), (37, "200L", 66.0),
    (55, "225S/M", 98.0), (90, "250M", 158.0), (160, "315S/M", 280.0),
]


def gerar(n_ativos, semente=7):
    rnd = random.Random(semente)
    cad = {}
    i = 0
    while len(cad) < n_ativos:
        base, partes, local = FAMILIAS[i % len(FAMILIAS)]
        seq = i // len(FAMILIAS) + 1
        nome = f"{base} {seq:02d}"
        i += 1

        d = {"local": f"{local} — setor {rnd.choice('ABCD')}", "partes": {}}
        # Nem todo ativo tem inversor: o drive e OPCIONAL, e a tela precisa
        # aguentar a mistura sem desalinhar.
        for j, parte in enumerate(partes):
            kw, carcaca, inom = rnd.choice(PORTES)
            dev = f"esp-{len(cad):02d}{j}"
            p = {
                "esp32": dev,
                "placa": {
                    "fabricante": rnd.choice(["WEG", "Voges", "Siemens"]),
                    "modelo": rnd.choice(["W22 IR3 Premium", "W21", "1LE0"]),
                    "potencia_cv": round(kw / 0.7355, 1),
                    "potencia_kw": kw,
                    "carcaca": carcaca,
                    "corrente_nominal_a": inom,
                    "rpm": rnd.choice([1160, 1760, 3520]),
                    "tensao_v": "380",
                },
            }
            if rnd.random() < 0.65:                 # ~2/3 tem inversor
                p["inversor"] = f"pf-{len(cad):02d}{j}"
                p["tag_inversor"] = f"U{len(cad)+1}{j+1}"
            d["partes"][parte] = p
        cad[nome] = d
    return cad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("n", nargs="?", type=int, default=24,
                    help="quantos ativos gerar (padrao 24)")
    ap.add_argument("--restaurar", action="store_true",
                    help="devolve o cadastro que existia antes do teste")
    a = ap.parse_args()

    if a.restaurar:
        if not os.path.exists(BACKUP):
            sys.exit("nao ha backup para restaurar")
        shutil.copy(BACKUP, CADASTRO)
        print(f"cadastro restaurado de {os.path.basename(BACKUP)}")
        return

    # Backup so na primeira vez, para nao sobrescrever o original com uma
    # planta de teste caso o script rode duas vezes.
    if os.path.exists(CADASTRO) and not os.path.exists(BACKUP):
        shutil.copy(CADASTRO, BACKUP)
        print(f"backup em {os.path.basename(BACKUP)}")

    cad = gerar(a.n)
    with open(CADASTRO, "w", encoding="utf-8") as f:
        json.dump(cad, f, ensure_ascii=False, indent=2)
        f.write("\n")

    partes = sum(len(v["partes"]) for v in cad.values())
    esps = sum(1 for v in cad.values() for p in v["partes"].values() if p.get("esp32"))
    invs = sum(1 for v in cad.values() for p in v["partes"].values() if p.get("inversor"))
    print(f"gerado: {len(cad)} ativos, {partes} partes, "
          f"{esps} ESP32, {invs} inversores ({esps + invs} dispositivos)")
    print(f"escrito em dados/ativos.json")


if __name__ == "__main__":
    main()
