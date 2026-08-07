# InsightX — material para conversa com investidor

> Levantamento de 2026-08-07. Este documento existe para ser **derrubável**:
> tudo que é fato tem fonte, tudo que é estimativa está marcado como
> estimativa e traz o método, e o que ainda não sabemos está listado no fim.
>
> Um material que só apresenta o lado bom não sobrevive a vinte minutos de
> conversa com quem investe a sério — e queima a confiança em tudo que veio
> antes. Este é escrito para o caso contrário.

---

## 1. Em cinco minutos

Monitoramento de condição de ativos rotativos existe e é bem servido —
Tractian, WEG e SEMEQ estão nesse mercado. Todos medem vibração e
temperatura, todos mandam o dado para a nuvem deles, todos cobram
assinatura.

O InsightX faz **duas coisas que nenhum deles faz**:

1. **Deixa o dado dentro da planta**, num PostgreSQL local, sem nuvem e sem
   mensalidade. Funciona com a internet caída.
2. **Lê a assinatura elétrica real do motor** — corrente, tensão, barramento
   CC e código de falha — direto do inversor por EtherNet/IP ou Modbus,
   **quando o ativo tem um**. Isso desempata diagnóstico que vibração
   sozinha não resolve.

**O inversor é um bônus, não um pré-requisito.** O produto monitora
vibração e temperatura em qualquer ativo rotativo, como os concorrentes; onde
existe drive na rede, ele ganha uma camada elétrica que nenhum deles tem. Na
tela de cadastro o inversor é campo **opcional** — o ativo funciona sem ele.

Isso importa para o dimensionamento de mercado: o endereçável é o parque
rotativo inteiro, e o inversor define onde a proposta é **mais forte**, não
onde ela é possível.

**Estágio: protótipo em bancada.** Nada em produção ainda. O que existe está
detalhado na seção 3, sem maquiagem.

---

## 2. O mercado

### 2.1 Números que têm fonte

| Indicador | Valor | Fonte |
|---|---|---|
| Mercado global de manutenção preditiva (2024) | **US$ 10,9 bi** | Fortune Business Insights |
| Projeção 2032 | **US$ 70,7 bi** | Fortune Business Insights |
| CAGR global | **~22% a.a.** | MetaTech Insights |
| Crescimento do mercado **brasileiro** até 2031 | **24,2% a.a.** | InfraFM |
| Custo anual de paradas não planejadas na indústria (global) | **~US$ 50 bi** | Exactitude Consultancy |

### 2.2 O vento a favor no Brasil, específico

A idade média das máquinas na indústria brasileira de transformação e
extrativa é de **14 anos**, e **38% do parque está no fim ou além da vida
útil** indicada pelo fabricante (ABIMAQ).

Isso importa mais para nós do que o tamanho do mercado: máquina velha falha
mais, e é onde monitoramento de condição paga mais rápido. É também a
população que **menos** justifica a troca por equipamento novo com telemetria
embarcada — ou seja, precisa de retrofit, que é o que fazemos.

### 2.3 A validação mais dura: um concorrente bem financiado

A **Tractian levantou US$ 196 milhões** no total, sendo **US$ 120 mi na
Série C** (nov/2024), liderada pela Sapphire Ventures, com General Catalyst,
Next47 e NGP Capital.

Isso é faca de dois gumes, e a conversa honesta reconhece os dois:

- **A favor:** ninguém precisa ser convencido de que o mercado existe. Uma
  Série C desse porte, com fundos desse calibre, num player brasileiro, já
  fez a validação por nós.
- **Contra:** é um concorrente com capital, marca e time comercial que nós
  não temos. Competir de frente na mesma proposta seria suicídio. Por isso a
  tese é de **diferenciação técnica em um nicho** (ativo com inversor, dado
  on-premise), não de disputa aberta.

### 2.4 O nosso mercado endereçável — em duas camadas

