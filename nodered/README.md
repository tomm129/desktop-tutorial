# Node-RED — Painel (Orange Pi)

Fluxo do Node-RED que assina a telemetria dos módulos de campo, apresenta o
dashboard (temperatura, vibração, corrente), avalia limites e gera alarmes.

## Atalho: instalação automática

Para provisionar o Orange Pi do zero — Mosquitto **com autenticação**,
Node-RED + dashboard, este `flows.json` e o serviço do PowerFlex:

```bash
cd <repo>/scripts
./setup_orangepi.sh
```

O passo a passo manual abaixo é exatamente o que o script faz, e continua
valendo se você preferir conduzir na mão.

## Pré-requisitos no Orange Pi

```bash
# Broker MQTT
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto

# Node-RED (instalador oficial)
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodered.js)

# Dashboard (dentro de ~/.node-red)
cd ~/.node-red
npm install node-red-dashboard
```

> ⚠️ **O Mosquitto 2.x não aceita conexão remota assim.** Sem um `listener`
> explícito ele escuta só em `localhost`, e o ESP32 nunca conecta — o sintoma
> no serial é `[MQTT] Falha (rc=-2)` em loop, fácil de confundir com problema
> de Wi-Fi. Crie `/etc/mosquitto/conf.d/monitoramento.conf`:
>
> ```
> listener 1883 0.0.0.0
> allow_anonymous false
> password_file /etc/mosquitto/passwd
> ```
>
> e o usuário com `sudo mosquitto_passwd -c /etc/mosquitto/passwd <usuario>`.
> Depois preencha as mesmas credenciais no `config.h` do ESP32, no
> `config.env` do PowerFlex e no nó de broker do Node-RED (aba *Security*).

> A leitura de corrente **não** usa mais `node-red-contrib-cip-ethernet-ip`:
> quem fala com o drive é o sidecar Python em `integracoes/powerflex525/`,
> que republica em MQTT. Veja o README de lá.

Inicie o Node-RED:

```bash
node-red-start        # ou: systemctl --user start nodered
```

Acesse o editor em `http://<IP_DO_ORANGE_PI>:1880`
e o dashboard em `http://<IP_DO_ORANGE_PI>:1880/ui`.

## Importar o fluxo

1. No editor do Node-RED: menu (☰) → **Import**.
2. Selecione o arquivo [`flows.json`](flows.json) (ou cole o conteúdo).
3. Clique em **Import** e depois em **Deploy**.

O fluxo já inclui:
- **`mqtt in`** assinando `monitoramento/+/telemetria` (broker `localhost:1883`).
- **Temperatura** → gauge (limites 60 °C / 75 °C).
- **Vibração RMS** → gráfico de linha.
- **Corrente** → gauge, alimentado por `mqtt in` em
  `monitoramento/+/corrente` — quem publica ali é o sidecar
  [`integracoes/powerflex525`](../integracoes/powerflex525/README.md), que lê
  o drive por EtherNet/IP.
- **Avaliação de limites** → status colorido no dashboard + saída de debug.
- **Status do dispositivo** → `mqtt in` em `monitoramento/+/status` mostra
  ONLINE/OFFLINE (via LWT do ESP32) no dashboard.
- **Comando → ESP32** → botão *Publicar agora* publica em
  `monitoramento/<device_id>/cmd`, fechando a comunicação nos dois sentidos.

## Comunicação ESP32 ↔ Node-RED (contrato MQTT)

Todo o elo entre campo e painel é MQTT. Broker: Mosquitto no Orange Pi.

| Sentido          | Tópico                                   | QoS | Payload                         |
|------------------|------------------------------------------|:---:|---------------------------------|
| ESP32 → Node-RED | `monitoramento/<id>/telemetria`          |  0  | JSON de telemetria              |
| ESP32 → Node-RED | `monitoramento/<id>/status` (retido/LWT) |  1  | `online` / `offline`            |
| Node-RED → ESP32 | `monitoramento/<id>/cmd`                  |  1  | JSON de comando                 |

**Comandos aceitos pelo ESP32** (tópico `cmd`):

```json
{ "comando": "publicar" }        // força uma leitura/publicação imediata
{ "intervalo_ms": 2000 }          // altera o intervalo de publicação (ms)
```

No fluxo, o nó **"monta comando"** define o `device_id` de destino
(`motor-01` por padrão) — ajuste para o seu equipamento. Para testar o
comando pela linha de comando:

```bash
mosquitto_pub -h localhost -t 'monitoramento/motor-01/cmd' -m '{"comando":"publicar"}'
```

## Ajustes importantes

- **Broker:** o nó `mqtt in` aponta para `localhost`. Se o Mosquitto estiver
  em outra máquina, edite o nó de configuração do broker.
- **Limites de alarme:** edite a função **"avaliar limites"** (constante
  `LIM`) — calibre com o equipamento em condição normal.
- **Credenciais do broker:** o `flows.json` vem sem senha. Com o Mosquitto
  autenticado, abra qualquer nó MQTT → edite o broker → aba **Security** →
  usuário e senha → **Deploy**. Uma vez só.
- **Corrente:** o gauge é alimentado por MQTT. Quem lê o drive é o sidecar
  [`integracoes/powerflex525`](../integracoes/powerflex525/README.md)
  (parâmetro *b003 [Output Current]*, manual *520COM-UM001*). Configure o IP
  do inversor lá, no `config.env`.

## Verificar a chegada dos dados

```bash
mosquitto_sub -h localhost -t 'monitoramento/#' -v
```
