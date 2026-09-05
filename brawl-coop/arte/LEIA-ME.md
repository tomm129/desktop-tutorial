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

**ATENÇÃO: algumas folhas vêm com direções em branco.** A do goblin vinha sem
as linhas 2, 6 e 7; a do arqueiro, sem a linha 1. No jogo isso aparecia como
personagem **invisível** andando para aquele lado — só a sombra e a barra de
vida. O `tools/completar_folha.py` preenche essas linhas copiando e espelhando
as vizinhas, e é bom rodá-lo em toda folha nova:

```
python tools/completar_folha.py arte/classes/<classe>/andar.png
```

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

## Efeitos — FreePixel

`vfx/` são efeitos de magia da categoria *spell-effects* do FreePixel, mesma
licença do resto. **São imagens únicas de 200x200, não folhas de animação**:
quem anima é o `Efeitos.gd`, fazendo o efeito nascer pequeno, crescer e sumir.

| Arquivo | Onde entra |
|---|---|
| `nova`    | Nova de fogo (mago) e Golpe giratório (guerreiro) |
| `escudo`  | Escudo sagrado (paladino) |
| `cura`    | Aura de cura (clérigo) |
| `raizes`  | Raízes (druida) |
| `corte`   | golpe corpo a corpo |
| `estouro` | frasco explosivo |
| `impacto` | acerto de projétil |

`enfeites/` são vegetação e pedras espalhadas pelo chão, das categorias
*foliage* e *rocks* do mesmo site.

## Quadros de ataque — gerados pela PixelLab

O FreePixel não tem folha de ataque. A do goblin (`classes/goblin/atacar.png`,
3 quadros x 8 direções) foi **gerada** pela API da PixelLab a partir da nossa
própria arte, o que mantém cor, proporção e densidade de pixel iguais:

```
set PIXELLAB_KEY=<chave>
python tools/gerar_ataque.py goblin
```

Como funciona: para cada direção o script estima o esqueleto (18 pontos) do
nosso quadro parado, move ombro/cotovelo/mão para montar 3 poses (arma erguida,
golpe à frente, recuperação) e pede a animação em 128x128. Só 5 direções são
geradas; as outras 3 saem por espelho.

**Custo**: ~5,5 gerações por personagem (a cota gratuita é de ~40 por mês).

Duas armadilhas que custaram tempo:

- **Anime o braço que segura a arma.** Animando o outro, o boneco erguia o
  punho vazio e a arma ficava parada — virava soco, não golpe.
- **`/estimate-skeleton` devolve `z_index` fracionário (-3.5) e
  `/animate-with-skeleton` exige inteiro**, recusando com 422. A saída de um
  endpoint não entra direto no outro; o script arredonda.
