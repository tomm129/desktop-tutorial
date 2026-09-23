# Telemetria do PowerFlex 525 (EtherNet/IP) → MQTT

*Sidecar* em Python que lê o inversor **Allen-Bradley PowerFlex 525** pela
rede **EtherNet/IP** e publica no broker MQTT. O drive já mede corrente,
tensão, frequência e barramento CC — tudo calibrado de fábrica — e ainda
guarda o histórico de falhas; aproveitar isso sai de graça.

```
PowerFlex 525 ──EtherNet/IP──> powerflex_mqtt.py ──MQTT──> Node-RED
```

> **Estado:** conferido contra os manuais oficiais (520-UM001 e
> 520COM-UM001) e testado contra um drive simulado por EtherNet/IP de
> verdade. **Ainda não rodou num drive real.** Rode a `--bancada` antes de
> ligar em produção.

Publica em `monitoramento/<DEVICE_ID>/inversor`:

```json
{
  "ts": 1730800000000,
  "corrente_a": 12.34,
  "tensao_v": 220.5,
  "dc_bus_v": 311.0,
  "frequencia_hz": 60.0,
  "rodando": true,
  "falha": { "codigo": 0, "texto": null },
  "ultima_falha": { "codigo": 7, "texto": "Sobrecarga do motor" },
  "status_bruto": 3
}
```

`falha` é a falha **ativa agora**; `ultima_falha` é o histórico (`b007`).
A diferença é o motivo da seção seguinte.

## O que a conferência com os manuais corrigiu

Cinco problemas da primeira versão, nenhum visível sem drive na mão:

| # | Problema | Efeito no painel | Fonte |
|---|---|---|---|
| 1 | **`b007` publicado como falha atual.** Ele guarda a falha *mais recente* e continua com ela depois do rearme | uma falha da semana passada deixava o ativo **em CRÍTICO para sempre** | 520-UM001, b007 |
| 2 | **`b005` com escala 0,1.** O barramento é em **volts inteiros** (0–1200 V DC) | 311 V aparecia como **31,1 V** | 520-UM001, b005 |
| 3 | **Classe 0x93 lendo o atributo 1.** Na DPI o valor fica no **atributo 9**; o 1 é a senha de proteção | trocar de classe, como o próprio README sugeria, passava a ler **outro dado, sem erro** | 520COM-UM001, Ap. C |
| 4 | **Quatro traduções de falha erradas** (F3, F42, F43, F63) e oito códigos ausentes | F42/F43 com as fases **trocadas**; F3 (perda de alimentação) descrito como outra coisa | 520-UM001, *Drive Error Codes* |
| 5 | **Unconnected Send fixo.** O manual não esclarece se o adaptador aceita o envelope | se o drive recusar, **nenhuma leitura** funciona | — |

**Como a falha ativa é lida agora:** pelo *DPI Fault Object* (classe
`0x97`), atributo de classe 4, *Fault Trip Instance* — "fault that tripped
the device". Diferente de zero enquanto o drive está desarmado; aí a falha
que o desarmou é a mais recente, `b007`.

Se o drive não responder a esse objeto, o sidecar **não afirma falha
nenhuma**: um alarme falso permanente é pior que nenhum, e a última falha
continua visível em `ultima_falha`. Houve uma alternativa descartada — o
bit *Faulted* da *Logic Status Word* (Assembly `0x04`) —, porque o manual
põe essa palavra na posição 0 **ou** 2 dependendo do perfil usado no CLP, e
numa leitura avulsa a posição fica ambígua.

**Sobre o item 5:** em `PF525_UNCONNECTED_SEND=auto` (padrão) o sidecar
tenta com o envelope e, se o drive recusar, sem ele — e guarda o que
funcionou. A `--bancada` mostra qual foi.

> ⚠️ **Se o seu `config.env` foi copiado de uma versão anterior do
> `config.example.env`, corrija a linha `PF525_ESCALA_DCBUS=0.1` para
> `1.0`.** Variável de ambiente vence o padrão do código: corrigir só o
> script não resolve.

## Duas decisões que valem explicar

**`rodando` vem da frequência de saída, não do bit de status.** O bit
`Active` do drive indica que ele recebeu comando de marcha e não está em
falha — e **continua verdadeiro com a velocidade em zero**, ou seja, com o
motor parado. Some a isso que o mapa de bits do `b006` varia entre versões
de firmware, e a conclusão é que construir "está rodando?" sobre ele é
frágil. Frequência de saída acima de `PF525_FREQ_PARADO_HZ` é física,
direta e não depende de interpretar protocolo. O `status_bruto` vai junto
no payload para quem quiser decodificar contra o próprio manual.

**Falha é traduzida aqui, não no Node-RED.** O mapa código → texto
(`FALHAS` no topo do script) fica junto de quem conhece o equipamento; o
painel só exibe o que recebe. Código não mapeado vira
`"falha F0xx (ver manual)"` — nunca é tratado como ausência de falha.

## Por que um sidecar em Python (e não só um nó no Node-RED)?

