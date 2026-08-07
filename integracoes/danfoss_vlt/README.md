# Sidecar Danfoss VLT (série FC)

Lê a telemetria de um inversor Danfoss por Modbus e publica **exatamente o
mesmo JSON** que o sidecar do PowerFlex 525. O painel não sabe a marca —
esse é o ponto.

> ⚠️ **Ainda não validado em hardware.** Escrito a partir da documentação
> oficial da Danfoss, sem nenhum drive à mão. Os pontos incertos estão
> marcados com `VERIFICAR` no código. Leia "Primeira instalação" antes de
> ligar em produção.

## Por que uma marca a mais importa

Planta real tem marcas misturadas. Se o painel só lê Allen-Bradley, ele
cobre metade da fábrica e o cliente precisa de dois sistemas — que é
exatamente o problema que ele já tem.

E há um ganho técnico específico: o Danfoss publica **16-17 Speed [RPM]**, a
velocidade real do eixo. O PowerFlex 525 não dá isso. Com a velocidade real,
o escorregamento é **medido** em vez de estimado da plaqueta, e a frequência
`2·s·f` que a sonda de MCSA procura (`tools/mcsa_sonda.py`) deixa de ser um
palpite.

## O que é lido — e a diferença entre as famílias

⚠️ **O grupo 16 NÃO é o mesmo em toda a linha FC.** Conferido nos guias de
programação de cada família:

| PNU | Parâmetro | JSON | FC 301/302 | FC 51 |
|---|---|---|---|---|
| 16-13 | Frequency [Hz] | `frequencia_hz` | ✅ | ✅ |
| 16-14 | Motor current [A] | `corrente_a` | ✅ | ✅ |
| 16-12 | Motor Voltage [V] | `tensao_v` | ✅ | ✅ |
| 16-30 | DC Link Voltage [V] | `dc_bus_v` | ✅ | ✅ |
| 16-10 | Power [kW] | `potencia_kw` | ✅ | ✅ |
| 16-18 | Motor Thermal [%] | `motor_termico_pct` | ✅ | ✅ |
| 16-34 | Heatsink Temp [°C] | `dissipador_c` | ✅ | ✅ |
| 16-03 | Status Word | `status_bruto` | ✅ | ✅ |
| 16-90 | Alarm Word | `falha` + `alarme_bruto` | ✅ | ✅ |
| **16-17** | **Speed [RPM]** | `rpm` | ✅ | ❌ |
| **16-16** | **Torque [Nm]** | `torque_nm` | ✅ | ❌ |

Escolha com `DANFOSS_FAMILIA=fc302` ou `fc51`. Errar não é fatal — o sidecar
abandona o parâmetro que o drive recusar e segue com o resto —, mas gera um
aviso por parâmetro na primeira leitura.

**`16-17 Speed [RPM]` merece destaque**: é a velocidade real do eixo, que o
PowerFlex 525 não entrega. Com ela o escorregamento é *medido* em vez de
estimado da plaqueta, e a frequência `2·s·f` que a sonda de MCSA procura
(`tools/mcsa_sonda.py`) deixa de ser palpite. **Só no FC 301/302** — no
FC 51 continua sendo estimativa.

### Uma diferença de modelo que vale entender

O PowerFlex entrega **um número** de falha. O Danfoss entrega uma **palavra
de bits**, onde vários alarmes convivem ao mesmo tempo. Para manter o mesmo
contrato JSON, o sidecar reporta o menor bit ativo como `falha.codigo` e
junta todos os textos em `falha.texto` — nenhum alarme fica escondido, e o
painel continua sem saber a marca. A palavra crua vai em `alarme_bruto`.

## Dois caminhos de leitura

| Modo | Como funciona | Quando usar |
|---|---|---|
| `parametro` (padrão) | uma transação Modbus por parâmetro | funciona sem configurar nada no drive |
| `pcd` | **uma** transação devolve até 10 parâmetros (registradores 2910–2919) | quando precisar de taxa — é o caminho para MCSA |

O modo `pcd` exige configurar o parâmetro **12-22** no drive, dizendo quais
parâmetros aparecem no bloco e em que ordem. Sem isso o bloco devolve zeros
ou lixo **e nada avisa** — por isso não é o padrão.

