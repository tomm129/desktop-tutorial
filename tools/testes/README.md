# Testes

Oito suítes que rodam sem hardware, sem broker e sem banco — 223
verificações, mais a checagem de compilação do firmware. Existem porque os
erros que este projeto já teve não eram erros de digitação — eram de
**cálculo**, de **contagem** e de **leitura de manual**, o tipo que passa
despercebido na leitura do código e só aparece em produção.

```bash
python tools/testes/testa_vibracao.py            # matematica da vibracao
python tools/testes/testa_inversores.py          # logica dos sidecars + MCSA
python tools/testes/testa_danfoss_modbus.py      # Danfoss contra drive simulado
python tools/testes/testa_powerflex_cip.py       # PowerFlex contra drive simulado
python tools/testes/testa_servico_inversores.py  # servico unico: as duas marcas + config ao vivo
python tools/testes/checa_firmware.py            # o C++ compila limpo?
python nodered/gera_flow.py                      # (gera antes dos de baixo)
node   tools/testes/valida_flow.js  nodered/flows.json
node   tools/testes/testa_painel.js nodered/flows.json
```

Os dois testes de drive simulado precisam das bibliotecas dos **sidecars**
(`pip install pycomm3 pymodbus`); os simuladores em si não precisam de nada.

## `testa_danfoss_modbus.py` e `testa_powerflex_cip.py` — a conversa com o drive

Sobem os drives simulados de `tools/simuladores/` — os **mesmos** que se
usam à mão — e leem deles pelo sidecar, por Modbus TCP e EtherNet/IP de
verdade. Cobrem o que a lógica pura não alcança: a chamada da biblioteca
(o pymodbus trocou `unit=` por `slave=` e depois por `device_id=`), a
quantidade de registradores pedida para cada tipo, o envelope CIP.

Foram conferidos por **mutação**: reintroduzindo cada bug que a leitura dos
manuais achou — parâmetro de 16 bits lido como 32, escala do barramento,
falha histórica como ativa, atributo errado na classe DPI —, o teste
reprova. Cenários do PowerFlex: drive normal e desarmado, drive que aceita e
que recusa o envelope Unconnected Send, as duas classes de parâmetro e o
drive sem objeto de falha.

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
- **menu Inversores**: o nó que grava a lista valida e salva, recusa
  conflito sem gravar, mantém o `id` ao editar e avisa ao remover um drive
  que ainda está associado a um ativo; ao reativar ou editar um item, o
  conflito é atribuído a **ele**, nunca ao vizinho que já funcionava;
- estados da lista (lendo / sem resposta / aguardando / recusado) —
  inclusive o drive recém-cadastrado que ainda tem um `offline` retido de
  antes, que tem de aparecer como "aguardando", não em vermelho;
- o validador do painel (JS) e o do serviço (Python) rodam os **mesmos
  casos** de `casos_validacao_inversores.json` e têm de dar as mesmas
  mensagens.

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
- O **esquema** do PostgreSQL já rodou no gateway real, mas nenhuma
  medição real foi gravada; aqui se verifica a coerência do SQL montado.
- Os sidecars do **PowerFlex** e do **Danfoss** foram conferidos contra os
  manuais oficiais e testados contra drives **simulados** — nunca contra um
  drive real. O simulador e o sidecar partem da **mesma** leitura do
  manual: o teste prova que o código faz o que o manual diz, não que o
  drive se comporta como o manual diz. Isso só a bancada fecha (roteiros
  nos READMEs de `integracoes/`).
- A **sonda de MCSA** foi validada contra dado sintético. Se o filtro
  interno do drive apaga a modulação de 2·s·f, isso só se descobre num
  motor real.
- A **renderização** das telas não é testada aqui — isso exige o Node-RED
  no ar.