O endereçável **não** se limita a ativo com inversor. O produto monitora
vibração e temperatura em qualquer máquina rotativa; o drive é uma camada
adicional. Então o mercado tem dois anéis:

| Anel | O que é | Nossa proposta ali |
|---|---|---|
| **Base** | qualquer ativo rotativo com energia no ponto de medição | dado on-premise, sem assinatura — competimos por **modelo**, não por tecnologia |
| **Núcleo** | os que têm inversor em rede | + assinatura elétrica e código de falha — competimos por **capacidade que ninguém tem** |

A estratégia comercial decorre disso: **entrar pelo núcleo** (onde a
diferenciação é técnica e demonstrável em uma visita) e **expandir para o
anel base** dentro do mesmo cliente, onde o argumento passa a ser custo e
propriedade do dado.

**Não consegui a base instalada de inversores no Brasil em fonte pública
confiável.** Poderia estimar por consumo de energia e vendas anuais de
drives, mas a margem sairia tão larga que não sustentaria decisão nenhuma —
e número inventado em pitch é o que se descobre na diligência.

**O método para levantar de verdade**, quando valer o esforço:

1. Vendas anuais de inversores no Brasil (ABINEE / ABIMAQ, dado associativo)
2. × vida útil média do drive (10–15 anos) = base instalada
3. × fração em plantas com rede industrial até o painel
4. × ticket por ativo monitorado

Para o anel base, a conta é outra e mais simples: número de plantas-alvo ×
ativos críticos por planta. Ambas se resolvem melhor **de baixo para cima**,
com um cliente real, do que com TAM de relatório.

Enquanto isso não existe, a conversa deve ser conduzida **de baixo para
cima**: quantos ativos tem a planta X, quanto custa uma parada dela, quanto
ela pagaria. É argumento mais forte que TAM de relatório, e é verificável.

---

## 3. Onde estamos de verdade

Sendo explícito, porque é o que dá credibilidade ao resto.

### O que existe e funciona

- **Painel completo e operacional**: hierarquia ativo → parte → grandeza,
  alarmes com histerese, linha do tempo de eventos, cadastro de
  dispositivos, dados de placa e sobressalentes, tema escuro.
- **Firmware ESP32** com RMS de vibração por eixo, **velocidade em mm/s com
  zonas ISO 20816** derivadas da plaqueta, **fator de crista**, e buffer
  offline com decimação (não perde dado durante queda de rede).
- **Dois sidecars de inversor**: Allen-Bradley PowerFlex 525 (EtherNet/IP) e
  Danfoss VLT série FC (Modbus TCP/RTU), publicando o **mesmo contrato JSON**
  — o painel não sabe a marca.
- **Histórico em PostgreSQL + TimescaleDB** na borda, com agregados
  contínuos, compressão e retenção.
- **Suíte de testes sem hardware**: 91 verificações automatizadas.

### O que NÃO existe

| | Situação |
|---|---|
| Instalação em planta real | **nenhuma** |
| Firmware gravado em placa | **não** — nunca compilado inteiro (sem PlatformIO na máquina de desenvolvimento) |
| Sidecar testado em inversor real | **não** — nem o PowerFlex nem o Danfoss |
| Escrita real no PostgreSQL | **não** — o SQL foi inspecionado, não executado |
| Análise espectral (FFT) | **não** — é o degrau 3 do roadmap |
| Certificação Ex / área classificada | **não** |
| Invólucro e grau de proteção | **não definido** |
| Cliente pagante ou carta de intenção | **nenhum** |

### A tradução honesta disso

É um **protótipo maduro em arquitetura e imaturo em campo**. As decisões
técnicas estão tomadas e documentadas, o software está escrito e testado no
que dá para testar sem hardware, e o que falta é confronto com a realidade —
que é justamente onde projetos assim costumam morrer.

Quem investe nesse estágio está apostando na tese e na execução, não em
tração. O documento que finge o contrário perde o investidor que sabe ler.

---

## 4. O produto e por que ele é diferente

