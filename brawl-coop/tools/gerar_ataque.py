# -*- coding: utf-8 -*-
"""Gera a folha de ATAQUE de um personagem usando a API da PixelLab.

Por que existe: a arte do FreePixel só tem idle/walk/run. Sem quadro de ataque,
o combate depende de gambiarra (o "bote" que o inimigo dá). Este script pede à
PixelLab os quadros de golpe, no MESMO tamanho da nossa arte (128px), partindo
do nosso próprio personagem como referência — é isso que mantém cor, proporção
e estilo iguais aos das outras animações.

COMO FUNCIONA

1. Para cada direção, estima o esqueleto (18 pontos) do nosso quadro parado.
2. Move ombro, cotovelo e mão para montar 3 poses: arma erguida, golpe à frente
   e recuperação. A direção do golpe acompanha o lado para onde o boneco olha.
3. Pede a animação em 128x128 e monta tudo numa folha 3 quadros x 8 direções.

CUSTO (a cota gratuita da PixelLab é de ~40 gerações por mês):
  estimativa de esqueleto = 0.1   |   animação = 1.0
  Só geramos 5 direções; as outras 3 saem por ESPELHO, o que economiza 3
  gerações por personagem. Total: ~5.5 por personagem.

USO
  set PIXELLAB_KEY=<sua chave>          (ou passe --chave <arquivo>)
  python tools/gerar_ataque.py goblin
"""
import argparse
import base64
import copy
import io
import json
import os
import pathlib
import sys
import urllib.request

from PIL import Image

API = "https://api.pixellab.ai/v1"
LADO = 128
# Qual braco da o golpe. Na nossa arte a arma fica na mao ESQUERDA do boneco;
# animando o direito, ele erguia o punho vazio e a arma ficava parada -- virava
# soco, nao golpe de arma.
BRACO = "LEFT"
RAIZ = pathlib.Path(__file__).resolve().parent.parent

# linha da folha -> (nome que a API entende, vetor "para frente" na tela)
# x cresce para a direita, y cresce para baixo
DIRECOES = {
    0: ("south",      (0.0, 1.0)),
    7: ("south-east", (0.7, 0.7)),
    6: ("east",       (1.0, 0.0)),
    5: ("north-east", (0.7, -0.7)),
    4: ("north",      (0.0, -1.0)),
}
# linha vazia -> (linha de origem, espelhar)
ESPELHOS = {1: (7, True), 2: (6, True), 3: (5, True)}


