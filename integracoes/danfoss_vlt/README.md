# Sidecar Danfoss VLT (FC 51, FC 301, FC 302)

Lê a telemetria de um inversor Danfoss por Modbus e publica **exatamente o
mesmo JSON** que o sidecar do PowerFlex 525. O painel não sabe a marca —
esse é o ponto.

> **Estado:** conferido contra os guias oficiais da Danfoss e testado contra
> um drive simulado por Modbus TCP de verdade. **Ainda não rodou num drive
> real.** Faça a bancada abaixo antes de ligar em produção.

## O que a documentação oficial confirmou

| Ponto | Resultado | Fonte |
|---|---|---|
| Endereço do registrador | `(PNU × 10) − 1` ✅ | FC 51 Design Guide, §8.9.1 |
| Largura | 16 bits = **1** registrador, 32 bits = **2** | idem |
| Tipo e escala de cada parâmetro | tabela abaixo | FC 301/302 Programming Guide, lista de parâmetros |
| Bits da palavra de alarme 16-90 | 32 bits mapeados | FC 301/302 Programming Guide, tabela *Alarm Word* |

**Três bugs da primeira versão, achados nessa conferência** — todos teriam
passado despercebidos até a bancada:

1. **Tudo era lido como 32 bits.** Seis dos nove parâmetros comuns são de
   16 bits. Pedir 2 registradores de um parâmetro de 16 bits junta o valor
   com a palavra seguinte, ou dá erro de endereço. Como a frequência é
   campo essencial, o sidecar entraria em **loop de reconexão eterno** sem
   publicar nada.
2. **O número do bit foi confundido com o número do alarme.** O código
   mostrava o bit 13 (falha de *inrush*) como "Sobrecorrente", que é o
   bit 5. Uma sobrecorrente real teria aparecido com o nome errado.
3. **Torque é `Int16`, não `Int32`.** Com a leitura antiga, torque de
   frenagem (negativo) saía como número absurdo.

## O que é lido

| Par. | Parâmetro | JSON | Tipo | Escala | FC 301/302 | FC 51 |
|---|---|---|---|---|---|---|
| 16-13 | Frequency | `frequencia_hz` | Uint16 | 0,1 Hz | ✅ | ✅ |
| 16-14 | Motor current | `corrente_a` | Int32 | 0,01 A | ✅ | ✅ |
| 16-12 | Motor Voltage | `tensao_v` | Uint16 | 0,1 V | ✅ | ✅ |
| 16-30 | DC Link Voltage | `dc_bus_v` | Uint16 | 1 V | ✅ | ✅ |
| 16-10 | Power [kW] | `potencia_kw` | Int32 | 0,01 kW | ✅ | ✅ ⚠️ |
| 16-18 | Motor Thermal | `motor_termico_pct` | Uint8 | 1 % | ✅ | ✅ |
| 16-34 | Heatsink Temp. | `dissipador_c` | Uint8 | 1 °C | ✅ | ✅ |
| 16-03 | Status Word | `status_bruto` | V2 | — | ✅ | ✅ |
| 16-90 | Alarm Word | `falha` + `alarme_bruto` | Uint32 | — | ✅ | ✅ ⚠️ |
| **16-17** | **Speed [RPM]** | `rpm` | Int32 | 1 rpm | ✅ | ❌ |
| **16-16** | **Torque [Nm]** | `torque_nm` | Int16 | 0,1 Nm | ✅ | ❌ |

⚠️ No FC 51 o guia não tabela os tipos, só a **faixa** de cada parâmetro — e
a faixa decide a largura (16-14 vai até 1856,00 A = 185600, que não cabe em
16 bits). Dois pontos ficam para a bancada: a escala da 16-10 e o mapa de
bits da 16-90, que o guia do FC 51 não publica.

### Duas leituras do manual que enganam

- **Índice de conversão ≥ 67 não é escala**, é o designador da unidade. A
  tabela mostra `67 → 1/60` para rpm, mas isso é rpm convertido para
  rotações por segundo (SI). O inteiro chega em rpm. Idem `100` = °C.
