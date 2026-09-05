# Brawl Coop — Protótipo

Protótipo de um jogo cooperativo top-down com **classes de RPG**, feito na
**Godot Engine 4**. Você e um aliado controlado pelo computador enfrentam ondas
de goblins numa arena.

## Como rodar

1. Baixe a Godot Engine (versão **4.3** ou mais nova) em https://godotengine.org/download
   — é um único arquivo, não precisa instalar nada.
2. Abra a Godot, clique em **Import**, e selecione o `project.godot` desta pasta.
3. Aperte **F5**.

Atalho para testar sem passar pela tela de escolha:

```
Godot_v4.3-stable_win64.exe --path . -- mago clerigo
```

(a primeira classe é a sua, a segunda é a do aliado)

## Controles

| Ação                    | Tecla / botão                 |
|-------------------------|-------------------------------|
| Escolher classe         | **1 a 7** (na tela inicial)   |
| Andar                   | **W A S D**                   |
| Mirar                   | mover o **mouse**             |
| Atacar                  | **botão esquerdo** do mouse   |
| Habilidade da classe    | **Q**                         |
| Escolher item           | **1 2 3 4**                   |
| Trocar o alvo do item   | **T** (você ↔ aliado)         |
| Usar o item             | **E**                         |
| Inimigos neutros/hostis | **N**                         |
| Recomeçar               | **R** (depois do fim de jogo) |

## As 7 classes

Tudo o que diferencia uma classe está em **`Classes.gd`** — é o único arquivo a
mexer para balancear.

| Classe | Vida | Ataque | Habilidade (Q) |
|---|---|---|---|
| Guerreiro | 160 | corpo a corpo em leque, 40 de dano | Golpe giratório: 55 em todos em volta |
| Paladino  | 150 | corpo a corpo em leque, 34 | Escudo sagrado: 4s de imunidade para a party |
| Clérigo   | 110 | tiro reto fraco, 18 | Aura de cura: 10 de vida por segundo, 4s |
| Mago      | 90  | tiro que estoura em área, 28 + 22 | Nova de fogo: 70 de dano em volta |
| Arqueiro  | 100 | tiro reto rápido e longo, 22 | Chuva de flechas: 7 tiros em leque |
| Druida    | 120 | tiro que deixa lento, 20 | Raízes: prende os inimigos por 2,6s |
| Assassino | 85  | corpo a corpo curto e veloz, 16 | Investida: avança atravessando, 45 de dano |

## O que já funciona

- **Escolha de classe** para você e para o aliado, com retrato e ficha.
- **Party de dois**: os dois saem do mesmo `Personagem.gd`; o aliado tem
  `por_ia = true`, te acompanha, ataca o inimigo mais perto, recua quando colam
  nele e solta a habilidade sozinho na hora certa.
- **8 direções de verdade**: o boneco olha para onde você mira, não é espelho.
- **Ondas de goblins** que perseguem o membro da party mais perto.
- **Inventário** de 4 slots (kit, escudo, turbo) com alvo alternável entre você
  e o aliado.
- **Itens caindo** dos inimigos mortos.
- **Modo neutro** (**N**): os inimigos andam e animam, mas não causam dano —
  serve para assistir o jogo rodando.
- **Fim de jogo** só quando **você** cai; o aliado cair não encerra.

## Armadilhas que já custaram tempo

- **Camada e máscara de colisão já vêm com o bit 1 ligado.** Se você só fizer
  `set_collision_mask_value(2, true)`, a camada 1 continua ligada e o tiro
  acerta o próprio jogador. Sempre zere (`collision_mask = 0`) antes.
- **A carência de invulnerabilidade é curta (0,2s) de propósito.** Com 0,5s ela
  absorvia o dano dos outros inimigos e uma onda de 7 machucava igual a uma de 3.
- **A pose de morte é aplicada dentro do `receber_dano()`**, não no
  `_physics_process()`: a Main pausa a árvore ao receber o sinal de morte, e aí
  o `_physics_process` nunca mais roda — o boneco morria em pé.
- **Piso de cor chapada não aceita variação de brilho por tile.** Mesmo 1,5% de
  diferença vira um xadrez visível na tela.
- **Y-sort só na camada dos personagens.** Se os tiles do chão entrarem na
  ordenação, um tile de baixo passa na frente de um personagem de cima.
- **Barra de vida não pode ser desenhada pelo próprio personagem.** Com y_sort,
  quem está à frente desenha por cima da barra de quem está atrás. Por isso as
  barras saíram para uma camada só delas (`BarrasNaTela.gd`), que entra depois
  da arena — e, já que estão todas no mesmo lugar, ela também empilha as que se
  encostam.
- **`class_name` novo só passa a existir depois de reimportar o projeto.**
  Criar o arquivo e rodar direto dá "Identifier not declared", e o jogo abre sem
  personagem nenhum. Rode a Godot uma vez com `--import` depois de criar.

## Publicando uma versão nova (o que os jogadores recebem)

O jogo distribuído são dois arquivos: **BrawlCoop.exe** (o motor, ~84 MB, quase
nunca muda) e **BrawlCoop.pck** (o jogo inteiro, ~824 KB). Uma atualização é só
o `.pck` novo — foi conferido que o `.exe` sai byte a byte idêntico entre
versões que só mexem no jogo.

Para publicar:

1. Suba a versão em **dois** lugares: `const VERSAO` no `Atualizador.gd` e o
   campo `versao` do `versao.json`.
2. Exporte:
   `Godot.exe --headless --path . --export-release "Windows" ../dist/BrawlCoop.exe`
3. Publique a release com os três arquivos anexados:
   `gh release create v0.4.2 dist/BrawlCoop.exe dist/BrawlCoop.pck dist/versao.json --title "..." --notes "..."`

O `.exe` vai junto para quem for instalar do zero; quem já tem o jogo recebe só
o `.pck`.

### Como o cliente se atualiza

`Atualizador.gd` é um autoload, então roda **antes** da cena principal:

1. monta o `.pck` mais recente que estiver em `user://patches/` (é assim que uma
   atualização já baixada entra em vigor, sem sobrescrever arquivo nenhum e sem
   precisar de permissão de administrador)
2. consulta `releases/latest/download/versao.json` — o próprio GitHub resolve
   qual é a release mais nova, então não há URL para editar a cada versão
3. se houver versão maior, baixa o `.pck` em segundo plano e avisa no rodapé
4. na abertura seguinte, o passo 1 aplica

Sem internet, ou com o GitHub fora, o jogo abre normalmente na versão que já
tem: o atualizador nunca bloqueia a abertura.

**Pegadinha observada:** logo depois de publicar, a URL de `latest` pode servir
por alguns instantes a resposta anterior em cache. O cliente vê a versão nova na
tentativa seguinte.

## Próximas etapas

1. **Online** — dois jogadores de verdade, em PCs diferentes, com o multiplayer
   embutido da Godot. A party já está pronta: os dois membros saem do mesmo
   script, só muda quem dá as ordens (teclado, IA ou rede).
2. **Reviver** — hoje quem cai fica caído até o fim da partida.
3. **Arte que falta** — quadros de ataque e de morte para os personagens,
   ícones de item em pixel art (os atuais são vetoriais e destoam), e chão com
   textura em vez de cor lisa.
4. **Variedade de inimigo** — hoje só goblin; o pacote tem imp, slime, orc,
   troll e mais 50.
