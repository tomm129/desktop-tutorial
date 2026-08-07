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
  - Aplica limites (thresholds) e gera **alarmes**.
  - Mantém histórico (arquivo/DB) — opcional.

- **Sidecar do PowerFlex** (`integracoes/powerflex525`): lê corrente,
  tensão, barramento CC, frequência, marcha e falha **diretamente do
  inversor** por **EtherNet/IP** (Orange Pi na rede Ethernet dos drives) e
  republica em MQTT. Roda como serviço systemd, fora do Node-RED — o
  motivo está no [README da integração](../integracoes/powerflex525/README.md).

## Tópicos MQTT

O esquema é plano — `monitoramento/<id>/<assunto>`. A hierarquia de
planta (ativo → parte) vive no **cadastro** do Node-RED, não no tópico:
assim, realocar ou renomear um equipamento não obriga a mexer no firmware
nem a migrar histórico. Ver [`nodered/README.md`](../nodered/README.md).

| Tópico                                             | Sentido        | Retido | Payload                    |
|----------------------------------------------------|----------------|:------:|----------------------------|
| `monitoramento/<device_id>/telemetria`             | ESP32 → Painel |  não   | JSON de telemetria         |
| `monitoramento/<device_id>/status`                 | ESP32 → Painel |  sim   | `online` / `offline` (LWT) |
| `monitoramento/<inversor_id>/inversor`              | PF525 → Painel |  não   | JSON de telemetria do drive|
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
    "crista": 3.52,
    "vel_mm_s": 2.14,
    "eixo_x_g": 0.05,
    "eixo_y_g": 0.02,
    "eixo_z_g": 1.01,
    "fs_hz": 371.4
  },
  "rede": {
    "rssi_dbm": -61,
    "uptime_s": 84213
  }
}
```

| Campo | O que é |
|---|---|
| `rms_g` | RMS AC combinado dos 3 eixos, em g |
| `pico_g` | maior desvio AC absoluto (eixo mais excitado) |
| `crista` | pico/RMS **por eixo**, reportando o maior. Sadio ≈ 3–4; acima de 5 há conteúdo impulsivo (rolamento batendo) |
| `vel_mm_s` | velocidade RMS, banda de 10 Hz até ~metade de `fs_hz`. É a unidade da **ISO 20816** — ver a ressalva de banda em [`objetivo.md`](objetivo.md) |
| `fs_hz` | taxa de amostragem **real medida** na janela, não a nominal |

#### Amostra recuperada do buffer

Quando o MQTT cai, o ESP32 continua medindo e guarda em RAM. Ao reconectar,
despeja o que guardou com dois campos a mais:

```json
{
  "device_id": "motor-01",
  "ts": 45000,
  "buffer": true,
  "atraso_ms": 372500,
  "decimado": true,
  "temperatura_c": 52.1,
  "vibracao": { "rms_g": 0.31, "pico_g": 1.28, "crista": 4.1,
                "vel_mm_s": 3.05, "fs_hz": 370.9 }
}
```

- **`atraso_ms`** — há quanto tempo a amostra foi colhida. O ESP32 não tem
  relógio de parede (e um reboot zeraria qualquer contagem), então quem
  reconstrói o instante é o painel: `ts_real = agora − atraso_ms`. Isso
  dispensa NTP no dispositivo.
- **`decimado`** — o buffer encheu e descartou uma amostra sim, outra não,
  para cobrir um período maior com menos resolução. O espaçamento entre
  amostras deixa de ser regular.
- O bloco `rede` **não vem** no backfill: RSSI e uptime descrevem o agora, e
  no agora eles não valem para uma amostra do passado.

**O painel trata o backfill de forma deliberadamente diferente:** grava no
histórico com o instante correto, mas **não** deixa que ele mexa no estado
ao vivo. Um valor crítico de duas horas atrás não pode disparar alarme
agora — o operador correria atrás de um problema que já passou. A linha do
tempo marca esse trecho como *recuperado*: nem "tudo bem", nem "buraco",
porque naquele período o dado existe mas o alarme não rodou.

### Payload do inversor (PowerFlex 525 → Painel)

Publicado pelo sidecar [`integracoes/powerflex525`](../integracoes/powerflex525/README.md),
que lê os parâmetros do grupo `b` por EtherNet/IP:

```json
{
  "ts": 1730800000000,
  "corrente_a": 12.34,
  "tensao_v": 220.5,
  "dc_bus_v": 311.0,
  "frequencia_hz": 60.0,
  "rodando": true,
  "falha": { "codigo": 0, "texto": null },
  "status_bruto": 3
}
```

O `inversor_id` não vai no corpo: ele já está no tópico, e repetir abriria
espaço para os dois discordarem.

#### O mesmo payload vale para qualquer marca

Este JSON é **contrato**, não formato do PowerFlex. Planta real tem marcas
misturadas, e um painel que só lê Allen-Bradley cobre metade da fábrica —
deixando o cliente com os dois sistemas que ele já queria unificar.

| Marca | Sidecar | Protocolo |
|---|---|---|
| Allen-Bradley PowerFlex 525 | [`integracoes/powerflex525`](../integracoes/powerflex525/README.md) | EtherNet/IP (CIP) |
| Danfoss VLT série FC | [`integracoes/danfoss_vlt`](../integracoes/danfoss_vlt/README.md) | Modbus TCP ou RTU |

Cada sidecar traduz o protocolo do fabricante para este mesmo JSON. O painel
nunca sabe a marca — e adicionar a terceira é escrever um tradutor, não
mexer no painel.

Duas diferenças que a tradução precisa resolver, e que valem conhecer:

- **Falha.** O PowerFlex entrega *um número*; o Danfoss, uma *palavra de
  bits* com vários alarmes simultâneos. O sidecar Danfoss reporta o menor
  bit ativo em `falha.codigo` e junta todos os textos em `falha.texto`,
  preservando o contrato sem esconder alarme.
- **Campos extras.** O Danfoss publica `rpm` (velocidade real do eixo), que
  o PowerFlex não tem. Campos a mais são opcionais por construção: o painel
  mostra o que existir e omite o resto.

**`rodando` vem da frequência de saída, não do bit de status.** O bit
`Active` do drive indica que ele recebeu comando de marcha e não está em
falha — e continua verdadeiro com a velocidade em zero, ou seja, com o
motor parado. O mapa de bits do `b006` ainda varia entre versões de
firmware. Frequência acima de zero é física e não depende de interpretar
protocolo. O `status_bruto` vai junto para quem quiser decodificar contra o
próprio manual.

**`falha.codigo` é o `b007`** (falha mais recente). Zero significa sem
falha; qualquer outro valor leva o ativo a **CRÍTICO** direto, sem comparar
com limite — o próprio drive já decidiu que há problema. Código não
mapeado vira `"falha F0xx (ver manual)"` em vez de ser tratado como
ausência de falha.

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

> A linha de **corrente** só vale para ativo com inversor associado no
> cadastro. Sem drive, o alarme é só temperatura e vibração — o inversor é
> opcional em toda a cadeia.

Os limites acima são um ponto de partida e devem ser calibrados com o
equipamento operando em condição normal (baseline).

## Fluxo de dados no Node-RED

Os três tópicos alimentam **um único registro** em memória, e um só nó
decide estado, cor e texto a partir dele:

1. `mqtt in` assina `monitoramento/+/telemetria`, `.../inversor` e
   `.../status`; cada um atualiza o registro do respectivo `device_id`.
2. A cada 2 s, a função **montar painel** consolida o registro segundo o
   cadastro de ativos, avalia limites e falhas, e emite: a tabela, a faixa
   de resumo, os *stat tiles* e os cards.
3. Os gráficos são alimentados direto da ingestão, com `msg.topic` = id do
   dispositivo (é o que separa as séries).

Concentrar a decisão num lugar só é deliberado: mudar um limite, uma cor ou
uma regra de estado é mexer em **uma** função, e a tabela, os alarmes e os
medidores continuam concordando entre si.
