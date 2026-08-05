# Arquitetura do Sistema

## Visão geral

O sistema é dividido em dois domínios: **campo** e **painel**. A comunicação
entre eles é feita por **MQTT** sobre Wi-Fi (ou rede cabeada, se o ESP32 for
substituído por variante com Ethernet).

```
┌──────────────────────────┐         ┌─────────────────────────────────────┐
│         CAMPO            │         │            PAINEL ELÉTRICO           │
│                          │         │                                       │
│  ESP32                   │  MQTT   │  Orange Pi                            │
│   • ADXL345 (vibração)   │ ──────► │   • Mosquitto (broker MQTT)           │
│   • MLX90614 (temp. IR)  │  Wi-Fi  │   • Node-RED                          │
│                          │         │      - assina telemetria de campo     │
│  Publica telemetria      │ ◄────── │      - lê corrente do PowerFlex 525   │
│  em JSON a cada N s       │  cmd*   │        via EtherNet/IP                │
└──────────────────────────┘         │      - dashboard + alarmes            │
                                      │      - histórico                      │
                                      └─────────────────────────────────────┘
  * canal de comando opcional (ex.: mudar intervalo de envio)
```

## Componentes

### Campo — ESP32
- Lê **vibração** com o acelerômetro **ADXL345** (I²C). Calcula, sobre uma
  janela de amostras, o **RMS** e o **pico** da aceleração (componente AC,
  já descontada a gravidade).
- Lê **temperatura** com o sensor definido em `config.h` — **MLX90614**
  (infravermelho sem contato, I²C) por padrão; **DS18B20** ou **DHT22** como
  alternativas de contato.
- Publica um pacote **JSON** de telemetria a cada `INTERVALO_PUBLICACAO_MS`.
- Usa **Last Will and Testament (LWT)** para sinalizar `offline` caso perca
  a conexão.

### Painel — Orange Pi
- **Mosquitto**: broker MQTT que recebe a telemetria dos módulos de campo.
- **Node-RED**:
  - Assina os tópicos de telemetria e alimenta o dashboard.
  - Lê a **corrente diretamente do inversor PowerFlex 525** por
    **EtherNet/IP** (Orange Pi na rede Ethernet dos drives), usando
    `node-red-contrib-cip-ethernet-ip` — veja `docs/hardware.md`.
  - Aplica limites (thresholds) e gera **alarmes**.
  - Mantém histórico (arquivo/DB) — opcional.

## Tópicos MQTT

Estrutura hierárquica baseada em `<planta>/<area>/<equipamento>`:

| Tópico                                             | Sentido        | Retido | Payload                    |
|----------------------------------------------------|----------------|:------:|----------------------------|
| `monitoramento/<device_id>/telemetria`             | ESP32 → Painel |  não   | JSON de telemetria         |
| `monitoramento/<device_id>/status`                 | ESP32 → Painel |  sim   | `online` / `offline` (LWT) |
| `monitoramento/painel/<inversor_id>/corrente`      | Painel interno |  não   | JSON de corrente (drive)   |
| `monitoramento/<device_id>/cmd`                    | Painel → ESP32 |  não   | JSON de comando            |

`<device_id>` é definido em `config.h` (ex.: `motor-01`).

### Payload de telemetria (ESP32 → Painel)

```json
{
  "device_id": "motor-01",
  "ts": 123456789,
  "temperatura_c": 47.3,
  "vibracao": {
    "rms_g": 0.182,
    "pico_g": 0.640,
    "eixo_x_g": 0.05,
    "eixo_y_g": 0.02,
    "eixo_z_g": 1.01
  },
  "rede": {
    "rssi_dbm": -61,
    "uptime_s": 84213
  }
}
```

### Payload de corrente (lido do PowerFlex 525 pelo Node-RED)

Montado no Node-RED a partir dos parâmetros lidos por EtherNet/IP:

```json
{
  "inversor_id": "powerflex-01",
  "ts": 123456789,
  "corrente_a": 12.4,
  "frequencia_hz": 60.0,
  "tensao_v": 220.5,
  "dc_bus_v": 311.0
}
```

### Payload de status (LWT)

- Mensagem `online` publicada (retida) ao conectar.
- Mensagem `offline` configurada como *will* — o broker publica
  automaticamente se o ESP32 cair.

### Payload de comando (Painel → ESP32)

O ESP32 assina `monitoramento/<device_id>/cmd` e aceita:

```json
{ "comando": "publicar" }       // força publicação imediata
{ "intervalo_ms": 2000 }         // altera o intervalo de publicação (ms)
```

## Limites de alarme (sugestão inicial)

| Grandeza            | Atenção   | Crítico   | Observação                          |
|---------------------|-----------|-----------|-------------------------------------|
| Temperatura         | > 60 °C   | > 75 °C   | Ajustar conforme o equipamento      |
| Vibração (RMS)      | > 0,5 g   | > 1,0 g   | Calibrar em condição normal primeiro|
| Corrente            | > 90 % In | > 110 % In| In = corrente nominal do motor      |

Os limites acima são um ponto de partida e devem ser calibrados com o
equipamento operando em condição normal (baseline).

## Fluxo de dados no Node-RED

1. `mqtt in` assina `monitoramento/+/telemetria`.
2. `json` converte o payload em objeto.
3. Nós de função separam temperatura / vibração e comparam com os limites.
4. `ui_gauge` / `ui_chart` exibem no dashboard.
5. Nó de alarme dispara notificação quando um limite é ultrapassado.
6. A corrente é lida do inversor PowerFlex 525 por EtherNet/IP em um ramo
   próprio (`node-red-contrib-cip-ethernet-ip`) e combinada no mesmo dashboard.
