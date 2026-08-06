# Telemetria do PowerFlex 525 (EtherNet/IP) → MQTT

*Sidecar* em Python que lê o inversor **Allen-Bradley PowerFlex 525** pela
rede **EtherNet/IP** e publica no broker MQTT. O drive já mede corrente,
tensão, frequência e barramento CC — tudo calibrado de fábrica — e ainda
guarda o histórico de falhas; aproveitar isso sai de graça.

```
PowerFlex 525 ──EtherNet/IP──> powerflex_mqtt.py ──MQTT──> Node-RED
```

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
  "status_bruto": 3
}
```

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
| b007      | Código da falha          | falha ativa → ativo em **CRÍTICO** |

> `b007` é a falha mais recente; `b008` e `b009` guardam as duas
> anteriores. O sidecar lê só a `b007` — histórico de falha é trabalho do
> banco, não do polling.

**Acesso CIP:** Parameter Object (classe `0x0F`), `instância = número do
parâmetro`, `atributo 1 = valor`, serviço `Get_Attribute_Single (0x0E)`. O
valor volta como **inteiro 16 bits** com escala implícita.

**Mensageria desconectada (UCMM).** O `generic_message()` do pycomm3 assume
`connected=True` por padrão, o que dispara um **Forward Open** antes da
requisição — comportamento certo para um rack Logix, mas o adaptador embarcado
do PowerFlex costuma recusar a abertura de conexão. Por isso a leitura aqui usa
`connected=False, unconnected_send=True`. O sintoma de esquecer esse detalhe é
falhar na *abertura da conexão*, não na leitura do parâmetro — o que manda você
investigar o lado errado.

> **Fallback:** em alguns firmwares o acesso é pelo **DPI Parameter Object
> (classe `0x93`)**, mesma lógica de instância/atributo. Se a classe `0x0F` não
> responder, ajuste `PF525_CLASSE=0x93` no `config.env` — não precisa mexer no
> código.

## ⚠️ Os dois ajustes que você provavelmente vai precisar fazer

1. **As escalas.** O valor bruto é inteiro; cada grandeza tem sua escala,
   e elas **variam com a faixa de potência do drive**. Os padrões
   (`PF525_ESCALA_FREQ`, `_CORRENTE`, `_TENSAO`, `_DCBUS`) são os típicos
   da família 520.

   Para calibrar: ligue `PF525_LOG_BRUTO=1`, ponha o teclado no parâmetro e
   confira se `bruto × escala` bate com o display. Ex.: bruto `1234` e
   display `12,34 A` ⇒ escala `0.01`.
2. **Classe do objeto (`PF525_CLASSE`).** `0x0F` ou `0x93` — veja o fallback
   acima.

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
