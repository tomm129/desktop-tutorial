# Firmware — Módulo de Campo (ESP32)

Firmware em **PlatformIO / Arduino** que lê **temperatura** e **vibração**
(ADXL345) e publica a telemetria por **MQTT** para o painel.

## Requisitos
- [PlatformIO](https://platformio.org/) (extensão do VS Code ou `pio` CLI).
- Um ESP32 (DevKit v1 ou equivalente).
- Hardware conforme [`docs/hardware.md`](../../docs/hardware.md).

## Configuração

1. Copie o arquivo de exemplo e edite com suas credenciais:

   ```bash
   cp include/config.example.h include/config.h
   ```

2. Ajuste em `include/config.h`:
   - `DEVICE_ID` — identificador do equipamento (ex.: `motor-01`).
   - `WIFI_SSID` / `WIFI_PASSWORD`.
   - `MQTT_HOST` — IP do Orange Pi (broker).
   - `TEMP_SENSOR_TYPE` — `1` para DS18B20 (padrão) ou `2` para DHT22.
   - Pinos, se necessário.

   > `include/config.h` está no `.gitignore` e **não** é versionado, para
   > não expor credenciais.

## Compilar e gravar

```bash
# Compilar
pio run

# Gravar no ESP32 conectado por USB
pio run --target upload

# Monitor serial (115200 baud)
pio device monitor
```

## O que ele publica

A cada `INTERVALO_PUBLICACAO_MS` (padrão 5 s), publica em
`monitoramento/<DEVICE_ID>/telemetria`:

```json
{
  "device_id": "motor-01",
  "ts": 84213000,
  "temperatura_c": 47.3,
  "vibracao": { "rms_g": 0.182, "pico_g": 0.640,
                "eixo_x_g": 0.05, "eixo_y_g": 0.02, "eixo_z_g": 1.01 },
  "rede": { "rssi_dbm": -61, "uptime_s": 84213 }
}
```

E mantém o status online/offline (retido, com LWT) em
`monitoramento/<DEVICE_ID>/status`.

## Como a vibração é calculada

O firmware amostra o ADXL345 por uma janela (`VIB_AMOSTRAS` amostras a
~500 Hz), calcula a magnitude da aceleração, remove a gravidade pela média
da janela e reporta:
- **`rms_g`** — RMS do componente AC (energia de vibração).
- **`pico_g`** — maior desvio absoluto no período.

Faça um *baseline* com o equipamento em condição normal antes de definir os
limites de alarme no Node-RED.

## Teste rápido sem Node-RED

Com o broker rodando, assine o tópico para ver os dados chegando:

```bash
mosquitto_sub -h <IP_DO_ORANGE_PI> -t 'monitoramento/#' -v
```
