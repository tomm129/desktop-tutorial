# InsightX — diferenciais frente aos concorrentes

> Levantamento de 2026-08-07. Todas as especificações de terceiros vêm de
> documentação pública do próprio fabricante (manuais, datasheets, registro
> FCC). As fontes estão no fim. Onde não consegui confirmar, está escrito
> que não consegui — **este documento não serve se exagerar**.

## Por que este documento existe

Para responder, com número e fonte, a duas perguntas que aparecem em toda
conversa comercial e em toda reunião de investidor:

1. *"Isso não é o que a Tractian/WEG/SEMEQ já faz?"*
2. *"Por que alguém compraria de vocês em vez deles?"*

A resposta honesta tem três partes: onde somos **melhores**, onde somos
apenas **diferentes**, e onde somos **piores**. Um documento que só lista
vitórias é inútil — o interlocutor acha o buraco em cinco minutos e perde a
confiança em tudo que veio antes.

---

## 1. O quadro comparativo

| | **InsightX** | **WEGscan 100** | **Tractian Smart Trac** | **SEMEQ** |
|---|---|---|---|---|
| Rádio do sensor | Wi-Fi 2,4 GHz (MQTT) | BLE 5.1 | Wi-Fi 802.11 b/g/n → 915 MHz (ger. atual) | BLE 5.1 |
| Uplink | **nenhum — fica na planta** | gateway → nuvem | Receiver → LTE → nuvem | gateway → nuvem |
| Alimentação | rede elétrica | bateria Li-SOCl₂, ~1 ano | bateria lítio **não trocável**, 3 anos | bateria, 3 anos |
| Intervalo de medição | **5 s** (config. até 2 s) | periódico, configurável | 10 min (ger. 1) / 30 min | ~1 h (720/mês) |
| Vibração — aceleração | 16 g, ~100 Hz de banda | 16 g, 13,3 kHz | 16 g, 1 Hz–32 kHz | 10 kHz |
| Vibração — velocidade | **mm/s, zonas ISO 20816** | não publicado | sim | sim |
| Fator de crista | **sim** | não publicado | sim | não publicado |
| FFT / espectro | ✗ roadmap | 12288 linhas | 4096 linhas/eixo | sim |
| **Corrente elétrica** | **real, do inversor** | campo magnético (proxy) | ✗ | sensor separado |
| MCSA (espectro da corrente) | ✗ — ver §2.1 | ✗ | ✗ | ✗ |
| Tensão / barramento CC | **sim** | ✗ | ✗ | ✗ |
| Código de falha do drive | **sim** | ✗ | ✗ | ✗ |
| Buffer offline | **240 amostras, com decimação** | 1 mês no sensor | 250 amostras | — |
| Banco de dados | **PostgreSQL local, seu** | nuvem WEG | nuvem Tractian | nuvem SEMEQ |
| Modelo comercial | **sem assinatura** | assinatura | assinatura | serviço + analistas |
| Grau de proteção | ⚠️ a definir | IP66 | IP69K | IP69K |
| Área classificada (Ex) | ✗ | variantes Ex | Smart Trac Ex, Zona 1/21 | — |
| Instalação | ⚠️ **precisa de cabo** | M4, ~10 min | adesivo, ~3 min | adesivo |

---

## 2. Onde somos genuinamente melhores

### 2.1 Corrente elétrica de verdade — o diferencial mais forte

Nenhum dos três lê a **assinatura elétrica** do motor pelo inversor. É a
maior lacuna do mercado de monitoramento de condição, e é exatamente onde
estamos.

| | O que mede |
|---|---|
| WEGscan | campo magnético — um *proxy* de corrente, sem escala absoluta |
| Tractian | nada elétrico no sensor |
| SEMEQ | tem sensor de corrente, mas é **outro produto**, comprado à parte |
| **InsightX** | corrente, tensão, barramento CC, frequência, marcha e **código de falha**, lidos do PowerFlex 525 por EtherNet/IP |

**Por que isso vale tanto:** vibração sozinha é ambígua. A vibração subiu —
é desbalanceamento mecânico ou problema elétrico? A corrente desempata. E dá
a **carga real**, que separa "vibrou porque está forçando" de "vibrou porque
está quebrando".