O nó `node-red-contrib-cip-ethernet-ip` é **orientado a tags** (feito para CLPs
ControlLogix/CompactLogix). O PowerFlex **não é tag-based** — os dados são
**parâmetros** acessados por mensageria CIP explícita. A biblioteca
[`pycomm3`](https://github.com/ottowayi/pycomm3) faz esse tipo de acesso CIP
genérico de forma confiável, então ela lê o parâmetro e republica em MQTT.

(Se no futuro houver um CLP ControlLogix lendo o drive por I/O, aí sim dá para
ler a tag do CLP direto no Node-RED. E há ainda a opção de **Modbus RTU** pela
porta serial do drive — mas aqui o alvo é EtherNet/IP.)

## O dado lido

No grupo `b` (Basic Display, só leitura) o **número do parâmetro é a
própria instância CIP**. Lidos a cada ciclo:

| Parâmetro | Grandeza                 | Uso no painel                      |
|----------:|--------------------------|------------------------------------|
| b001      | Frequência de saída (Hz) | deriva **rodando/parado**          |
| b003      | Corrente de saída (A)    | grandeza com limite de alarme      |
| b004      | Tensão de saída (V)      | leitura de referência              |
| b005      | Tensão do barramento CC  | leitura de referência              |
| b006      | Status do drive          | publicado cru (`status_bruto`)     |
| b007      | Falha **mais recente**   | `ultima_falha` (histórico)         |
| DPI Fault `0x97` | Falha **ativa**   | `falha` → ativo em **CRÍTICO**     |

Escalas (campo *Display* de cada parâmetro no 520-UM001): b001 `0,01 Hz`,
b003 `0,01 A`, b004 `0,1 V`, **b005 `1 V`**.

**Acesso CIP:** Parameter Object (classe `0x0F`), `instância = número do
parâmetro`, `atributo 1 = valor`, serviço `Get_Attribute_Single (0x0E)` —
confirmado no Apêndice C do 520COM-UM001. Na alternativa, DPI Parameter
Object (`0x93`), o valor está no **atributo 9**; o código escolhe sozinho
conforme `PF525_CLASSE`.

**Mensageria desconectada (UCMM).** O `generic_message()` do pycomm3 assume
`connected=True` por padrão, o que dispara um **Forward Open** antes da
requisição — comportamento certo para um rack Logix, mas o adaptador
embarcado não é orientado a tags. Leitura pontual de parâmetro é o caso de
uso de UCMM, e é o que se usa aqui.

## Sem drive na mão? Use o simulador

`tools/simuladores/drive_powerflex.py` é um PowerFlex 525 de mentira que fala
EtherNet/IP de verdade, com um painel no navegador para trocar de cenário,
disparar falha e ver cada pedido deste sidecar. Manual em
[`tools/simuladores/README.md`](../../tools/simuladores/README.md).

## Bancada — antes de ligar em produção

Não precisa de broker. Do Orange Pi ou de qualquer PC na rede do drive:

```bash
PF525_IP=192.168.1.10 python powerflex_mqtt.py --bancada
```

Mostra cada parâmetro com valor bruto e com escala, se o drive respondeu
ao objeto de falha e qual modo de envio funcionou. Compare com o teclado:
o **b005** é o mais fácil, porque com o motor parado ele não flutua.

Se a classe `0x0F` não responder, repita com `PF525_CLASSE=0x93`.

## Testes

```bash
python tools/testes/testa_powerflex_cip.py
```

Sobe um drive **simulado** — um servidor EtherNet/IP mínimo que responde ao
que o pycomm3 realmente manda — e lê dele pelo sidecar. Cobre drive sem
falha e desarmado, drive que aceita e que recusa o envelope Unconnected
Send, as duas classes de parâmetro e o drive sem objeto de falha.
Reintroduzindo qualquer um dos bugs 1, 2 ou 3 acima, ele reprova.

Não substitui a bancada: o simulador e o sidecar partem da mesma leitura
do manual.

> ⚠️ **No `config.env`, comentário só em linha própria.** O `EnvironmentFile=`
> do systemd não corta comentário no fim da linha: `PF525_ESCALA=0.01  # ...`
> faz o valor virar a string inteira e o serviço entra em crash-loop no
> `float()`. O bash corta e esconde o problema — funciona quando você testa na
> mão e quebra quando vira serviço.

## Instalação (no Orange Pi)

```bash
cd /opt/iot/integracoes/powerflex525      # ou onde você clonou
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

cp config.example.env config.env          # edite IP, escala, MQTT...
set -a; . ./config.env; set +a
python powerflex_mqtt.py
```

Verifique a chegada com:

```bash
mosquitto_sub -h localhost -t 'monitoramento/+/inversor' -v
```

## Rodar como serviço (systemd)

```bash
sudo cp powerflex525-corrente.service /etc/systemd/system/
# ajuste User=, WorkingDirectory= e caminhos dentro do arquivo
sudo systemctl daemon-reload
sudo systemctl enable --now powerflex525-corrente
journalctl -u powerflex525-corrente -f
```

## Referências (manuais Rockwell)

- **520-UM001** — PowerFlex 520-Series, lista completa de parâmetros (grupo b).
- **520COM-UM001** — PowerFlex 525 Embedded EtherNet/IP Adapter (objetos CIP,
  assemblies de I/O e acesso a parâmetros).
