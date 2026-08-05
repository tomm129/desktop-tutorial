# Hardware e Ligações

## Módulo de Campo (ESP32)

### Componentes
- **ESP32** (DevKit v1 ou equivalente).
- **ADXL345** — acelerômetro digital de 3 eixos (I²C), para vibração.
- **Sensor de temperatura** — *em definição*. O firmware suporta:
  - **DS18B20** (padrão) — sensor digital 1-Wire, versão à prova d'água
    disponível, ótimo para ambiente industrial e leitura de superfície/óleo.
  - **DHT22** — temperatura + umidade, para ambiente. Menor precisão para
    contato direto.
- Fonte 5 V estável (o ESP32 regula para 3,3 V).

### Ligações I²C — ADXL345

| ADXL345 | ESP32        |
|---------|--------------|
| VCC     | 3V3          |
| GND     | GND          |
| SDA     | GPIO 21 (SDA)|
| SCL     | GPIO 22 (SCL)|
| CS      | 3V3 (força modo I²C) |
| SDO     | GND (endereço 0x53)  |

> Endereço I²C padrão: `0x53` (SDO em GND). Com SDO em VCC vira `0x1D`.

### Ligações — DS18B20 (padrão)

| DS18B20 | ESP32   |
|---------|---------|
| VCC     | 3V3     |
| GND     | GND     |
| DATA    | GPIO 4  |

> Resistor de **pull-up de 4,7 kΩ** entre DATA e 3V3 (obrigatório no 1-Wire).

### Ligações — DHT22 (alternativa)

| DHT22 | ESP32   |
|-------|---------|
| VCC   | 3V3     |
| GND   | GND     |
| DATA  | GPIO 4  |

> Resistor de pull-up de 10 kΩ entre DATA e VCC.

Os pinos são configuráveis em
[`firmware/esp32-campo/include/config.h`](../firmware/esp32-campo/include/config.h).

### Boas práticas de instalação (vibração)
- Fixe o ADXL345 **rigidamente** na carcaça do equipamento (base metálica,
  parafuso ou adesivo estrutural). Fixação frouxa distorce a leitura.
- Oriente o eixo Z na direção esperada de maior vibração, se conhecida.
- Faça um **baseline** com o equipamento em condição normal antes de definir
  os limites de alarme.

## Central do Painel (Orange Pi)

### Componentes
- **Orange Pi** (Zero 2 / 3 / 5 — qualquer modelo com rede e Linux).
- Cartão SD / eMMC com Linux (Armbian recomendado).
- **Mosquitto** (broker MQTT).
- **Node-RED** + `node-red-dashboard`.

### Medição de corrente no painel

A corrente é medida no **painel**, não no módulo de campo. Opções comuns:

1. **Medidor de energia Modbus RTU** (ex.: multimedidor DIN) lido via
   `node-red-contrib-modbus` (RS-485 → USB no Orange Pi). *Recomendado* para
   precisão e por já entregar corrente/tensão/potência calibrados.
2. **Sensores de corrente SCT-013** (transformadores de corrente não
   invasivos) ligados a um **conversor A/D** (ex.: ADS1115 no I²C do
   Orange Pi) e lidos pelo Node-RED.
3. **Relé/medidor inteligente** que publique diretamente em MQTT.

A escolha define o ramo de entrada de corrente no fluxo do Node-RED
(`nodered/flows.json`). Por padrão o fluxo inclui um nó de exemplo que pode
ser trocado pela fonte real.

### Software no Orange Pi (resumo)

```bash
# Broker MQTT
sudo apt update && sudo apt install -y mosquitto mosquitto-clients

# Node-RED (instalador oficial)
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodered.js)

# Dashboard e (opcional) Modbus, dentro de ~/.node-red
cd ~/.node-red
npm install node-red-dashboard node-red-contrib-modbus
```

Detalhes de importação do fluxo em [`nodered/README.md`](../nodered/README.md).