- **O índice é relativo à unidade-base.** A 16-10 tem índice `1`, que é
  "×10 W" — ou seja, **0,01 kW** por unidade, e não "×10 kW".

### Alarmes: vários ao mesmo tempo

O PowerFlex entrega **um número** de falha. O Danfoss entrega uma **palavra
de bits**, onde vários alarmes convivem. O sidecar reporta o menor bit
ativo como `falha.codigo` e junta todos os textos em `falha.texto`. Cada
texto traz o número do alarme como aparece no display do drive —
`Sobrecorrente (A13)` —, e a palavra crua vai em `alarme_bruto`.

## Por qual porta ler

| Drive | Caminho recomendado | Por quê |
|---|---|---|
| **FC 51** | **RS-485 embutido** (terminais 68/69) | é a única porta de rede que ele tem |
| **FC 301/302** | **RS-485 embutido** (terminais 68/69) | não mexe na placa de rede que o CLP usa |

A placa de rede dos seus FC 301/302 fala com o CLP da linha. **Não é
preciso tocá-la**: a porta RS-485 embutida é independente e aceita Modbus
RTU (`8-30 = [2]`). Ler por ela é invisível para o CLP.

> A versão anterior deste README dizia que Modbus TCP era a **MCA 121**. O
> guia do FC 301/302 confirma que a **MCA 121 é EtherNet/IP**. Se um dia
> quiser ler pela rede Ethernet em vez do RS-485, confira no drive qual
> placa está montada (parâmetro 15-60 *Option Mounted*) antes de escolher o
> protocolo.

## Ligação física (os dois modelos)

```
Adaptador USB-RS485          Drive Danfoss
      A / D+   ─────────────  68  (P: TX+/RX+)
      B / D−   ─────────────  69  (N: TX−/RX−)
      GND      ─────────────  61  (comum / malha)
```

- **Terminação:** ligue a chave **BUS TER** do drive em **ON** se ele
  estiver na ponta do cabo. Padrão de fábrica: **OFF**.
- **Malha do cabo** no terminal 61, que já vai ao chassi por um circuito RC.
- Cabo par trançado com malha. Para bancada, um metro de qualquer par
  trançado serve.

> Se nada responder, a primeira suspeita é **A e B invertidos**. A
> nomenclatura dos adaptadores não é padronizada. Inverter os dois fios não
> queima nada.

## Parâmetros do drive

| Par. | Ajuste | Padrão de fábrica |
|---|---|---|
| **8-30** Protocol | **`[2] Modbus RTU`** | `[0] FC` ← **tem de mudar** |
| 8-31 Address | 1 (igual a `DANFOSS_UNIT`) | 1 |
| 8-32 Baud Rate | `[2] 9600` | 9600 no FC 51 |
| 8-33 Parity | `[0] Even Parity, 1 Stop Bit` | Even, 1 stop |

> ⚠️ **Mudar o 8-30 só vale depois de desligar e religar o drive** — está
> escrito no manual dos dois modelos. Se continuar mudo, é isso.
>
> **Na fábrica isso importa:** religar um FC 301/302 de produção exige uma
> parada da linha. Combine com a manutenção antes. E confira que a porta
> RS-485 não está sendo usada por outra coisa (MCT 10, IHM externa) antes
> de trocar o protocolo.

## Roteiro de bancada — o FC 51 que você tem em casa

Tudo **do PC**, sem Orange Pi e sem broker. O sidecar só **lê** o drive:
não escreve nenhum parâmetro, não dá partida, não muda referência.

**1. Instale** (uma vez):

```bash
pip install pymodbus pyserial
```

**2. Ligue o adaptador USB-RS485** nos terminais 68/69/61 e descubra a porta
COM no Gerenciador de Dispositivos (ex.: `COM5`).

**3. No drive:** `8-30 = [2] Modbus RTU`, **desligue e religue**.

