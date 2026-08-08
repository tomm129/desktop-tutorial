# Revisão crítica — 2026-08-08

Revisão adversarial das decisões de engenharia, feita com o Kimi Code (K3)
como revisor independente e verificada aqui. O objetivo era atacar as
decisões, não validá-las — um revisor que só concorda não serve.

Abaixo só o que **sobreviveu à verificação**, com o que fazer a respeito.

---

## 1. A taxa de amostragem é 20× menor do que precisa ser — e o limite não é o sensor

**Este é o achado mais importante.**

Hoje o firmware lê o ADXL345 **uma amostra por transação I²C**, com
`delayMicroseconds` entre elas, e chega a ~370 amostras/s (banda útil
~100 Hz). Está documentado como "limite do I²C".

**Não é.** O ADXL345 tem **FIFO de 32 amostras** e ODR até 3200 Hz. Lendo em
rajada pelo FIFO, a conta muda completamente:

| Modo | Amostras/s | Banda útil |
|---|---|---|
| Hoje (uma por transação, com delay) | ~370 | ~100 Hz |
| Teto teórico amostra-a-amostra @ 400 kHz | ~4.900 | ~1.200 Hz |
| **Rajada de FIFO @ 400 kHz** | **~7.400** | **~1.800 Hz** |
| Teto do próprio sensor (ODR máx.) | 3.200 | 1.600 Hz |

Ou seja: mesmo sem trocar sensor nem interface, dá para chegar ao **teto do
ADXL345 (3200 Hz)**, com banda de 1600 Hz. Isso **fecha a lacuna da ISO
20816-3**, que exige resposta plana até 1000 Hz e hoje é nossa limitação
declarada.

### O corolário que dói

A **2× frequência de linha (120 Hz)** está fora da nossa banda atual.

É onde se manifestam mecanicamente as falhas **elétricas**: folga, problema
de estator, barra de rotor. Temos um produto cujo diferencial é assinatura
elétrica — e a manifestação mecânica dessas falhas cai **logo acima** do que
conseguimos ver. Frequência de passagem de pás em ventilador com muitas pás
também.

**Ação:** reescrever a aquisição para usar o FIFO do ADXL345 com leitura em
rajada. **Esforço baixo, impacto alto.** É a melhor relação do roadmap
inteiro, e sobe de prioridade acima do nó com acelerômetro SPI.

---

## 2. O eMMC do Orange Pi é o maior risco de confiabilidade

PostgreSQL + TimescaleDB gravando continuamente num eMMC de placa de US$ 35,
sem ECC, sem no-break, sem watchdog documentado.

eMMC de consumo tem ciclos de escrita contados. Telemetria a cada 5 s de N
sensores, mais o WAL do Postgres, é carga de escrita constante. E queda de
energia no meio de uma escrita corrompe.

**A promessa "o dado fica na planta" morre junto com uma placa de US$ 35.**

**Ações, da mais barata para a mais cara:**

- `synchronous_commit = off` e ajuste de WAL — perde-se no máximo alguns
  segundos numa queda, e reduz muito a escrita
- backup diário para fora da placa
- watchdog de hardware
- rootfs em modo leitura com overlay
- monitorar o desgaste (`Lifetime writes` do ext4) e expor no painel
- **NVMe** onde a placa tiver M.2 (o Orange Pi 5 tem)

**Esforço baixo, impacto alto.**

---

## 3. Contradição entre a tese de negócio e o degrau 4 do roadmap

O `objetivo.md` promete o **degrau 4 — prognóstico (RUL)**, que exige
histórico de máquinas que falharam **com registro** (run-to-failure).

O `diferenciais.md` promete **dado on-premise, sem nuvem**.

**As duas coisas não convivem.** Instalações isoladas nunca agregam o
conjunto de dados de falha que o degrau 4 exige. É justamente esse conjunto
o fosso da Tractian — milhares de máquinas alimentando um modelo comum.

Não é fatal, mas precisa de decisão consciente. Os caminhos:

1. **Assumir que o degrau 4 não é nosso** — parar no diagnóstico (degrau 3),
   que já é muito, e não prometer RUL.
