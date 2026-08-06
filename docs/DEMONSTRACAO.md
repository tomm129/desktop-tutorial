# Demonstração sem hardware

Sobe uma planta industrial fictícia — caldeira, ETE, torre de resfriamento e
transporte — com condições diferentes em cada ativo, de modo que **uma única
tela mostre os quatro estados** que o painel sabe representar.

> ⚠️ **Os dados são simulados.** Servem para demonstrar o comportamento da
> interface, não para representar medições de nenhuma planta real. Ao
> apresentar, diga isso — é a diferença entre demonstrar um produto e
> alegar uma instalação.

## Como rodar

Precisa apenas de Node.js e Python.

```bash
# 1. Node-RED com o fluxo do repositório
npx node-red

# 2. Aponte o cadastro de placa para o exemplo da demo
cp dados/ativos.demo.json dados/ativos.json
export IOT_DADOS="$PWD/dados"        # Windows: set IOT_DADOS=%CD%\dados

# 3. A planta
python tools/simulador_campo.py --demo
```

Abra `http://localhost:1880/dashboard/visao`.

Para o cadastro de ativos do fluxo, cole na constante `ATIVOS` da função
**montar painel**:

```javascript
const ATIVOS = {
    'Caldeira 01': { partes: {
        'Bomba de alimentacao':  { esp32: 'caldeira-bomba', inversor: 'pf-caldeira-01', tag_inversor: 'U11' },
        'Ventilador de tiragem': { esp32: 'caldeira-vent',  inversor: 'pf-caldeira-02', tag_inversor: 'U12' }
    } },
    'ETE — Tanque de Aeracao': { partes: {
        'Soprador 1': { esp32: 'ete-soprador-1', inversor: 'pf-ete-01', tag_inversor: 'U21' },
        'Soprador 2': { esp32: 'ete-soprador-2', inversor: 'pf-ete-02', tag_inversor: 'U22' }
    } },
    'Torre de Resfriamento': { partes: {
        'Ventilador':            { esp32: 'torre-ventilador', inversor: 'pf-torre-01', tag_inversor: 'U31' },
        'Bomba de recirculacao': { esp32: 'torre-bomba',      inversor: 'pf-torre-02', tag_inversor: 'U32' }
    } },
    'Transporte 1': { partes: {
        'Motor 1': { esp32: 'transp-motor-1', inversor: 'pf-transp-01', tag_inversor: 'U41' },
        'Motor 2': { esp32: 'transp-motor-2' }
    } }
};
```

## O que cada ativo demonstra

| Ativo | Estado | O que mostra |
|---|---|---|
| **Caldeira 01** | ▲ ATENÇÃO | Limite cruzado (62 °C no ventilador de tiragem) — o caso comum |
| **ETE — Tanque de Aeração** | ■ CRÍTICO | Vibração acima de 1,0 g no Soprador 2 — a falha mecânica clássica |
| **Torre de Resfriamento** | ■ CRÍTICO | **Falha F008 no inversor** com todas as grandezas dentro da faixa |
| **Transporte 1** | ● OK | A referência do que é normal |

### O ativo que mais vale mostrar

A **Torre de Resfriamento** é o argumento mais forte da demonstração:
temperatura, vibração e corrente estão **todas verdes**, e o ativo está
crítico — porque o próprio inversor acusou sobretemperatura no dissipador.

Nenhum sistema baseado só em limites de vibração e temperatura pegaria
isso. É a fusão das três fontes (sensor + drive) fazendo diferença numa
tela.

### O segundo argumento: o limite é do motor, não do sistema

Abrindo a Torre, a ficha do ventilador mostra
`Limite de alarme: 36.5 / 44.6 A (90% / 110% da In)` — derivado da corrente
nominal de 40,5 A da placa daquele motor. O Transporte 1, com um motor de
8,2 A, tem limite de 7,4 / 9,0 A.

O mesmo painel cobra cada ativo pelo que ele é, sem ninguém configurar
limite a mão.

## Imagens

Em [`img/demo/`](img/demo/), na ordem em que eu apresentaria:

| # | Arquivo | O que mostra |
|---|---|---|
| 1 | `1-visao-geral.jpg` | A parede de cards: quatro ativos, quatro estados, alarmes no topo |
| 2 | `2-caldeira-atencao.jpg` | Detalhe da caldeira — atenção por temperatura, com o ventilador identificado |
| 3 | `3-ete-vibracao-critica.jpg` | Detalhe da ETE — vibração crítica no Soprador 2, os outros normais |
| 4 | `4-torre-falha-inversor.jpg` | **Detalhe da torre — crítico por falha do drive, grandezas todas verdes** |
| 5 | `5-transporte-normal.jpg` | Detalhe de um ativo saudável — a referência |
| 6 | `6-placa-sobressalentes.jpg` | Ficha de placa e sobressalentes, com o limite derivado da In |

### O que cada tela de detalhe contém

A mesma estrutura em todos os ativos — o que muda é o que os dados dizem:

1. **Cabeçalho** — nome, estado, marcha (`▶ rodando 60,0 Hz`), código de
   falha se houver, e a procedência (`sensor motor-01 · inversor U31`)
2. **Leituras agora** — seis valores: temperatura, vibração e corrente com
   barra contra o limite e estado; tensão, barramento CC e frequência como
   leitura de referência (sem limite, porque não são critério de alarme)
3. **Partes deste ativo** — uma linha por motor + a linha consolidada, com
   a coluna `Inversor` trazendo a TAG do drive no painel
4. **Dados de placa e sobressalentes** — ficha, foto da plaqueta e peças
5. **Gráficos** — temperatura, vibração e corrente ao longo do tempo, uma
   série por dispositivo
6. **Publicar agora** — força leitura imediata em todas as partes do ativo

### Capturar em resolução maior

As imagens do repositório estão em 1568×744, capturadas 1:1 (sem
reamostragem) e com o conteúdo ampliado para o texto ficar legível em
projeção. Servem para slide.

Se precisar de mais resolução, capture da sua tela com a demo rodando:

- **Windows:** `Win + Shift + S`
- Esconda a barra do navegador com **F11** antes de capturar
- Página inteira sem rolagem: `F12` → `Ctrl+Shift+P` → digite
  *"screenshot"* → **Capture full size screenshot**

O último gera um PNG da página toda na largura da janela — é o que rende
melhor em tela grande.