Para a sonda de MCSA o `pcd` é o que muda o jogo: com uma leitura por
amostra em vez de dez, a taxa sobe o bastante para procurar a modulação em
`2·s·f`. No PowerFlex, a mensageria explícita não permite isso de jeito
nenhum.

## Primeira instalação — faça nesta ordem

### Passo 0: configurar o próprio drive

O FC 51 **sai de fábrica em protocolo FC, não Modbus**. Sem isto ele não
responde, e o sintoma é timeout — que parece problema de fiação.

| Par. | Ajuste | Padrão de fábrica |
|---|---|---|
| **8-30** Protocol | **`[2] Modbus`** | `[0] FC` ← **tem de mudar** |
| 8-31 Address | 1 (ou o que puser em `DANFOSS_UNIT`) | 1 |
| 8-32 Baud Rate | `[2] 9600` | 9600 |
| 8-33 Parity | `[0] Even Parity, 1 Stop Bit` | Even, 1 stop |

Os padrões de baud e paridade já batem com o código (9600 8E1). Só o 8-30
precisa mesmo de mudança.

> Mudar o 8-30 **só passa a valer depois de desligar e religar o drive** —
> está escrito no próprio manual. Se continuar mudo, é isso.

### Passo 1: bancada, antes de qualquer MQTT

```bash
DANFOSS_FAMILIA=fc51 DANFOSS_TRANSPORTE=rtu \
DANFOSS_SERIAL=/dev/ttyUSB0 python danfoss_mqtt.py --bancada
```

Conecta, lê tudo uma vez, imprime uma tabela e sai. Não precisa de broker.
Ponha o display do drive em cada parâmetro e compare com a coluna da
direita.

O que se confere aqui **não é se o programa roda** — é se a **escala** e o
**mapeamento de registrador** estão certos para esta família. É onde a
documentação da Danfoss varia entre modelos, e onde o erro passa
despercebido porque o número continua plausível: `123,0 A` no lugar de
`12,30 A` ainda parece corrente.

### Passo 2: se vier erro ou lixo em tudo

O mapeamento da sua família é outro. Use a varredura:

```bash
python danfoss_mqtt.py --varrer 1614
```

Ela lê os registradores em volta do endereço calculado e mostra o conteúdo
de cada um. Com o display no 16-14, procure o valor na lista — o offset
aparece sozinho.

### Passo 3: só então suba como serviço

Com as escalas conferidas, desligue o `--bancada`, ajuste
`DANFOSS_LOG_BRUTO=0` e rode normal.

### Por que o passo 3 pode ser necessário

O código converte parâmetro em registrador por `(PNU × 10) − 1`, que é a
regra citada nos manuais de Modbus RTU da linha VLT. **Não consegui
confirmá-la no PDF oficial que baixei** — o manual que obtive é o da placa
Modbus TCP, que trata do mecanismo PCD e não do acesso direto a parâmetro. E
há famílias com mapeamento próprio; a **FC 51 Micro Drive** em particular.

Preferi implementar a regra conhecida e entregar junto a ferramenta de
varredura, em vez de fingir certeza sobre um número que decide se a leitura
sai certa ou errada.

## Requisitos

```bash
pip install pymodbus paho-mqtt
# Modbus RTU tambem precisa de:
pip install pyserial
```

## Ligação física

- **Modbus TCP** — precisa de placa Ethernet no drive (MCA 121 no FC 302).
  Se o inversor já está em rede, é o caminho mais simples e o mais rápido.
- **Modbus RTU** — RS-485 embutido na maioria dos FC, sem opcional. Precisa
  de um conversor USB-RS485 no Orange Pi. Confira no drive: `8-30` =
  `[2] Modbus RTU`, `8-31` = endereço, `8-32/8-33` = baud e paridade
  (padrão 9600 8E1).

## O que ainda falta

- [ ] Confirmar o modelo exato do drive em campo (FC 302? FC 51? FC 360?)
- [ ] Validar escalas e mapeamento contra o display
- [ ] Confirmar a numeração dos bits de alarme para a família em uso
- [ ] Medir a taxa real do modo `pcd` e rodar a sonda de MCSA em cima dela
