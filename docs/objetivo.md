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
projeto adiciona uma terceira fonte de altíssimo valor **onde ela existe**:
a corrente do inversor — PowerFlex 525 por EtherNet/IP ou Danfoss VLT por
Modbus.

> O inversor é **bônus, não pré-requisito**. Vibração e temperatura já
> entregam valor em qualquer ativo rotativo; onde há drive na rede, soma-se
> a camada elétrica. No cadastro, o inversor é campo opcional.

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
PowerFlex 525 (corrente, se houver) --EIP-->    |  MQTT como barramento               + treino de modelos
                                     v
                                 Detecção de anomalia / diagnóstico
```

- **Edge (ESP32):** amostragem dos sensores e cálculo de *features* leves
  (RMS, pico) para não trafegar sinal bruto o tempo todo.
- **Borda (Orange Pi):** Mosquitto (broker MQTT) + Node-RED fazem a fusão dos
  sinais disponíveis (vibração e temperatura sempre; corrente quando há
  inversor), avaliação de limites, dashboard local e o primeiro nível de
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

## Velocidade (mm/s) e fator de crista — o que foi feito e o que vale

Duas medidas foram acrescentadas ao firmware porque são o padrão do mercado
(ver `diferenciais.md`) e custam pouco:

- **Velocidade RMS em mm/s.** É nesta unidade que a **ISO 20816-3** (antiga
  10816-3) julga severidade, com zonas A/B/C/D. "3,8 mm/s, zona C" comunica
  para qualquer mantenedor; "0,42 g" não diz nada a ninguém. Obtida por
  integração da aceleração, com passa-alta Butterworth de 2ª ordem em 10 Hz
  antes e depois da integral.
- **Fator de crista** (pico/RMS, por eixo, reporta o maior). Sobe *antes* do
  RMS quando um rolamento começa a falhar: os impactos elevam o pico sem
  mexer na energia média. Não tem limite de alarme de propósito — em estágio
  avançado ele **cai** de novo, quando os impactos viram ruído contínuo, e um
  limite fixo se calaria justo quando o defeito piorou. O que vale é a
  tendência.

### Como o grupo ISO é escolhido

A norma classifica por **potência ou altura de eixo (H)**, e os limites mudam
bastante entre grupos. O painel deriva isso da própria plaqueta — a carcaça
IEC já traz o H em milímetros (`132S/M` → H = 132 mm):

| Grupo | Critério | A/B | B/C | C/D |
|---|---|---|---|---|
| 1 rígida | > 300 kW ou H ≥ 315 mm | 2,3 | 4,5 | 7,1 |
| 1 flexível | idem, base flexível | 3,5 | 7,1 | 11,0 |
| 2 rígida | > 15 a 300 kW ou 160 ≤ H < 315 | 1,4 | 2,8 | 4,5 |
| 2 flexível | idem, base flexível | 2,3 | 4,5 | 7,1 |
| pequena | **abaixo do escopo da 20816-3** | 0,71 | 1,8 | 4,5 |

Valores conferidos contra as Tabelas A.1 e A.2 da **ISO 20816-3:2022**; a
linha "pequena" é a Classe I da ISO 10816-1, porque a 20816-3 só começa
acima de 15 kW.

**Isso não é detalhe acadêmico.** Um motor de 7,5 kW julgado pelo Grupo 2
usaria 2,8 mm/s como atenção onde o correto é 1,8 — o painel ficaria calado
no início da degradação justamente das máquinas mais numerosas de uma
planta. Base flexível não dá para adivinhar da plaqueta; assume-se rígida
(motor em base de concreto) e quem souber declara `iso_grupo` no cadastro.

⚠️ **Limitação honesta da banda.** A ISO 20816-3 (item 4.3) exige resposta
plana de **10 Hz a 1000 Hz**, e é nessa banda que valem os limites das
tabelas. Nós cobrimos de 10 Hz até ~metade da taxa de amostragem — hoje
~100 Hz, teto imposto pelo I²C do ADXL345. Portanto o número é *comparável
ao longo do tempo na mesma máquina* (que é como o usamos), mas **não é uma
medição certificada ISO**, e subestima máquina com energia forte acima de
100 Hz. Sair dessa limitação é o mesmo trabalho que destrava o degrau 3:
acelerômetro por SPI + FFT no edge.

Um detalhe a mais da norma: para máquina **abaixo de 600 rpm** a banda
começa em 2 Hz, não em 10. Nosso passa-alta fixo de 10 Hz cortaria a
fundamental dessas máquinas (10 Hz = 600 rpm). Não há nenhuma no escopo
atual, mas se entrar uma, `VIB_HP_HZ` precisa mudar para ela.

## Próximos passos

- [x] Leitura real do **PowerFlex 525** via EtherNet/IP — sidecar
      `integracoes/powerflex525`, publicando corrente, tensão, barramento
      CC, frequência, marcha e código de falha.
- [x] *Feature extraction* de vibração no edge: RMS, pico, **fator de
      crista** e **velocidade em mm/s** com zonas ISO 20816.
- [x] Buffer offline no ESP32 (240 amostras, com decimação quando enche) e
      *backfill* no painel — o dado medido durante queda de comunicação
      entra no histórico com o instante correto, sem disparar alarme ao vivo.
- [ ] FFT / espectro no edge — exige acelerômetro por SPI (o I²C limita a
      taxa) e, de preferência, ESP32-S3 (é o único da linha com otimização
      de FFT em assembly no `esp-dsp`).
- [ ] Baseline + detecção de anomalia por ativo (degrau 2).
- [ ] Persistência do histórico (banco na borda + sincronização com a nuvem).
- [ ] Roadmap para diagnóstico espectral (degrau 3) e nó de vibração dedicado.
