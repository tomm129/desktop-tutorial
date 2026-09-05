# Arte

## Personagens e inimigo — FreePixel

Folhas de sprite de https://freepixel.art (categoria *characters*).

**Licença**: livre para uso pessoal e **comercial**, **sem exigir crédito** (o
crédito aqui é cortesia). A única restrição relevante: não é permitido
**redistribuir os arquivos crus como pacote de assets** — dentro de um jogo,
como aqui, é permitido.

Cada folha é **8 direções x N quadros**, quadros de 128x128:

- `parado.png` = 512x1024 -> 4 quadros x 8 direções
- `andar.png`  = 768x1024 -> 6 quadros x 8 direções

Ordem das linhas (a direção para onde o boneco OLHA), girando no sentido
horário a partir de "olhando para baixo":

```
0 baixo   1 baixo-esq   2 esquerda   3 cima-esq
4 cima    5 cima-dir    6 direita    7 baixo-dir
```

Quem converte ângulo em linha é `_linha_da_direcao()`, no `Personagem.gd` e no
`Inimigo.gd`.

| Pasta | Personagem original no FreePixel |
|---|---|
| `classes/guerreiro` | Barbarian |
| `classes/paladino`  | Golden Paladin |
| `classes/clerigo`   | Healer Priestess |
| `classes/mago`      | Fire Mage |
| `classes/arqueiro`  | Archer Ranger |
| `classes/druida`    | Druid |
| `classes/assassino` | Masked Assassin |
| `classes/goblin`    | Goblin Warrior (o inimigo) |

**Estas folhas não têm quadro de morte nem de levar pancada.** O jogo resolve
assim: pancada = tingir de vermelho; morte = girar o sprite 90 graus e sumir
desvanecendo. Se um dia aparecer arte com esses quadros, é só acrescentar as
animações em `tools/gerar_animacoes.py`.

Os `.tres` de animação são **gerados**, não escritos à mão:

```
python tools/gerar_animacoes.py
```

Ele aponta para a folha inteira e recorta cada quadro com `AtlasTexture`, então
são 2 imagens por personagem em vez de 80 PNGs soltos.

## Piso — FreePixel

`piso2/grama_terra.png` é o tileset *topdown grass-dirt* (4x4 tiles de 32px).
`piso2/grama.png` é a célula de grama pura, recortada dele — é a única usada
hoje. As outras 15 células são transições grama/terra, para quando o chão
deixar de ser liso.

## Ícones de item — Kenney

`itens/` são os ícones 102 / 105 / 148 do pacote **Generic Items** do Kenney
(https://kenney.nl/assets/generic-items), licença **CC0**. São vetoriais, não
pixel art — destoam do resto e são candidatos a troca.