Some-se o **código de falha do próprio drive**: quando o inversor desarma, o
painel já mostra `F005 — sobretensão` em vez de "o ativo ficou mudo". O
concorrente, nesse mesmo instante, mostra um sensor que parou de responder.

E isso sai **de graça** em hardware: o inversor já está lá, já mede tudo
isso para se controlar, e já fala EtherNet/IP. Só ninguém estava lendo.

#### ⚠️ O que ainda NÃO é MCSA — e por quê

Uma versão anterior deste documento dizia que a leitura de corrente habilita
MCSA (*Motor Current Signature Analysis*) para barra de rotor quebrada. **Isso
estava errado, e a correção importa** — é o tipo de afirmação que um cliente
técnico derruba na primeira pergunta.

A MCSA clássica procura bandas laterais em `f_s·(1 ± 2ks)`. Para um motor de
4 polos a 60 Hz e 1760 rpm, ficam em 57,3 e 62,7 Hz. Separá-las da
fundamental exige resolução de 0,01–0,05 Hz (janela de 20 a 100 s) e
amostragem de **pelo menos 5 kHz** do sinal de corrente.

Pelo inversor isso é impossível, por dois motivos independentes:

1. **O parâmetro `b003` é corrente RMS** — um escalar que o drive já
   integrou. A portadora de 60 Hz não está mais lá; amostrar rápido não
   recupera o que foi descartado.
2. **Mensageria explícita faz uma ida-e-volta por leitura.** O sidecar hoje
   lê a 1 Hz. Nem com otimização isso chega perto de 5 kHz.

**A hipótese que continua viva:** barra quebrada também **modula a
amplitude** da corrente, e o envelope oscila em `2·s·f_s` — ~2,7 Hz no motor
acima. A corrente RMS *é* essencialmente esse envelope. Se o filtro interno
do drive não a tiver apagado, bastaria amostrar a ~12 Hz por 60 s.

Isso é testável, e a sonda existe: `tools/mcsa_sonda.py`. Validada contra
dados sintéticos com quantização e jitter reais — detecta modulação de 0,4%
a 33× acima do piso, e distingue corretamente uma oscilação de carga em
0,8 Hz de uma raia em 2,7 Hz. **Falta rodar num motor real.**

Se o drive tiver matado a modulação, o caminho para MCSA de verdade é
**TC no cabo do motor + ADC do ESP32 a alguns kHz** — hardware novo, e a
decisão deve esperar o resultado da sonda.

### 2.2 Medição contínua, não amostragem periódica

A bateria dos concorrentes impõe o intervalo. A Tractian mede a cada 10
minutos; a SEMEQ, cerca de uma vez por hora. Nós medimos a cada 5 segundos.

Isso não é vaidade de número. É o que se **perde** entre as janelas:

- partida e parada do motor (o pico de corrente de partida é diagnóstico);
- batida de carga, embuchamento, cavitação intermitente;
- o transiente que precede o desarme.

Um amostrador de 10 minutos vê 0,17% do tempo. Nós vemos tudo. Para tendência
de longo prazo, o intervalo deles basta — mas para **entender o que
aconteceu numa parada**, não.

### 2.3 O dado não sai da planta

Os três são serviço em nuvem com mensalidade. Nós somos on-premise:
PostgreSQL + TimescaleDB no Orange Pi, dentro da fábrica.

Isso resolve três objeções reais de compra:

- **Restrição de dados.** Há planta que não exporta telemetria de processo,
  por política ou por contrato. Para essas, os três concorrentes estão fora
  antes da conversa técnica começar.
- **Custo previsível.** Sem mensalidade por sensor, o custo é o hardware.
- **Sem refém.** Se o fornecedor sumir, a planta continua com o banco.

E funciona **sem internet**: o painel, os alarmes e o histórico rodam
inteiros na borda. Nos três concorrentes, cair a internet é cair o produto.

### 2.4 Aberto por construção

MQTT, PostgreSQL, Node-RED — tudo padrão. Consequências práticas:

- **Power BI** conecta nativo no PostgreSQL (não existe conector de MQTT);
- **Grafana** para gráfico de engenharia;
- integração com ERP/CMMS é um `SELECT`, não uma negociação de API.

