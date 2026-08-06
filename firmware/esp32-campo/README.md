# Firmware — Módulo de Campo (ESP32)

Firmware em **PlatformIO / Arduino** que lê **temperatura** (MLX90614,
infravermelho sem contato) e **vibração** (ADXL345) e publica a telemetria
por **MQTT** para o painel.

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
   - `TEMP_SENSOR_TYPE` — `3` para MLX90614 (infravermelho sem contato,
     **padrão**), `1` para DS18B20 ou `2` para DHT22.
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
                "eixo_x_g": 0.05, "eixo_y_g": 0.02, "eixo_z_g": 1.01,
                "fs_hz": 371.4 },
  "rede": { "rssi_dbm": -61, "uptime_s": 84213 }
}
```

E mantém o status online/offline (retido, com LWT) em
`monitoramento/<DEVICE_ID>/status`.

## Comandos recebidos do Node-RED

O firmware **assina** `monitoramento/<DEVICE_ID>/cmd` e aceita comandos em
JSON, fechando a comunicação nos dois sentidos:

```json
{ "comando": "publicar" }     // publica a telemetria imediatamente
{ "intervalo_ms": 2000 }       // muda o intervalo de publicação (500..3600000 ms)
```

No dashboard do Node-RED há o botão **"Publicar agora"** que envia o primeiro
comando. Teste manual:

```bash
mosquitto_pub -h <IP_DO_ORANGE_PI> -t 'monitoramento/motor-01/cmd' -m '{"comando":"publicar"}'
```

## Como a vibração é calculada

O firmware amostra o ADXL345 por uma janela de `VIB_AMOSTRAS` amostras,
remove a gravidade **eixo a eixo** (pela média da janela) e reporta:

- **`rms_g`** — RMS do componente AC, combinando os três eixos
  (`√(varX + varY + varZ)`). É a energia de vibração.
- **`pico_g`** — maior desvio AC absoluto do eixo mais excitado.
- **`fs_hz`** — a taxa de amostragem **realmente medida** naquela janela.

> **Por que eixo a eixo.** Calcular pela magnitude do vetor (`√(x²+y²+z²)`)
> parece equivalente, mas não é: como `|g + v| ≈ g + v_paralelo_à_gravidade`,
> a vibração transversal à gravidade some no termo de 2ª ordem. O resultado
> passaria a depender da orientação de montagem — um motor com vibração
> radial horizontal reportaria RMS quase zero. Somando a variância dos três
> eixos, o valor fica invariante à orientação.

> **Sobre `fs_hz`.** A taxa real é menor que `1/VIB_INTERVALO_US`, porque
> cada leitura I²C custa ~0,7 ms: com os 2000 µs padrão dá ~370 Hz, não os
> 500 Hz nominais. Por isso o ODR do ADXL está em 200 Hz (banda 100 Hz) —
> abaixo de metade da taxa real, para não haver aliasing. Se acelerar a
> amostragem, dá para subir o ODR na mesma proporção; confira sempre o
> `fs_hz` que chega no tópico em vez de confiar no valor nominal.

Faça um *baseline* com o equipamento em condição normal antes de definir os
limites de alarme no Node-RED.

## Teste rápido sem Node-RED

Com o broker rodando, assine o tópico para ver os dados chegando:

```bash
mosquitto_sub -h <IP_DO_ORANGE_PI> -t 'monitoramento/#' -v
```
