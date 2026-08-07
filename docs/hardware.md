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

Os pinos são configuráveis em `config.h` — que você cria copiando
[`config.example.h`](../firmware/esp32-campo/include/config.example.h).
O link aponta para o exemplo de propósito: o `config.h` guarda credenciais e
por isso não é versionado, então num clone novo ele ainda não existe.

### MRT311 — avaliado e adiado para a fase de produto

O **Winsen MRT311** foi considerado como substituto do MLX90614. Vale
registrar por que **não** entrou agora, para a análise não se perder.

**Ele não é um termômetro — é o elemento sensor cru.** O MLX90614 traz
termopilha, amplificador, ADC, DSP e calibração de fábrica num encapsulamento
só, e entrega °C por I²C. O MRT311 entrega **tensão de termopilha**, e nada
mais.

| Parâmetro (manual Winsen v3.0) | Valor |
|---|---|
| Encapsulamento | TO-46, 4 pinos |
| Pinagem | 1 = termopilha +, 2 = NTC, 3 = termopilha −, 4 = GND |
| Responsividade | 160 ± 40 V/W |
| Ruído | 38 nV/√Hz |
| NTC integrado | 100 kΩ @ 25 °C, β = 3950 |
| Campo de visão | **95°** (acima de 50%) |
| Filtro | 5,5–14 µm, transmitância ≥ 75% |
| Constante de tempo | ≤ 13 ms |

**O ADC interno do ESP32 não serve.** Estimativa para um motor a 60 °C com
o sensor a 25 °C: potência incidente ~123 µW, saída ~20 mV, sensibilidade
~0,66 mV/°C. Resolver 0,5 °C exige ~0,3 mV. O ADC interno tem 12 bits com
vários LSB de ruído — na prática 3 a 5 mV efetivos, ou seja **±5 a 8 °C**.
Nenhum filtro em software conserta sinal que não chegou ao conversor.

**O que a adoção exigiria:**

- **ADS1115** (16 bits, PGA 16×, ±256 mV → 7,8 µV/LSB, I²C no mesmo
  barramento do ADXL345). Dois canais em modo diferencial para a termopilha
  e um para o divisor do NTC.
- Implementar NTC → temperatura ambiente (equação β, ou a tabela R-T do
  manual), Stefan-Boltzmann `V ∝ ε·(T_alvo⁴ − T_sensor⁴)` e correção de
  emissividade.
- Aferição contra termômetro de referência — a calibração que hoje vem
  pronta de fábrica.

**Atenção ao campo de visão de 95°**: a 30 cm o círculo enxergado tem ~65 cm
de diâmetro, ou seja a leitura vira média ponderada do motor **e de tudo em
volta**. Obriga montagem próxima, na ordem de 5 a 10 cm.

**Quando faz sentido trocar:** na fase de produto, por **custo em escala** —
o MRT311 sai por uma fração do MLX90614, e ter a cadeia analógica sob
controle próprio é vantagem de projeto. Para o protótipo, o MLX90614 entrega
o mesmo resultado sem construir cadeia analógica nenhuma.

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

> **Seção opcional.** Só se aplica a ativo que tem inversor na rede. Sem
> ele o sistema funciona igual, monitorando vibração e temperatura.

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