### 2.5 Hierarquia de ativo com placa e sobressalentes

O painel modela **Ativo → Parte → Grandeza** (Transporte 1 → Motor 1 →
temperatura + inversor U1), e cada parte carrega dados de placa e lista de
sobressalentes com foto da plaqueta.

Isso fecha o ciclo que os outros deixam aberto: eles dizem *"o rolamento
está falhando"*; nós dizemos *"o rolamento está falhando, o código é
6208-ZZ, e é este o motor"*. E a corrente nominal da placa deixa de ser
decoração: ela vira **o limite de alarme daquele ativo** (90%/110% da In),
em vez de um número fixo no código que não serve para dois motores
diferentes.

### 2.6 Buffer offline com decimação

Ambos guardamos dado durante queda de comunicação — a Tractian, 250
amostras. A diferença está no que acontece quando o buffer enche: um anel
comum descarta o mais antigo e preserva só os últimos minutos, perdendo
justamente o **início** da queda, que é onde está a pista.

Nosso buffer **decima**: descarta uma amostra sim, outra não, dobrando o
período coberto pela metade da resolução. Uma queda longa fica registrada
inteira, mais grossa. Cada amostra carrega o próprio instante, então o
espaçamento irregular não atrapalha o banco nem o gráfico.

E o painel marca esse trecho na linha do tempo como **recuperado** — nem
"tudo bem", nem "buraco". Quem analisa precisa saber que naquele período o
dado existe mas o **alarme não rodou**.

---

## 3. Onde somos apenas diferentes (nem melhor, nem pior)

- **Wi-Fi contra BLE/sub-GHz.** Wi-Fi dá alcance de infraestrutura já
  existente e não exige gateway proprietário. Em compensação, a própria
  Tractian **abandonou** Wi-Fi 2,4 GHz (30–50 m, 15 sensores por receiver)
  em favor de 915 MHz (1 km, 100 sensores) — sinal claro de onde o Wi-Fi
  trava quando a planta cresce. Para uma instalação de um galpão, Wi-Fi
  resolve; para uma planta inteira, esse é o próximo problema.
- **Alimentação de rede.** Custa cabo e eletricista, e ganha medição
  contínua e nenhuma manutenção de bateria. É troca, não vitória.

---

## 4. Onde somos piores — e o que fazer a respeito

Ser honesto aqui é o que dá credibilidade ao resto.

| Lacuna | Situação | Caminho |
|---|---|---|
| **Instalação** | eles: adesivo, 3 min, sem cabo. Nós: precisa de alimentação | posicionar para ativo **com inversor** (onde já há painel e energia) — que é exatamente onde nosso diferencial de corrente existe |
| **Banda de vibração** | nosso mm/s cobre ~10–100 Hz; a norma pede 10–1000 Hz; eles vão a 32–64 kHz | limite do ADXL345 por I²C. Resolve com acelerômetro SPI + ESP32-S3 e FFT no edge |
| **Sem FFT/espectro** | eles diagnosticam BPFO/BPFI/BSF/FTF; nós ainda não | degrau 3 do roadmap; depende do item acima |
| **Sem certificação Ex** | eles têm variantes para área classificada | mercado que não atacamos agora |
| **Grau de proteção** | eles: IP66–IP69K validado. Nós: invólucro ainda não definido | decisão de produto pendente |
| **Sem analistas** | a SEMEQ vende laudo de especialista humano | é outro negócio (serviço), não produto |

**A lacuna de banda merece nota.** O `mm/s` que reportamos é medido entre
10 Hz e cerca de metade da taxa de amostragem (~100 Hz hoje). A ISO 20816
define 10–1000 Hz. Portanto: o número é **comparável ao longo do tempo na
mesma máquina** — que é o que importa para tendência e é como o usamos — mas
**não é medição certificada ISO**, e subestima máquina com conteúdo forte
acima de 100 Hz. Dizer o contrário seria mentir para um cliente que sabe
conferir.

---

## 5. O que copiamos deles (de propósito)

Engenharia validada em campo é de graça; ignorá-la por orgulho seria burrice.