O comparativo completo, com specs verificadas na documentação de cada
fabricante (manual, datasheet, registro FCC), está em
[`diferenciais.md`](diferenciais.md). O resumo:

| | InsightX | WEGscan | Tractian | SEMEQ |
|---|---|---|---|---|
| Corrente elétrica real | **sim**, se houver drive | campo magnético (proxy) | não | sensor à parte |
| Código de falha do drive | **sim**, se houver drive | não | não | não |
| Intervalo de medição | **5 s** | periódico | 10–30 min | ~1 h |
| Dado fica na planta | **sim** | nuvem | nuvem | nuvem |
| Assinatura | **não** | sim | sim | serviço |
| Instalação | precisa de cabo | 10 min | 3 min | 3 min |
| Análise espectral | **não** (roadmap) | sim | sim | sim |

Os dois últimos itens são onde perdemos, e estão na tabela de propósito.

---

## 5. Modelo de negócio — três caminhos, ainda em aberto

Não está decidido, e este documento apresenta os três em vez de fingir
convicção. Cada um muda o produto, não só o preço.

### A) Venda de hardware, software incluso

Cliente compra os nós e o gateway. Sem mensalidade.

**A favor** — é o que mais contrasta com os três concorrentes, e resolve
duas objeções reais de compra: custo previsível e nenhuma dependência de
fornecedor. Casa com o argumento de dado on-premise.

**Contra** — receita não recorrente. Investidor de SaaS desconta pesado
múltiplo de hardware. E cada real de receita exige uma venda nova.

### B) Hardware + assinatura de software

Equipamento mais mensalidade por ativo monitorado.

**A favor** — receita recorrente, previsível, e é o modelo que o mercado de
capital premia. Financia suporte e evolução.

**Contra** — **contradiz o que hoje está escrito no `diferenciais.md`**
("sem assinatura" é listado como diferencial). Escolher este caminho exige
reescrever aquele documento, e perder o argumento contra os três
concorrentes. Não dá para ter os dois.

### C) Serviço de monitoramento

Você instala, opera e entrega laudo — o modelo da SEMEQ.

**A favor** — ticket maior por cliente, e a barreira deixa de ser
tecnológica e passa a ser a competência de análise, que é mais difícil de
copiar.

**Contra** — escala com gente, não com software. Múltiplo de empresa de
serviço, não de tecnologia. E exige analista de vibração, que é o produto
real da SEMEQ e não temos.

### Recomendação para a conversa

Enquanto não houver um cliente pagante, **o modelo é hipótese** — e
apresentá-lo como decidido convida a uma pergunta que ainda não se pode
responder ("qual seu churn? qual seu CAC?"). É mais forte dizer: *"os três
caminhos estão mapeados, com o trade-off explícito, e a escolha vem do
primeiro piloto."*

---

## 6. Por que agora

1. **Retrofit ficou barato.** ESP32 com Wi-Fi custa poucos dólares;
   acelerômetro MEMS idem. A conta que não fechava há dez anos fecha hoje.
2. **O inversor virou padrão e já fala rede.** PowerFlex fala EtherNet/IP,
   Danfoss fala Modbus — a fonte de dados elétricos que ninguém lê já está
   instalada e paga.
3. **O parque brasileiro envelheceu.** 14 anos de média, 38% além da vida
   útil (ABIMAQ). Máquina velha é onde preditiva paga mais rápido.
4. **O mercado foi validado por terceiros.** A Série C da Tractian tirou a
   dúvida sobre existir demanda.

---

## 7. Barreira de entrada — e a resposta honesta

**A pergunta que vai vir:** "por que a Tractian não faz isso amanhã?"

A resposta sincera é que **tecnicamente ela poderia**. A barreira não é
patente nem segredo — é de **foco e de modelo**:

- Ler o inversor exige falar EtherNet/IP e Modbus, entrar na rede industrial
  do cliente e lidar com a política de TI dele. É trabalho chato, específico
  por marca, e conflita com a proposta de valor deles: *instala em 3 minutos,
  sem cabo, sem TI*.
