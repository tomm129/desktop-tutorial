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

Em [`img/demo/`](img/demo/):

| Arquivo | Tela |
|---|---|
| `1-visao-geral.jpg` | Parede de cards com os quatro estados e a faixa de alarmes |
| `2-detalhe-falha-inversor.jpg` | Torre de Resfriamento — falha do drive com grandezas normais |
| `3-placa-sobressalentes.jpg` | Dados de placa e lista de sobressalentes |

### Capturar em resolução maior

As imagens do repositório servem de referência. Para apresentação em
projetor, capture da sua própria tela com a demo rodando — sai na resolução
nativa do monitor:

- **Windows:** `Win + Shift + S`
- Esconda a barra do navegador com **F11** (tela cheia) antes de capturar
- Para a página inteira sem rolagem: `F12` → `Ctrl+Shift+P` → digite
  *"screenshot"* → **Capture full size screenshot**

O último gera um PNG da página toda, na largura da janela — é o que rende
melhor em slide.
