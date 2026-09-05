# Modelos 3D (KayKit)

Ponha aqui os `.gltf`/`.glb` do **KayKit Character Pack: Adventurers**
(https://kaylousberg.itch.io/kaykit-adventurers) — licença **CC0**, uso
comercial livre e sem atribuição.

O nome do arquivo só precisa **conter** a palavra que identifica a classe:

| Arquivo contém | Vira a classe |
|---|---|
| `barbarian` | guerreiro |
| `knight` | paladino |
| `rogue` | assassino |
| `mage` | mago |
| `ranger` | arqueiro |

Faltam **clérigo** e **druida** no pacote grátis: o Druid está no tier pago
(US$ 7,95) e clérigo não existe nesse pacote — dá para improvisar recolorindo
o Knight ou o Mage.

## Como gerar as folhas de sprite

```
Godot.exe --headless --editor --path . --quit          # importa os modelos
Godot.exe --path . --script res://tools/render3d/Renderizador.gd
python tools/gerar_animacoes.py
```

Estes arquivos **não vão para o git** (ver `.gitignore`): são dezenas de MB e
qualquer um baixa do itch.io de graça. O que o jogo usa são os PNGs gerados em
`arte/classes/`.
