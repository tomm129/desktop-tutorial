# Sistema de Monitoramento de Corrente, Temperatura e Vibração

Sistema de monitoramento industrial distribuído para acompanhamento de
**temperatura** e **vibração** de equipamentos rotativos — e de **corrente
elétrica**, lida do inversor onde houver um na rede.

O projeto combina dois lados:

- **Campo (ESP32):** módulo instalado próximo ao equipamento, coleta
  **temperatura** e **vibração** (acelerômetro ADXL) e envia os dados por
  Wi-Fi usando o protocolo **MQTT**.
- **Painel (Orange Pi + Node-RED):** central instalada no painel elétrico.
  Roda o **broker MQTT** e o **Node-RED**, faz o monitoramento de
  **corrente**, apresenta o dashboard, gera alarmes e armazena o histórico.

```
        CAMPO                                   PAINEL ELÉTRICO
 ┌──────────────────┐                    ┌────────────────────────────┐
 │      ESP32        │                    │        Orange Pi           │
 │                   │                    │                            │
 │  ADXL (vibração)  │                    │  ┌──────────────────────┐  │
 │  MLX90614 (temp.) │   Wi-Fi / MQTT     │  │  Mosquitto (broker)  │  │
 │                   │ ─────────────────► │  │  Node-RED (dashboard)│  │
 │  Publica JSON     │                    │  │  Corrente: PowerFlex │  │
 │                   │                    │  │  525 via EtherNet/IP │  │
 └──────────────────┘                    │  └──────────────────────┘  │
                                          └────────────────────────────┘
```

## Estrutura do repositório

| Pasta | Descrição |
|---|---|
| `firmware/esp32-campo` | Firmware do sensor (PlatformIO) — temperatura + vibração via MQTT |
| `firmware/ixnode-provisionamento` | Provisionamento do IX Node (ESP-IDF, ESP32-C6): portal Wi-Fi e identidade |
| `nodered/` | Painel — o `flows.json` é **gerado** por `gera_flow.py`; edite o gerador |
| `integracoes/powerflex525` | Corrente do Allen-Bradley PowerFlex 525 (EtherNet/IP) |
| `integracoes/danfoss_vlt` | Danfoss FC 51 / FC 301 / FC 302 (Modbus RTU/TCP) |
| `scripts/` | Instalação do gateway (`setup_orangepi.sh`) e conferência (`verifica_instalacao.sh`) |
| `sql/` | Esquema do histórico (PostgreSQL + TimescaleDB) |
| `tools/` | Simulador de campo, gerador de planta de teste, sonda de MCSA e as suítes de teste |
| `docs/` | Arquitetura, comissionamento, investidor, concorrentes, revisões |

## Primeiros passos

1. **Gateway (Orange Pi):** siga [`docs/comissionamento.md`](docs/comissionamento.md)
   — do cartão em branco ao painel no ar, com as armadilhas já resolvidas.
2. **Campo (ESP32):** configure `firmware/esp32-campo/include/config.h` e
   grave o firmware — veja [`firmware/esp32-campo/README.md`](firmware/esp32-campo/README.md).
3. Consulte a arquitetura e os tópicos MQTT em
   [`docs/arquitetura.md`](docs/arquitetura.md).

**Para abrir o painel:** qualquer navegador na mesma rede do gateway, em
`http://insightx.local:1880/dashboard/` (ou pelo IP). O que muda em cada tipo
de rede está em [`docs/comissionamento.md`](docs/comissionamento.md#como-acessar-o-painel).

## Documentação

- [Objetivo e visão do projeto](docs/objetivo.md)
- [**Comissionamento do gateway**](docs/comissionamento.md) — do cartão
  em branco ao painel no ar, com as armadilhas já resolvidas
- [Teste de escala do painel](docs/teste-de-escala.md) — o que quebra com
  77 dispositivos, e como reproduzir
- [**Revisão crítica**](docs/revisao-critica.md) — ataque às decisões de
  engenharia, com o que sobreviveu à verificação e a prioridade revisada
- [**Material para investidor**](docs/INVESTIDOR.md) — mercado, estágio real,
  modelos de negócio e riscos, com fonte para cada número
- [**Diferenciais frente aos concorrentes**](docs/diferenciais.md) — WEG,
  Tractian e SEMEQ com specs verificadas, e onde ganhamos e perdemos
- [Arquitetura e tópicos MQTT](docs/arquitetura.md)
- [Visualização, histórico e Power BI](docs/visualizacao.md)
- [Hardware e ligações](docs/hardware.md)

## Status

🚧 **Protótipo com gateway rodando em hardware real, ainda sem instalação em
planta.** O quadro honesto, com o que falta, está em
[`docs/INVESTIDOR.md`](docs/INVESTIDOR.md#3-onde-estamos-de-verdade).

| Parte | Estado |
|---|---|
| Gateway (Orange Pi 3 LTS) | ✅ comissionado; verificador **30/30** na placa |
| Painel | ✅ operacional; testado com 77 dispositivos simulados |
| Histórico (TimescaleDB) | ✅ esquema aplicado no gateway · ⬜ nenhuma medição real ainda |
| Firmware do sensor | 🔶 matemática validada e compilada · ⬜ firmware inteiro nunca gravado |
| Provisionamento IX Node (C6) | 🔶 compila · ⬜ teste em placa |
| Sidecar PowerFlex 525 | 🔶 conferido nos manuais, testado contra drive simulado · ⬜ inversor real |
| Sidecar Danfoss FC 51/301/302 | 🔶 conferido nos manuais, testado contra drive simulado · ⬜ bancada |
| Testes sem hardware | ✅ 177 verificações em 7 suítes, incluindo os dois inversores por protocolo real |

**Próximos passos, na ordem que mais destrava:**

1. **Bancada do Danfoss FC 51** — roteiro no
   [README do sidecar](integracoes/danfoss_vlt/README.md). Roda do PC, sem
   gateway.
2. **Gravar um ESP32** apontando para o gateway — é o que faz a primeira
   medição real entrar no banco.
3. **Piloto num motor da fábrica** — a única linha do
   [`INVESTIDOR.md`](docs/INVESTIDOR.md) que muda a conversa.

**Definições de hardware:**

- **Temperatura (campo):** sensor infravermelho **sem contato MLX90614**
  (I²C), no mesmo barramento do ADXL345. Firmware também suporta DS18B20 e
  DHT22 por configuração.
- **Corrente (painel) — opcional:** onde o ativo tem inversor na rede, a
  corrente é lida direto dele — **PowerFlex 525** por EtherNet/IP ou
  **Danfoss FC 51/301/302** por Modbus. Sem inversor, o ativo é monitorado
  por vibração e temperatura como qualquer outro.

Veja [`docs/hardware.md`](docs/hardware.md) para ligações e parâmetros.
