# -*- coding: utf-8 -*-
"""Gera os .tres de SpriteFrames a partir das folhas de sprite do FreePixel.

As folhas vêm em 8 DIREÇÕES x N quadros, com quadros de 128x128:

    parado.png  = 512x1024 -> 4 colunas (quadros) x 8 linhas (direções)
    andar.png   = 768x1024 -> 6 colunas (quadros) x 8 linhas (direções)

A ordem das linhas, conferida olhando a folha do arqueiro, gira no sentido
horário começando de baixo (a direção que o boneco está OLHANDO):

    linha 0 = baixo        linha 4 = cima
    linha 1 = baixo-esq.   linha 5 = cima-dir.
    linha 2 = esquerda     linha 6 = direita
    linha 3 = cima-esq.    linha 7 = baixo-dir.

Quem converte um ângulo nessa linha é o Personagem.gd (função _linha_da_direcao).

Em vez de exportar 80 PNGs por personagem, o .tres aponta para a folha inteira
e recorta cada quadro com um AtlasTexture (region). São 2 arquivos de imagem
por personagem, e não 80.

Uso:  python tools/gerar_animacoes.py
"""
import pathlib

LADO = 128            # tamanho do quadro
DIRECOES = 8          # linhas da folha
FPS_PARADO = 6.0
FPS_ANDANDO = 12.0
FPS_ATACANDO = 11.0   # 3 quadros: erguer, bater, voltar

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def gera(pasta_arte: str, saida: str) -> None:
    """pasta_arte é relativo à raiz do projeto, ex: 'arte/classes/mago'."""
    ext = []          # (id, caminho res://)
    sub = []          # (id, id_da_folha, x, y)
    animacoes = []    # (nome, [ids de sub], loop, fps)

    for chave, arquivo, fps in (("parado", "parado.png", FPS_PARADO),
                                ("andando", "andar.png", FPS_ANDANDO),
                                ("atacando", "atacar.png", FPS_ATACANDO)):
        caminho = RAIZ / pasta_arte / arquivo
        if not caminho.exists():
            # A folha de ataque e opcional: so alguns personagens tem, porque
            # ela e gerada pela PixelLab e custa cota (ver tools/gerar_ataque.py).
            if chave == "atacando":
                continue
            raise SystemExit(f"faltando: {caminho}")

        # Descobre quantos quadros tem a folha pela largura dela.
        largura = _largura_png(caminho)
        quadros = largura // LADO

        # O id NAO pode ser chave[0]: "andando" e "atacando" dariam os dois "a",
        # uma folha sobrescreveria a outra e a caminhada passaria a apontar para
        # os quadros de ataque (foi exatamente o que aconteceu na 0.9.0).
        id_folha = "f%d" % len(ext)
        ext.append((id_folha, f"res://{pasta_arte}/{arquivo}"))

        for linha in range(DIRECOES):
            ids = []
            for coluna in range(quadros):
                id_sub = f"{chave}_{linha}_{coluna}"
                sub.append((id_sub, id_folha, coluna * LADO, linha * LADO))
                ids.append(id_sub)
            animacoes.append((f"{chave}_{linha}", ids, chave != "atacando", fps))

    linhas = [f'[gd_resource type="SpriteFrames" load_steps={len(ext) + len(sub) + 1} format=3]', ""]
    for id_ext, caminho in ext:
        linhas.append(f'[ext_resource type="Texture2D" path="{caminho}" id="{id_ext}"]')
    linhas.append("")
    for id_sub, id_folha, x, y in sub:
        linhas.append(f'[sub_resource type="AtlasTexture" id="{id_sub}"]')
        linhas.append(f'atlas = ExtResource("{id_folha}")')
        linhas.append(f"region = Rect2({x}, {y}, {LADO}, {LADO})")
        linhas.append("")
    linhas.append("[resource]")

    blocos = []
    for nome, ids, loop, fps in animacoes:
        quadros_txt = ", ".join(
            '{\n"duration": 1.0,\n"texture": SubResource("%s")\n}' % i for i in ids)
        blocos.append('{\n"frames": [%s],\n"loop": %s,\n"name": &"%s",\n"speed": %s\n}'
                      % (quadros_txt, "true" if loop else "false", nome, fps))
    linhas.append("animations = [" + ", ".join(blocos) + "]")

    (RAIZ / saida).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"{saida}: {len(animacoes)} animacoes ({DIRECOES} direcoes x 2 estados), "
          f"{len(sub)} recortes, {len(ext)} imagens")


def _largura_png(caminho: pathlib.Path) -> int:
    """Lê a largura no cabeçalho IHDR, sem depender de biblioteca de imagem."""
    dados = caminho.read_bytes()[16:20]
    return int.from_bytes(dados, "big")


if __name__ == "__main__":
    for classe in ("guerreiro", "paladino", "clerigo", "mago",
                   "arqueiro", "druida", "assassino"):
        gera(f"arte/classes/{classe}", f"Animacoes_{classe}.tres")
    gera("arte/classes/goblin", "Animacoes_goblin.tres")
