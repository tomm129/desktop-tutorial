# Leitura de corrente do PowerFlex 525 (EtherNet/IP) → MQTT

*Sidecar* em Python que lê a **corrente de saída** do inversor **Allen-Bradley
PowerFlex 525** pela rede **EtherNet/IP** e publica no broker MQTT. O Node-RED
consome o tópico e alimenta o gauge de corrente — mantendo todo o barramento
em MQTT.

```
PowerFlex 525 ──EtherNet/IP──> powerflex_mqtt.py ──MQTT──> Node-RED (gauge)
```

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

| Parâmetro | Grandeza                 | Instância CIP |
|----------:|--------------------------|:-------------:|
| b001      | Frequência de saída (Hz) | 1             |
| b002      | Frequência comandada     | 2             |
| **b003**  | **Corrente de saída (A)**| **3**         |
| b004      | Tensão de saída (V)      | 4             |
| b005      | Tensão do barramento CC  | 5             |
| b006      | Status do drive          | 6             |

**Acesso CIP:** Parameter Object (classe `0x0F`), `instância = número do
parâmetro`, `atributo 1 = valor`, serviço `Get_Attribute_Single (0x0E)`. O
valor volta como **inteiro 16 bits** com escala implícita.

> **Fallback:** em alguns firmwares o acesso é pelo **DPI Parameter Object
> (classe `0x93`)**, mesma lógica de instância/atributo. Se a classe `0x0F` não
> responder, troque `class_code=0x0F` por `0x93` em `powerflex_mqtt.py`.

## ⚠️ Os dois ajustes que você provavelmente vai precisar fazer

1. **Escala (`PF525_ESCALA`).** O valor bruto é inteiro; a corrente real vem
   dividida por uma escala. O padrão aqui é `0.01` (2 casas decimais).
   **Confirme comparando com o display `b003` no teclado do drive** e ajuste
   até bater. Ex.: se o bruto lido for `1234` e o teclado mostrar `12,34 A`,
   a escala é `0.01`.
2. **Classe do objeto (`0x0F` vs `0x93`).** Veja o fallback acima.

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

Saída esperada (a cada `PF525_INTERVALO_S`), publicada em
`monitoramento/<PF525_DEVICE_ID>/corrente`:

```json
{ "corrente_a": 12.34, "ts": 1730800000000 }
```

Verifique com:

```bash
mosquitto_sub -h localhost -t 'monitoramento/+/corrente' -v
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
