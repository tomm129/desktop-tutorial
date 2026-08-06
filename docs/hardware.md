# Hardware e Ligações

## Módulo de Campo (ESP32)

### Componentes
- **ESP32** (DevKit v1 ou equivalente).
- **ADXL345** — acelerômetro digital de 3 eixos (I²C), para vibração.
- **MLX90614** — termômetro **infravermelho sem contato** (I²C). Sensor
  padrão do projeto: mede a temperatura da **superfície do equipamento** à
  distância, compartilhando o mesmo barramento I²C do ADXL345.
  - O firmware também suporta, como alternativas de contato: **DS18B20**
    (1-Wire) e **DHT22**.
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

### Ligações — MLX90614 (sensor de temperatura padrão)

O MLX90614 é I²C e usa o **mesmo barramento** do ADXL345 (endereços
diferentes, sem conflito): ADXL345 = `0x53`, MLX90614 = `0x5A`.

| MLX90614 | ESP32         |
|----------|---------------|
| VIN      | 3V3           |
| GND      | GND           |
| SDA      | GPIO 21 (SDA) |
| SCL      | GPIO 22 (SCL) |

> Módulos MLX90614 costumam já trazer os resistores de pull-up do I²C.
> Aponte o sensor para a superfície do equipamento a ser monitorado; ele lê
> a **temperatura do objeto** (`readObjectTempC`) sem contato. Respeite o
> campo de visão (FOV) do modelo — quanto mais perto, menor a área lida.

### Ligações — DS18B20 (alternativa de contato)

| DS18B20 | ESP32   |
|---------|---------|
| VCC     | 3V3     |
| GND     | GND     |
| DATA    | GPIO 4  |

> Resistor de **pull-up de 4,7 kΩ** entre DATA e 3V3 (obrigatório no 1-Wire).

### Ligações — DHT22 (alternativa de contato)

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

### Medição de corrente — Inversor PowerFlex 525 (EtherNet/IP)

A corrente é lida **diretamente do inversor de frequência** — não há sensor
de corrente externo. O drive **Allen-Bradley PowerFlex 525** já mede e
disponibiliza corrente, frequência, tensão e status de falha, tudo
calibrado, pela sua interface **EtherNet/IP embarcada**.

```
   Inversor(es) PowerFlex 525            Orange Pi
   ┌───────────────────────┐            ┌───────────────────┐
   │  EtherNet/IP embarcado │  Ethernet │  powerflex_mqtt.py │
   │  Output Current (b003) │ ────────► │  (sidecar pycomm3) │
   │  Output Freq   (b001)  │  (rede    │         ↓           │
   │  Output Voltage(b004)  │  dos      │       MQTT          │
   │  Drive Status  (b006)  │  drives)  │         ↓           │
   │  Fault Code    (b007)  │           │  Node-RED           │
   └───────────────────────┘            └───────────────────┘
```

**Rede:** o Orange Pi é ligado por **Ethernet** à mesma rede dos inversores.
Defina IPs fixos (ex.: Orange Pi `192.168.1.10`, drive `192.168.1.20`) na
mesma sub-rede. No PowerFlex 525 o IP é configurado nos parâmetros do grupo
de comunicação (**C128–C131**) ou via BOOTP/DHCP.

**Leitura:** quem fala com o drive é o sidecar
[`integracoes/powerflex525`](../integracoes/powerflex525/README.md) — o nó
`node-red-contrib-cip-ethernet-ip` é orientado a *tags* (feito para
ControlLogix), e o PowerFlex expõe **parâmetros**, não tags. Parâmetros
lidos hoje:

| Grandeza             | Parâmetro | Uso no painel                        |
|----------------------|-----------|--------------------------------------|
| Frequência de saída  | b001      | deriva o estado **rodando/parado**   |
| Corrente de saída    | b003      | grandeza com limite de alarme        |
| Tensão de saída      | b004      | leitura de referência                |
| Tensão do barramento | b005      | DC bus — leitura de referência       |
| Status do drive      | b006      | publicado cru, para decodificar      |
| Código de falha      | b007      | falha ativa → ativo em **CRÍTICO**   |

> ⚠️ **Confirme os números de parâmetro e o mapeamento CIP** no manual do
> adaptador EtherNet/IP do PowerFlex 525 (publ. *520COM-UM001*). Para
> leitura cíclica eficiente, o recomendado é mapear esses parâmetros nos
> **Datalinks** do drive e lê-los pela conexão de I/O; leitura pontual pode
> ser feita por *explicit messaging* (Parameter Object).

**Vários inversores:** basta repetir o ramo de leitura para cada IP/drive e
identificar cada um por um `medidor_id` no dashboard.

### Software no Orange Pi (resumo)

```bash
# Broker MQTT
sudo apt update && sudo apt install -y mosquitto mosquitto-clients

# Node-RED (instalador oficial)
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodered.js)

# Dashboard 2.0, dentro de ~/.node-red
cd ~/.node-red
npm install @flowfuse/node-red-dashboard
```

Detalhes de importação do fluxo em [`nodered/README.md`](../nodered/README.md).