- Dado on-premise **contradiz o modelo de assinatura em nuvem** que sustenta
  a receita recorrente deles. Não é algo que se acrescente sem canibalizar.

Ou seja: a barreira é que fazer o que fazemos **estragaria o produto deles**.
É uma barreira real, mas não é permanente — vale para o nicho, não para o
mercado inteiro.

---

## 8. Riscos, sem filtro

| Risco | Gravidade | Mitigação |
|---|---|---|
| Nada validado em campo | **alta** | piloto é o próximo passo; sem ele não há conversa |
| Concorrente com US$ 196 mi | **alta** | não competir de frente; nicho de ativo com inversor |
| Instalação exige cabo | média | mirar ativo que já tem painel e energia — o inversor é opcional, a energia não |
| Sem análise espectral | média | limita o diagnóstico ao degrau 2; roadmap definido |
| Wi-Fi em planta metálica | média | a própria Tractian migrou para 915 MHz — o caminho é conhecido |
| Modelo de negócio indefinido | média | decidir no primeiro piloto, não antes |
| Fundador único / bus factor | **alta** | documentação do repositório é a mitigação parcial |

---

## 9. O que precisa ser levantado antes da próxima conversa

Estes números não existem ainda, e **dependem de dados que só a operação
fornece** — não de pesquisa:

- [ ] **Custo do nó** (BOM real: ESP32-S3 + acelerômetro + sensor de
      temperatura + invólucro + montagem)
- [ ] **Custo do gateway** (Orange Pi + fonte + invólucro)
- [ ] **Tempo de instalação** medido, não estimado
- [ ] **Preço que uma planta pagaria** — levantado com um cliente real, não
      calculado por margem
- [ ] **Custo de uma parada** num ativo típico do cliente-alvo — é o número
      que sustenta o ROI, e ele varia de 10× entre setores
- [ ] **Base instalada de inversores no Brasil** (ABINEE/ABIMAQ)
- [ ] **Piloto em planta** com os FC 301/302 disponíveis

O item que mais muda a conversa é o **piloto**. Ele transforma toda a seção
3 de "não existe" em "está rodando há N meses e pegou X".

---

## Fontes

- [Predictive Maintenance Market — Fortune Business Insights](https://www.fortunebusinessinsights.com/predictive-maintenance-market-102104) — mercado global 2024 e projeção 2032
- [Predictive Maintenance Market — MetaTech Insights](https://www.metatechinsights.com/pt/industry-insights/predictive-maintenance-market-1942) — CAGR
- [Manutenção preditiva cresce no Brasil — InfraFM](https://www.infrafm.com.br/Textos/0/24327/Manutencao-preditiva-cresce-no-Brasil-e-impulsiona-eficiencia-energetica-em-edificios-e-setores) — crescimento brasileiro de 24,2% a.a.
- [Mercado de Manutenção Preditiva — Exactitude Consultancy](https://exactitudeconsultancy.com/pt/relat%C3%B3rios/21572/mercado-de-manuten%C3%A7%C3%A3o-preditiva/) — custo de paradas não planejadas
- [Sobre a necessidade de renovação do parque de máquinas no Brasil — ABIMAQ](https://abimaq.org.br/blogmaq/1688/sobre-a-necessidade-de-renovacao-do-parque-de-maquinas-no-brasil) — idade média de 14 anos, 38% além da vida útil
- [Tractian Raises $120M in Series C — WilmerHale](https://launch.wilmerhale.com/research/news-publications/20241219-tractian-raises-$120m-in-series-c-funding) — rodada e investidores
- [TRACTIAN funding — Tracxn](https://tracxn.com/d/companies/tractian/__vIv7VxpWYbnuHWuozg9ietz-MLAI3YQQvtNJLGnf71Q/funding-and-investors) — total captado

Specs dos concorrentes: ver as fontes de [`diferenciais.md`](diferenciais.md),
todas de documentação oficial dos fabricantes.
