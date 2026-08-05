# Sistema de Monitoramento de Corrente, Temperatura e Vibração

Sistema de monitoramento industrial distribuído para acompanhamento de
**corrente elétrica**, **temperatura** e **vibração** de equipamentos.

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

| Pasta                 | Descrição                                                        |
|-----------------------|------------------------------------------------------------------|
| `firmware/esp32-campo`| Firmware do ESP32 (PlatformIO) — temperatura + vibração via MQTT |
| `nodered/`            | Fluxo do Node-RED para o Orange Pi (dashboard + alarmes)         |
| `docs/`               | Documentação de arquitetura e hardware                           |

## Primeiros passos

1. **Painel (Orange Pi):** instale o broker MQTT e o Node-RED, importe o
   fluxo — veja [`nodered/README.md`](nodered/README.md).
2. **Campo (ESP32):** configure `firmware/esp32-campo/include/config.h` e
   grave o firmware — veja [`firmware/esp32-campo/README.md`](firmware/esp32-campo/README.md).
3. Consulte a arquitetura e os tópicos MQTT em
   [`docs/arquitetura.md`](docs/arquitetura.md).

## Documentação

- [Arquitetura e tópicos MQTT](docs/arquitetura.md)
- [Hardware e ligações](docs/hardware.md)

## Status

🚧 Em desenvolvimento. Definições atuais:

- **Temperatura (campo):** sensor infravermelho **sem contato MLX90614**
  (I²C), no mesmo barramento do ADXL345. Firmware também suporta DS18B20 e
  DHT22 por configuração.
- **Corrente (painel):** lida direto do inversor **PowerFlex 525** por
  **EtherNet/IP** (Orange Pi na rede Ethernet dos drives).

Veja [`docs/hardware.md`](docs/hardware.md) para ligações e parâmetros.
