# Objetivo do projeto

## Visão

Uma plataforma **aberta** de monitoramento de condição de ativos rotativos
(motores, bombas, ventiladores) que une o melhor de duas abordagens que hoje
vivem separadas — **aquisição de dados + nuvem** e **sensoriamento de vibração
e temperatura** — e adiciona uma camada de **IA** para evoluir do *monitorar*
para o *prever*: manutenção preditiva em (quase) tempo real.

> Em uma frase: unir aquisição/nuvem + sensoriamento de vibração/temperatura,
> e colocar IA em cima dos dados para antecipar falhas.

## Referências de mercado e o gap

| Abordagem            | Faz bem                                   | Limite                                   |
|----------------------|-------------------------------------------|------------------------------------------|
| Coleta + nuvem       | Adquire sinais de chão de fábrica e sobe  | Não foca em diagnóstico de vibração      |
| Sensor de vibração   | Vibração + temperatura + preditiva        | Sensor "por fora", sem a corrente do drive |

O que este projeto quer é **juntar os dois** e ainda somar um diferencial que
nenhum dos dois entrega de forma nativa.

## O diferencial: fusão multissensor (corrente + vibração + temperatura)

A maioria das soluções de condição olha **vibração + temperatura**. Este
projeto adiciona uma terceira fonte de altíssimo valor: **a corrente do
inversor PowerFlex 525 (via EtherNet/IP)**.

Isso habilita **MCSA — Motor Current Signature Analysis**, que revela falhas
que a vibração externa nem sempre distingue:

- barra de rotor quebrada;
- excentricidade de entreferro;
- desbalanceamento/assimetria elétrica de fase;
- estimativa indireta de carga/torque.

A fusão **corrente + vibração + temperatura** reduz a ambiguidade do
diagnóstico. Exemplo clássico: a vibração subiu — é desbalanceamento mecânico
ou problema elétrico? A assinatura da corrente desempata.

## Roadmap: a escada de maturidade da preditiva

"IA preditiva" não é uma coisa só; é uma escada. Cada degrau tem um custo de
dado diferente. A estratégia é entregar valor desde o degrau 1 e subir
conforme se acumula histórico.

| # | Degrau                | O que entrega                              | Precisa de                         | Status       |
|---|-----------------------|--------------------------------------------|------------------------------------|--------------|
| 1 | Monitorar             | Valor + limites (ISO 10816, ΔT)            | Só o sensor                        | **Feito** ✅ |
| 2 | Detecção de anomalia  | "Fora do normal desta máquina"             | ~2–4 semanas de operação normal    | Próximo      |
| 3 | Diagnóstico           | "É rolamento / desbalanceamento / rotor"   | Análise espectral + assinaturas    | Médio prazo  |
| 4 | Prognóstico (RUL)     | "Falha provável em ~X dias"                | Histórico de falhas reais          | Longo prazo  |

Ponto-chave: o degrau 4 (o que as pessoas imaginam ao ouvir "IA preditiva")
exige **dados de máquinas que falharam com registro** (run-to-failure), que
quase nenhum site tem no início. Por isso começamos pelos degraus **2 e 3**,
que funcionam **sem histórico de falha** (não supervisionado + regras), e
acumulamos dado para o degrau 4.

## Arquitetura de dados — o que roda onde

```
[ Campo ]                         [ Painel / Borda ]              [ Nuvem ]
ESP32 (MLX90614 + ADXL345)  --->  Orange Pi (Node-RED + Mosquitto)  --->  Armazenamento
   |  features leves no edge         |  fusão, limites, dashboard          + histórico
PowerFlex 525 (corrente) --EIP-->    |  MQTT como barramento               + treino de modelos
                                     v
                                 Detecção de anomalia / diagnóstico
```

- **Edge (ESP32):** amostragem dos sensores e cálculo de *features* leves
  (RMS, pico) para não trafegar sinal bruto o tempo todo.
- **Borda (Orange Pi):** Mosquitto (broker MQTT) + Node-RED fazem a fusão dos
  três sinais, avaliação de limites, dashboard local e o primeiro nível de
  anomalia. Funciona mesmo sem internet.
- **Nuvem:** histórico de longo prazo, treino de modelos e visão de frota.
  A borda continua operando se a nuvem cair (resiliência).

## Pipeline de IA

1. **Feature extraction**
   - Vibração: RMS, pico, *crest factor*, *kurtosis*, FFT/espectro.
   - Corrente (MCSA): espectro da corrente, bandas laterais.
   - Temperatura: nível e tendência (ΔT sobre baseline / ambiente).
2. **Baseline + anomalia (não supervisionado)** — aprende o "normal" de cada
   ativo e sinaliza desvios. Não precisa de falha registrada.
3. **Diagnóstico (regras + assinaturas)** — mapeia padrões espectrais para
   modos de falha conhecidos (rolamento, desbalanceamento, desalinhamento,
   folga, barra de rotor).
4. **Prognóstico / RUL (supervisionado)** — quando houver histórico de falhas,
   estima vida útil remanescente.

## Limitações conhecidas de hardware

- **ADXL345:** excelente para **RMS / severidade global** de vibração
  (degraus 1–2), mas limitado para **diagnóstico fino de rolamento** (degrau
  3), que exige frequências altas (kHz). I²C + ODR baixo são o teto aqui.
  Evolução natural: nó dedicado com acelerômetro melhor (ADXL355 ou IEPE
  piezo) e FFT no edge, amostrando em kHz.
- **MLX90614:** temperatura sem contato (IR), ótima para superfície do motor;
  atenção à emissividade e ao campo de visão.

## Próximos passos

- [ ] Leitura real da corrente do **PowerFlex 525** via EtherNet/IP no
      Node-RED (hoje é um nó de exemplo).
- [ ] Adicionar *feature extraction* de vibração (RMS/FFT) — decidir edge vs
      borda.
- [ ] Baseline + detecção de anomalia por ativo (degrau 2).
- [ ] Persistência do histórico (banco na borda + sincronização com a nuvem).
- [ ] Roadmap para diagnóstico espectral (degrau 3) e nó de vibração dedicado.
