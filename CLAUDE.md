# CLAUDE.md — Contexto do Projeto: InsightX (monitoramento de condição)

Lido automaticamente pelo Claude Code ao abrir esta pasta. Contém decisões já
tomadas e bugs já resolvidos — **não repita esses diagnósticos, aplique as
conclusões direto**.

## O que é

**InsightX** — monitoramento de condição de equipamento rotativo industrial.
Dois lados:

- **Campo (ESP32):** temperatura (MLX90614 infravermelho, sem contato) e
  vibração (ADXL345), publicando JSON por MQTT.
- **Painel (Orange Pi):** broker Mosquitto + Node-RED Dashboard 2.0 + banco.
  Lê corrente do inversor **onde houver um**, e apresenta tudo.

**O inversor é um PLUS, não requisito.** Decisão explícita do usuário: o
produto tem que funcionar sem drive nenhum na rede. Na tela de cadastro a
adição do inversor é opcional, e ~1/3 dos ativos do teste de escala não têm.
Não reescrever a proposta de valor como se drive fosse obrigatório — isso já
foi corrigido uma vez no material de investidor.

## Estado real do projeto — não maquiar

Tecnicamente maduro, **comercialmente em zero**: nenhuma instalação, nenhum
piloto, nenhuma carta de intenção. Está escrito sem maquiagem no
`docs/INVESTIDOR.md` e é a única linha daquele documento que muda tudo quando
mudar. O maior risco não é técnico, é dispersão — começar coisa nova antes de
o primeiro piloto existir.

## Estrutura

| Pasta | O quê |
|---|---|
| `firmware/esp32-campo/` | firmware atual (PlatformIO, framework Arduino) |
| `firmware/ixnode-provisionamento/` | firmware ESP-IDF novo — provisionamento (SoftAP + portal cativo + NVS) |
| `nodered/` | **`gera_flow.py` gera o flow** — ver aviso abaixo |
| `integracoes/powerflex525/` | corrente via EtherNet/IP (CIP) |
| `integracoes/danfoss_vlt/` | corrente via Modbus TCP/RTU |
| `sql/` | esquema TimescaleDB + migração |
| `tools/` | simulador, gerador de planta, sonda MCSA |
| `tools/testes/` | suíte de verificação — rodar antes de commitar |
| `docs/` | arquitetura, hardware, investidor, diferenciais, revisão crítica |

Branch de trabalho: `claude/iot-monitoring-repo-18ccwm`. Remoto
`tomm129/desktop-tutorial` (**privado**).

## ⚠️ O flow do Node-RED é GERADO

`nodered/gera_flow.py` (~3800 linhas) **gera** o JSON do flow. Editar o JSON
direto é trabalho perdido — a próxima geração sobrescreve. Toda alteração de
painel se faz no gerador.

## Preferência do usuário: ESP-IDF, não Arduino

Declarada explicitamente. O firmware de campo atual usa o framework Arduino
por herança; o caminho é migrar. **Decisão tomada: o FIFO em rajada (abaixo)
entra direto no firmware ESP-IDF**, portando sensor e buffer junto, em vez de
ser feito duas vezes. No IDF dá para amarrar a amostragem a timer de hardware
ou I²S, que é o que o FIFO precisa para não voltar a depender de `delay`.

Terminologia: é "firmware do ESP32 escrito com o framework Arduino" — o chip
sempre foi ESP32; Arduino é só a camada de API.

## Bugs resolvidos — não rediagnosticar

### Velocidade 33% baixa — RESOLVIDO

Três passa-altas de 1ª ordem em cascata atenuavam demais na banda. Trocado por
**Butterworth de 2ª ordem a 10 Hz** → erro caiu para **1,4%**.
**Achado por teste numérico, não por leitura de código** — revisão visual não
pega erro de resposta em frequência. Estrutura em `Biquad` no `main.cpp`.

### Integração trapezoidal errava 25% a 100 Hz — RESOLVIDO

Substituída por mistura de regras discretas com pesos **(7/8, 1/8)**
(`INT_C0`/`INT_C1`) → erro máximo **1,8%** na banda.

### Widget inteiro sumia no painel — RESOLVIDO

Um `tile_simples` **sem o campo `tend`** fazia o Vue apagar o **widget
inteiro**, não só o tile. Corrigido dos dois lados: `tend` neutro na geração +
guarda `v-if` no template. Lição: no Dashboard 2.0, campo ausente em um item
derruba o conjunto.

### "O painel está errado" — era o simulador mentindo

Ativos marcados como normais apareciam em ATENÇÃO. **O painel estava certo**:
motores de 7,5 kW caem no perfil ISO `peq`, cujo limite de atenção é 1,8 mm/s.
Antes de acusar o painel, conferir o perfil ISO derivado da plaqueta.

### Formulário de edição do cadastro fechava sozinho — RESOLVIDO

A guarda do watcher era `!this.novos.find(...)`, e um dispositivo já
cadastrado **nunca** está em `novos` — então fechava sempre. Corrigido com
`!this.editando`.

### `IDF_TARGET=esp32s3` no ambiente sobrescrevia `idf.py set-target`

Silenciosamente. A primeira compilação saiu para o chip errado. Conferir a
variável de ambiente antes de culpar o `set-target`.

### aedes 1.x é ESM-only e precisa de `await Aedes.createBroker()`

`new Aedes()` aceita a conexão TCP mas **nunca manda CONNACK** — o sintoma é
"connack timeout" no cliente, que parece problema de rede e não é.

### Gráfico de tendências colapsava com 45 séries — RESOLVIDO

Ver `docs/teste-de-escala.md` para o caso completo. O painel elege **até 8
séries**, piores primeiro. Três armadilhas que valem mais que o conserto:

