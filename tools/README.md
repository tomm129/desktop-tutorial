# Ferramentas

Tudo aqui roda **sem hardware**. São as ferramentas para desenvolver,
demonstrar e conferir o sistema antes de ter sensor, inversor ou máquina
na bancada.

| Ferramenta | Para quê | Manual |
|---|---|---|
| **`simuladores/drive_powerflex.py`** | um **PowerFlex 525 de mentira** que fala EtherNet/IP de verdade — com **painel no navegador** para trocar de cenário, disparar falha e ver cada pedido do sidecar | [simuladores/README.md](simuladores/README.md) |
| **`simuladores/drive_danfoss.py`** | um **Danfoss FC 51 / FC 301 / FC 302 de mentira** que fala Modbus TCP de verdade | [simuladores/README.md](simuladores/README.md) |
| `simulador_campo.py` | simula os **ESP32 de campo** publicando no MQTT — vibração, temperatura, falha de sensor, dispositivo mudo | `python tools/simulador_campo.py --help` |
| `gera_planta_teste.py` | gera um **cadastro grande** (dezenas de ativos) para ver o que quebra no painel quando a planta cresce | [../docs/teste-de-escala.md](../docs/teste-de-escala.md) |
| `mcsa_sonda.py` | **sonda de viabilidade de MCSA**: grava a corrente do inversor e procura a modulação de barra quebrada em 2·s·f | docstring do próprio arquivo |
| `testes/` | as **suítes de teste** — 7 conjuntos, rodam em segundos | [testes/README.md](testes/README.md) |

## Como elas se encaixam

```
simulador_campo.py ──MQTT──────────────────────────┐
                                                   ▼
drive_powerflex.py ──EtherNet/IP──> sidecar ──MQTT──> Node-RED ──> painel
drive_danfoss.py   ──Modbus TCP───> sidecar ──MQTT──┘      │
                                                           ▼
                                                     TimescaleDB
```

Com o simulador de campo e os dois drives simulados ligados ao mesmo tempo,
o painel do InsightX mostra uma planta inteira — sensores **e** inversores —
sem um único equipamento real.

## O limite de tudo isto

Simulador escrito a partir do manual prova que o código faz o que o manual
diz. **Não** prova que o equipamento real se comporta como o manual diz. Os
roteiros de bancada com os equipamentos reais estão nos READMEs de
`integracoes/` — e são eles que fecham a validação.