2. **Sincronização opcional de frota** — on-premise por padrão, com o
   cliente podendo optar por contribuir dados anonimizados em troca de
   modelos melhores. Preserva a promessa e destrava o degrau 4.

**Ação:** decidir, e alinhar os dois documentos. Hoje eles se contradizem.

---

## 4. Node-RED como camada de aplicação — certo para MVP, errado como destino

Riscos reais: laço de eventos de thread única, exceção não tratada em um nó
derruba o runtime inteiro, lógica de negócio presa numa ferramenta visual, e
o editor exposto na mesma porta do painel.

Sintoma que confirma: o `flows.json` é **gerado** por `gera_flow.py`, e há
uma suíte de testes só para validar o JSON gerado. Isso é contorno de uma
inadequação, não elegância.

**A trajetória certa já começou:** o sidecar do PowerFlex foi tirado de
dentro do Node-RED de propósito. O caminho é continuar — ingestão e alarme
viram serviço versionado, e o Node-RED fica só como dashboard.

**Esforço médio.** Não é urgente, mas não deve ser esquecido.

---

## O que NÃO se sustentou

Sendo justo com as decisões que estão certas:

- **Integração no domínio do tempo para o mm/s.** O revisor sugeriu domínio
  da frequência (dividir por jω e usar Parseval). É elegante e correto —
  mas exige FFT, que exige a taxa maior do item 1. Para um escalar em
  streaming, o filtro IIR é a escolha certa, e os testes já mostram 1,4% de
  erro. Fica como opção *depois* do item 1, não em vez dele.

- **"O portal cativo deveria ter vindo depois do acelerômetro SPI."**
  Discordo. Provisionamento é **bloqueio de produto** — sem ele não se
  instalam vinte nós numa planta, e nenhuma capacidade técnica compensa
  isso. FFT é capacidade; provisionamento é pré-requisito de venda.

- **Wi-Fi como transporte.** O risco de escala é real e está documentado (a
  própria Tractian migrou para 915 MHz), mas o caso deles era bateria +
  densidade. Com nó alimentado da rede, perto do painel, e sem trafegar
  forma de onda, Wi-Fi resolve a v1. Vale projetar de forma agnóstica ao
  rádio, não trocar agora.

---

## Prioridade revisada

| # | Ação | Esforço | Por quê |
|---|---|---|---|
| 1 | **FIFO do ADXL345 em rajada** | baixo | 20× na taxa, fecha a banda ISO, traz os 120 Hz para dentro |
| 2 | **Endurecer o armazenamento do gateway** | baixo | é o maior risco de confiabilidade do produto |
| 3 | **Gravar e testar o firmware ESP-IDF em placa** | baixo | compilar não é validar; nada rodou ainda |
| 4 | **Validar a sonda de MCSA em motor real** | médio | decide se o diferencial nº 1 existe de fato |
| 5 | **Decidir degrau 4 × on-premise** | baixo | os documentos se contradizem hoje |
| 6 | Tirar a lógica do Node-RED | médio | dívida de arquitetura, não urgência |
| 7 | Nó com acelerômetro SPI + FFT | alto | só necessário *depois* do item 1 |

O item 1 rebaixou o item 7: boa parte do ganho que justificava trocar de
sensor está disponível sem trocar nada.

---

## Fontes

- [Envelope Analysis — Vibromera](https://vibromera.eu/glossary/envelope-analysis/) — banda de 500–5000 Hz para defeito de rolamento
- [Why Sampling Rate Matters in Bearing Vibration Monitoring — IoT Bearings](https://iotbearings.com/why-sampling-rate-matters-bearing-vibration-monitoring/) — mínimo de 12.800 amostras/s para envelope
- [Bearing Fault Frequencies — Vibromera](https://vibromera.eu/glossary/bearing-fault-frequencies/) — BPFO/BPFI e harmônicas
- ISO 20816-3:2022, item 4.3 — resposta plana exigida de 10 Hz a 1000 Hz
- Datasheet do ADXL345 (Analog Devices) — FIFO de 32 amostras, ODR até 3200 Hz