1. **Desempate instável** — o `ui-chart` **acumula** séries; ordenar por
   "visto por último" fazia a legenda crescer sem limite. Desempate por ID.
2. **Lista única para dois tipos** — ESP32 e inversor no mesmo ranking fazia
   drives ocuparem as vagas do gráfico de temperatura, que eles não publicam.
   A eleição é **separada por tipo**.
3. **Guarda permissiva na inicialização** — deixar tudo passar nos ~2 s
   iniciais envenenava a legenda **para sempre**. A guarda é **estrita**:
   melhor gráfico vazio por dois segundos.

### Validadores devolvem `undefined`, não `null`

`valida_vel`/`valida_crista` devolvem `undefined` para ausente. Isso é
deliberado: evita alarme falso em firmware antigo que ainda não publica o
campo. Não "corrigir" para `null`.

## Fatos verificados externamente — pode confiar

- **ISO 20816-3:2022** — zonas A/B/C/D, Grupos 1/2, suporte rígido/flexível,
  banda 10–1000 Hz (2 Hz abaixo de 600 rpm). Conferido contra o PDF da norma.
  Máquina pequena usa ISO 10816-1 Classe I. O perfil sai da **plaqueta**
  (`altura_eixo()` faz o parse da carcaça IEC).
- **Danfoss** — grupo 16 de parâmetros conferido nos guias oficiais. O **FC
  302 tem 16-16/16-17**; o **FC 51 não tem**. Perfis por família em
  `integracoes/danfoss_vlt`.
- **Rolamento por envelope** — banda 500–5000 Hz, mínimo **12.800 S/s**.
- **MCSA de verdade** exige ≥5 kHz e resolução de 0,01–0,05 Hz — fora do
  nosso alcance hoje. A alternativa viável é **envelope modulado em 2·s·f**.
- **ADXL345** — FIFO de 32 amostras, ODR até 3200 Hz. Leitura em rajada dá
  **~7.400 S/s contra os 370 S/s atuais**.

## Laço de teste local — usar antes de afirmar que funciona

Node-RED + broker aedes + simulador, dirigido pelo Chrome com screenshot.
**Pegou bugs que revisão estática não pegaria** (widget em branco, texto
cortado, imagem quebrada, gráfico colapsado). Não declarar painel OK sem
rodar.

```bash
python tools/gera_planta_teste.py 24            # planta grande
python tools/simulador_campo.py --do-cadastro --intervalo 3
python tools/gera_planta_teste.py --restaurar   # devolve o cadastro
```

Suíte: `tools/testes/` — `testa_vibracao.py` (12), `testa_inversores.py` (32),
`testa_painel.js` (47), `valida_flow.js`, `checa_firmware.py`.

## Nunca versionar

Já está no `.gitignore` e **tem que continuar**: `dados/ativos.json` e o
backup `.antes-do-teste`, `dados/fotos/*`, `firmware/esp32-campo/include/config.h`,
`integracoes/**/config.env`, `.claude/settings.local.json`. O repo é privado,
mas isso é dado de cliente e credencial. Cuidado com `git add -A` — já
comitou um backup de cadastro uma vez.

## Regras de visualização

Matiz categórico em ordem fixa, **nunca ciclado** — acima de 8 séries agrupa,
filtra ou usa small multiples, jamais gera cor nova. Cores de status são
reservadas. Nunca eixo duplo.

## Prioridade revisada (após a revisão adversarial em `docs/revisao-critica.md`)

1. **FIFO do ADXL345 em rajada, no firmware ESP-IDF** — esforço baixo, 20× na
   taxa de amostragem, fecha a lacuna da ISO 20816 e traz os **120 Hz** (2×
   frequência de linha) para dentro da banda. É a melhor relação do roadmap.
2. **Endurecer o armazenamento do gateway** — risco de desgaste do eMMC.
3. **Gravar e testar o firmware ESP-IDF** no ESP32-**C6** do usuário.
4. **Sonda de MCSA** (`tools/mcsa_sonda.py`) num FC 302 real.
5. **Resolver a contradição** entre `objetivo.md` (degrau 4) e
   `diferenciais.md` (on-premise).
6. **Bancada com o FC 51** (o usuário tem um em casa, com RS-485).

Não testado no teste de escala e é o que degrada **silenciosamente**: carga no
gateway (77 dispositivos ≈ 26 msg/s, Node-RED é laço de thread única). O
sintoma aparece como "o painel está travando", sem apontar a causa.

## Escopo — não expandir sem pedir

Sem RainMaker, Alexa, Home Assistant. O produto é o painel local + campo. Ideia
adjacente já discutida e **não iniciada**: tela de **OEE / máquina parada**,
que vende mais fácil que preditiva (ROI aritmético em vez de probabilístico) e
usa a mesma infraestrutura. Fica para depois do primeiro piloto.

## Ambiente desta máquina

- **ESP-IDF v5.4.4** em `C:\esp\v5.4.4\esp-idf`.
- Python: **3.14** é o do PATH (`C:\Python314`) e tem a stack do projeto
  (`numpy`, `paho-mqtt`, `littlefs-python`). **Não instalar coisa pesada nele**
  — usar venv com o 3.12, senão quebra a suíte de teste.
- **O disco C: vive cheio** (chegou a 0,1 GB de 465 GB). Com o **Storage Sense
  ligado**, o Windows apaga arquivo sozinho e sem avisar — já evaporou um venv
  inteiro no meio de uma sessão. Conferir espaço antes de qualquer instalação.
- `idf.py monitor` não funciona aqui (sem TTY) — usar script de monitor serial.
