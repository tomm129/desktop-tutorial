# -*- coding: utf-8 -*-
"""Preenche linhas VAZIAS de uma folha de sprite 8-direções.

Por que isto existe: a folha de caminhada do goblin, como vem do FreePixel,
tem as linhas 2 (esquerda), 6 (direita) e 7 (baixo-direita) em branco. No jogo
isso aparecia como goblin INVISÍVEL andando para esses lados — só a sombra e a
barra de vida na tela.

Como preenche, sem inventar desenho:

  linha 7 (baixo-dir)  = espelho da linha 1 (baixo-esq)
  linha 5 (cima-dir)   = espelho da linha 3 (cima-esq)
  linha 6 (direita)    = espelho da linha 2 (esquerda)
  linha 2 (esquerda)   = a diagonal de baixo (linha 1), que é o ângulo mais
                         próximo quando o par espelhado também está vazio

A ordem das linhas é a mesma do resto do projeto (ver arte/LEIA-ME.md):
0 baixo · 1 baixo-esq · 2 esquerda · 3 cima-esq · 4 cima · 5 cima-dir ·
6 direita · 7 baixo-dir

Uso:  python tools/completar_folha.py arte/classes/goblin/andar.png
"""
import sys
import pathlib
from PIL import Image

LADO = 128
DIRECOES = 8

# de quem copiar quando a linha estiver vazia: (origem, espelhar?)
RECEITA = {
    7: (1, True),    # baixo-dir  <- baixo-esq espelhada
    5: (3, True),    # cima-dir   <- cima-esq espelhada
    6: (2, True),    # direita    <- esquerda espelhada
    2: (1, False),   # esquerda   <- baixo-esq (o par espelhado tambem esta vazio)
    1: (7, True),
    3: (5, True),
}


def linha_vazia(im: Image.Image, linha: int) -> bool:
    colunas = im.width // LADO
    pixels = 0
    for c in range(colunas):
        q = im.crop((c * LADO, linha * LADO, c * LADO + LADO, linha * LADO + LADO))
        pixels += sum(1 for a in q.getchannel("A").getdata() if a > 8)
    return pixels < 200


def completa(caminho: pathlib.Path) -> None:
    im = Image.open(caminho).convert("RGBA")
    colunas = im.width // LADO
    vazias = [l for l in range(DIRECOES) if linha_vazia(im, l)]
    if not vazias:
        print(f"{caminho}: nada a fazer, as 8 direcoes estao preenchidas")
        return
    print(f"{caminho}: linhas vazias {vazias}")

    for linha in vazias:
        origem, espelhar = RECEITA.get(linha, (0, False))
        if linha_vazia(im, origem):
            origem = 0   # ultimo recurso: a linha de frente, que sempre existe
            espelhar = False
        for c in range(colunas):
            q = im.crop((c * LADO, origem * LADO, c * LADO + LADO, origem * LADO + LADO))
            if espelhar:
                q = q.transpose(Image.FLIP_LEFT_RIGHT)
            im.paste(q, (c * LADO, linha * LADO))
        print(f"  linha {linha} <- linha {origem}{' espelhada' if espelhar else ''}")

    im.save(caminho)
    print(f"{caminho}: gravado")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("uso: python tools/completar_folha.py <folha.png>")
    for arg in sys.argv[1:]:
        completa(pathlib.Path(arg))