| Origem | O que trouxemos |
|---|---|
| Tractian | **fator de crista** como medida publicada; velocidade em mm/s; buffer offline; portal cativo para provisionamento; OTA dos sensores pelo gateway |
| WEG | **ISO 20816** como norma de posicionamento do sensor; fixação M4 com torque de 4 Nm em bucha recartilhada; invólucro **não-metálico** (é o que permite antena interna sem furar o IP) |
| SEMEQ | transmissão **por evento + heartbeat** (manda quando muda, e manda sempre a cada N para provar que está vivo) |

O ponto sobre o invólucro merece destaque porque inverte uma premissa comum:
o conflito não é entre antena e vedação, é entre antena e **metal**. O
WEGscan é IP66 com antena interna porque a caixa é de policarbonato. Caixa
plástica resolve os dois problemas de uma vez.

---

## 6. Resumo para uma conversa de cinco minutos

> Monitoramento de condição existe e é bem servido por Tractian, WEG e
> SEMEQ. Todos medem vibração e temperatura, todos vendem assinatura, todos
> mandam o dado para a nuvem deles.
>
> Nós fazemos duas coisas que nenhum deles faz: lemos a **assinatura
> elétrica real** do motor pelo inversor que já está instalado — o que
> desempata diagnóstico que vibração sozinha não resolve — e deixamos o
> **dado dentro da planta**, num banco padrão, sem mensalidade e sem
> internet.
>
> Em troca, exigimos alimentação elétrica e ainda não fazemos análise
> espectral. Por isso miramos o ativo que tem inversor: é onde já há energia
> e é onde nosso diferencial existe.

---

## Fontes

Especificações de terceiros, todas de documentação pública:

- [Manual de Instalação Mecânica WEGscan 100 (PDF)](https://static.weg.net/medias/downloadcenter/hb1/h5d/WEG-WEGscan100-installation-manual-10010754124-pt.pdf) — invólucro plástico, fixação M4/4 Nm, ISO 20816, Anatel 13320-22-07908
- [Sensor de Vibração Industrial: guia WEGscan 100 — Blog WEG](https://www.weg.net/digital/blog/sensor-de-vibracao-industrial-wegscan100/) — 16 g, 13,3 kHz, 12288 linhas, Bluetooth 5, Li-SOCl₂
- [SENSOR IOT WEGscan 100-1-MFM — CSA Automação](https://loja.csaautomacao.com.br/produto/sensor-iot-wegscan-100-1-mfm/) — IP66, policarbonato, BLE 5.1, 56×62×34 mm
- [Smart Trac Datasheet (PDF) — Tractian](https://tractian-webpage.s3.amazonaws.com/website/pages/sensor-inteligente/en/Datasheet_EN.pdf) — Wi-Fi 802.11 b/g/n, 3 anos, IP69K, 4096 linhas/eixo, 250 amostras offline, M6, encapsulamento em resina
- [Sensor de Vibração — Tractian](https://tractian.com/sensor-tractian) — geração atual: 915 MHz/4G, 1 km, 100 sensores, até 64 kHz
- [Smart Trac Ex — Tractian](https://tractian.com/blog/smart-trac-ex-sensor-iot-areas-classificadas) — IP68, Ex Zona 1/21
- [Sensor wireless — SEMEQ](https://semeq.com/pt/sensor-wireless-para-manutencao-preditiva/) — 10 kHz de resposta, 25,6 kHz de amostragem, 3 anos, IP69K
- [Gateway Fusion Sensor — SEMEQ](https://semeq.com/en/product/gateway-fusion-sensor/) — BLE 5.1, uplink Ethernet/Wi-Fi/3G/4G, OPC e Modbus
- [Sensor de Corrente — SEMEQ](https://semeq.com/pt/product/sensor-de-corrente/) — BLE 5.1, transmissão por limiar + periódica

**Não confirmado:** o chip de rádio de nenhum dos três. O registro FCC do
WEGscan 100 existe (ID `2BDMZ-WEGSCAN100`) mas o site que hospeda as fotos
internas bloqueou os acessos. A inferência de que a WEG usa um SoC BLE
dedicado (e não um ESP32) vem do orçamento de energia — Li-SOCl₂ com um ano
de autonomia não sustenta os picos de corrente do Wi-Fi —, não de leitura
direta do componente.