def chamar(rota: str, corpo: dict, chave: str, segundos: int = 240) -> dict:
    req = urllib.request.Request(
        f"{API}/{rota}",
        data=json.dumps(corpo).encode(),
        headers={"Authorization": "Bearer " + chave, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=segundos) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Sem isto o erro vira so "HTTP 422" e nao da para saber o que a API
        # recusou -- que foi exatamente o que me travou na primeira tentativa.
        detalhe = e.read().decode()[:800]
        raise SystemExit("a API recusou " + rota + " (HTTP " + str(e.code) + "): " + detalhe)


def para_base64(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def de_base64(dado) -> Image.Image:
    bruto = dado["base64"] if isinstance(dado, dict) else dado
    return Image.open(io.BytesIO(base64.b64decode(bruto))).convert("RGBA")


def ponto(esqueleto: list, rotulo: str) -> tuple:
    for p in esqueleto:
        if p["label"] == rotulo:
            return p["x"], p["y"]
    return 0.5, 0.5


def com(esqueleto: list, mudancas: dict) -> list:
    p = copy.deepcopy(esqueleto)
    for pt in p:
        if pt["label"] in mudancas:
            pt["x"], pt["y"] = mudancas[pt["label"]]
        # A propria API e inconsistente: /estimate-skeleton devolve z_index
        # fracionario (-3.5, -0.5) e /animate-with-skeleton exige inteiro,
        # recusando com 422. Arredondar aqui e o que liga os dois.
        pt["z_index"] = int(round(float(pt.get("z_index", 0))))
    return p


def poses_do_golpe(esqueleto: list, frente: tuple) -> list:
    """As 3 poses. O golpe sai na direcao para onde o boneco esta olhando."""
    fx, fy = frente
    ox, oy = ponto(esqueleto, BRACO + " SHOULDER")

    def preso(x, y):
        return (min(max(x, 0.03), 0.97), min(max(y, 0.03), 0.97))

    armada = com(esqueleto, {
        (BRACO + " ARM"):    preso(ox - fx * 0.24, oy - fy * 0.24 - 0.20),
        (BRACO + " ELBOW"):  preso(ox - fx * 0.13, oy - fy * 0.13 - 0.06),
        "NOSE":         preso(*[a + b for a, b in zip(ponto(esqueleto, "NOSE"), (-fx * 0.03, -fy * 0.03))]),
    })
    batendo = com(esqueleto, {
        (BRACO + " ARM"):    preso(ox + fx * 0.34, oy + fy * 0.34 + 0.12),
        (BRACO + " ELBOW"):  preso(ox + fx * 0.17, oy + fy * 0.17 + 0.06),
        "NOSE":         preso(*[a + b for a, b in zip(ponto(esqueleto, "NOSE"), (fx * 0.05, fy * 0.05))]),
    })
    voltando = com(esqueleto, {
        (BRACO + " ARM"):    preso(ox + fx * 0.10, oy + fy * 0.10 + 0.18),
        (BRACO + " ELBOW"):  preso(ox + fx * 0.05, oy + fy * 0.05 + 0.09),
    })
    return [armada, batendo, voltando]


def gerar(classe: str, chave: str, so_uma: int = -1) -> None:
    pasta = RAIZ / "arte" / "classes" / classe
    parado = Image.open(pasta / "parado.png").convert("RGBA")
    colunas_parado = parado.width // LADO

    destino = pasta / "atacar.png"
    if destino.exists():
        folha = Image.open(destino).convert("RGBA")
    else:
        folha = Image.new("RGBA", (LADO * 3, LADO * 8), (0, 0, 0, 0))

    gasto = 0.0
    for linha, (nome_api, frente) in DIRECOES.items():
        if so_uma >= 0 and linha != so_uma:
            continue
        ref = parado.crop((0, linha * LADO, LADO, linha * LADO + LADO))
        if colunas_parado > 1:
            ref = parado.crop((0, linha * LADO, LADO, linha * LADO + LADO))

        print(f"  linha {linha} ({nome_api}): estimando esqueleto...", flush=True)
        r = chamar("estimate-skeleton", {"image": {"type": "base64", "base64": para_base64(ref)}}, chave, 120)
        esqueleto = r["keypoints"]
        gasto += 0.1

        print(f"  linha {linha} ({nome_api}): gerando o golpe...", flush=True)
        r = chamar("animate-with-skeleton", {
            "image_size": {"width": LADO, "height": LADO},
            "view": "low top-down",
            "direction": nome_api,
            "guidance_scale": 4.0,
            "skeleton_keypoints": poses_do_golpe(esqueleto, frente),
            "reference_image": {"type": "base64", "base64": para_base64(ref)},
        }, chave)
        gasto += 1.0
        for i, im in enumerate(r["images"][:3]):
            folha.paste(de_base64(im), (i * LADO, linha * LADO))

    # As 3 direcoes que faltam saem por espelho, economizando 3 geracoes.
    for linha, (origem, _) in ESPELHOS.items():
        for c in range(3):
            q = folha.crop((c * LADO, origem * LADO, c * LADO + LADO, origem * LADO + LADO))
            folha.paste(q.transpose(Image.FLIP_LEFT_RIGHT), (c * LADO, linha * LADO))

    folha.save(destino)
    print(f"{destino}: gravado ({folha.size}) — gastou ~{gasto:.1f} geracoes")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("classe", help="pasta em arte/classes (ex: goblin)")
    ap.add_argument("--chave", help="arquivo com a chave da API")
    ap.add_argument("--linha", type=int, default=-1, help="gerar so uma linha (para testar)")
    args = ap.parse_args()

    chave = os.environ.get("PIXELLAB_KEY", "")
    if args.chave:
        chave = pathlib.Path(args.chave).read_text(encoding="utf-8").strip()
    if not chave:
        sys.exit("faltou a chave: defina PIXELLAB_KEY ou passe --chave <arquivo>")

    gerar(args.classe, chave, args.linha)
