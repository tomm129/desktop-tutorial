# Testes

Quatro verificações que rodam sem hardware, sem broker e sem banco. Existem
porque os erros que este projeto já teve não eram erros de digitação — eram
de **cálculo** e de **contagem**, o tipo que passa despercebido na leitura e
só aparece em produção.

```bash
python tools/testes/testa_vibracao.py            # matematica da vibracao
python tools/testes/testa_inversores.py          # drivers de inversor + MCSA
python tools/testes/checa_firmware.py            # o C++ compila limpo?
python nodered/gera_flow.py nodered/flows.json   # (gera antes dos de baixo)
node   tools/testes/valida_flow.js  nodered/flows.json
node   tools/testes/testa_painel.js nodered/flows.json
```

## `testa_vibracao.py` — a matemática

Reimplementa em Python o cálculo de `medirVibracao()` e confere contra
sinais sintéticos cuja resposta é conhecida **analiticamente**: senoide de
amplitude e frequência dadas, sinal 1x+2x, offset DC, impulso periódico.

Foi o que pegou o erro grave: a primeira versão usava três passa-altas de 1ª
ordem em cascata e reportava velocidade **33% abaixo** do valor correto —
número plausível, gráfico bonito, e completamente errado. Trocado por
Butterworth de 2ª ordem, o erro caiu para 1,4%.

Também é o que escolheu a regra de integração: o trapézio, que é a escolha
reflexa, erra 25% em 100 Hz; a mistura `(7/8, 1/8)` erra 1,8%.

**Se mexer no filtro, no integrador ou na taxa de amostragem, rode isto.**

## `checa_firmware.py` — o C++ compila?

Extrai a matemática direto do `main.cpp` (sem cópia, que envelheceria) e
compila com o cross-compiler da Espressif, com `-Wall -Wextra`. Não executa —
quem valida o algoritmo é o teste acima. Aqui se pega typo, tipo errado,
declaração faltando.

Pula com aviso se não achar compilador.

## `valida_flow.js` — o flow gerado é coerente?

1. Checa a **sintaxe** de todo JavaScript embutido nos nós `function` do
   `flows.json` (13 blocos hoje). Sem isto, um erro de sintaxe só aparece no
   deploy do Node-RED.
2. Confere que a contagem de colunas do `INSERT INTO medicoes` bate com o
   tamanho de **cada** array de valores montado.

O item 2 existe por causa de um bug real: a query declarava 18 colunas e as
linhas tinham 19. Os `$n` desalinhavam **a partir da segunda linha** — ou
seja, nunca no teste com um dispositivo, sempre em produção.

## `testa_painel.js` — a lógica do painel funciona?

Executa o código real dos nós contra mensagens simuladas. Cobre:

- amostra ao vivo com os campos novos (velocidade, crista);
- **firmware antigo** sem esses campos — tem de virar `undefined`, não
  `null`, senão todo dispositivo não atualizado entraria em "sem leitura" e
  alarmaria falso no dia do deploy;
- backfill não pode encostar no estado ao vivo (valor crítico de duas horas
  atrás não dispara alarme agora);
- reconstrução do timestamp a partir de `atraso_ms`;
- duas quedas distantes viram faixas separadas na linha do tempo;
- rejeição de valores fisicamente impossíveis;
- teto da fila de backfill.

## `testa_inversores.py` — drivers de inversor e sonda de MCSA

Lógica pura, sem hardware:

- **Danfoss**: conversão de parâmetro (PNU) em registrador Modbus, e
  decodificação da palavra de alarme — que é um *campo de bits*, com vários
  alarmes ao mesmo tempo, diferente do número único do PowerFlex.
- **Sonda de MCSA** (`tools/mcsa_sonda.py`): contra séries sintéticas com
  jitter e quantização de 0,01 A realistas, verifica que ela **acha** a raia
  de barra quebrada (até 0,4% de modulação), **não confunde** uma oscilação
  de carga em 0,8 Hz com o 2·s·f esperado, e **não inventa** raia num motor
  sadio.

O teste do Danfoss só passou a existir de verdade depois de um conserto: o
sidecar tinha `import paho` no topo com `sys.exit` em caso de falta, o que
tornava o módulo impossível de importar sem a biblioteca. A suíte pulava os
testes **em silêncio**, dando impressão de que passavam. Dependência pesada
agora é importada só na hora de usar.

## O que estes testes **não** cobrem

Sendo explícito, para ninguém confundir "passou" com "funciona":

- O firmware **nunca foi compilado inteiro** nem gravado — não há
  PlatformIO nesta máquina. Só a matemática foi compile-checada.
- A escrita real no **PostgreSQL** não foi executada; o que se verifica é a
  coerência do SQL montado.
- O caminho **CIP/EtherNet-IP** do PowerFlex nunca tocou um inversor real.
- O sidecar **Danfoss** também não. Em especial, a regra de conversão
  PNU → registrador e as escalas de cada parâmetro **precisam ser
  conferidas contra o display do drive** — o teste garante que o código
  calcula o que diz calcular, não que a fórmula seja a certa para a família
  em uso.
- A **sonda de MCSA** foi validada contra dado sintético. Se o filtro
  interno do drive apaga a modulação de 2·s·f, isso só se descobre num
  motor real.
- A **renderização** das telas não é testada aqui — isso exige o Node-RED
  no ar.