**4. Rode a bancada** (PowerShell):

```powershell
$env:DANFOSS_FAMILIA="fc51"; $env:DANFOSS_TRANSPORTE="rtu"; $env:DANFOSS_SERIAL="COM5"
python integracoes/danfoss_vlt/danfoss_mqtt.py --bancada
```

Sai uma tabela com cada parâmetro: endereço, tipo, valor bruto e valor com
escala. **Coloque o display do drive em cada parâmetro e compare.**

**5. O que conferir, nesta ordem:**

1. **Com o motor parado:** tensão do barramento (16-30) deve bater com o
   display — em 220 V monofásico, ~310 V. É o teste mais fácil porque o
   valor não flutua.
2. **Com o motor girando:** frequência (16-13) e corrente (16-14).
3. **A potência (16-10)** é a escala mais incerta no FC 51. Se o display
   marcar `0,37 kW` e a tabela `3,70`, ajuste
   `DANFOSS_ESCALA_POTENCIA=0.001`.

**6. Se vier erro em tudo:** inverta A e B. Se continuar, confira se o drive
foi mesmo religado depois do 8-30. Em último caso, `--varrer 1614` mostra os
registradores em volta do endereço calculado para achar o deslocamento.

**7. Opcional — confirmar o mapa de alarmes.** Não é preciso provocar nada:
se o drive tiver **qualquer** alarme ou advertência no display durante a
bancada, compare o número mostrado (ex.: `A13`) com o texto da tabela. Se
baterem, o mapa de bits do FC 51 é o mesmo do FC 302.

Se quiser provocar um, o método conhecido é a falta de fase do motor
(A30/A31/A32) — mas ele exige mexer nos bornes de potência:

> ⚠️ **Só com o drive DESLIGADO da rede e depois de esperar o tempo de
> descarga do barramento CC: 4 minutos nas carcaças M1–M3 do FC 51, 15 nas
> M4/M5** (FC 51 Design Guide, *Discharge Time*). Os capacitores seguram
> tensão letal com o display já apagado. Se não estiver à vontade com
> trabalho em painel, pule este passo — ele é opcional.

## Dois caminhos de leitura

| Modo | Como funciona | Quando usar |
|---|---|---|
| `parametro` (padrão) | uma transação Modbus por parâmetro | funciona sem configurar nada no drive |
| `pcd` | **uma** transação devolve até 10 parâmetros (registradores 2910–2919) | quando precisar de taxa — é o caminho para MCSA |

O modo `pcd` exige configurar o parâmetro **12-22** no drive, dizendo quais
parâmetros aparecem no bloco e em que ordem. Sem isso o bloco devolve zeros
ou lixo **e nada avisa** — por isso não é o padrão.

## Testes

```bash
python tools/testes/testa_inversores.py        # lógica pura: endereço, largura, alarmes
python tools/testes/testa_danfoss_modbus.py    # drive simulado, Modbus TCP de verdade
```

O segundo sobe um servidor Modbus que se comporta como um FC 302 num estado
conhecido — frenando, com dois alarmes ativos — e lê dele pelo sidecar.
Cada parâmetro existe **só** nos registradores que o manual diz que ele
ocupa. Reintroduzindo o bug dos 32 bits, o teste quebra na hora. Ele
**não** substitui a bancada: o simulador e o sidecar partem da mesma leitura
do manual.

## O que ainda falta

- [x] ~~Confirmar o mapeamento de registrador~~ — FC 51 Design Guide §8.9.1
- [x] ~~Tipos e escalas~~ — lista de parâmetros do FC 301/302
- [x] ~~Mapa de bits do alarme~~ — no FC 301/302
- [ ] **Bancada com o FC 51** (roteiro acima)
- [ ] Escala da 16-10 e mapa de bits da 16-90 **no FC 51**
- [ ] FC 301/302 na fábrica: agendar a parada para religar o drive após o 8-30
- [ ] Medir a taxa real do modo `pcd` e rodar a sonda de MCSA em cima dela
