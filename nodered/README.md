# Node-RED — Painel (Orange Pi)

Fluxo do Node-RED que assina a telemetria dos módulos de campo, apresenta o
dashboard (temperatura, vibração, corrente), avalia limites e gera alarmes.

## Pré-requisitos no Orange Pi

```bash
# Broker MQTT
sudo apt update && sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto

# Node-RED (instalador oficial)
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodered.js)

# Nós adicionais (dentro de ~/.node-red)
cd ~/.node-red
npm install node-red-dashboard
# opcional, se a corrente vier por Modbus:
npm install node-red-contrib-modbus
```

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
- **Corrente** → gauge, alimentado por um nó de **exemplo** que você deve
  trocar pela fonte real (Modbus, ADS1115/SCT-013 ou MQTT).
- **Avaliação de limites** → status colorido no dashboard + saída de debug.

## Ajustes importantes

- **Broker:** o nó `mqtt in` aponta para `localhost`. Se o Mosquitto estiver
  em outra máquina, edite o nó de configuração do broker.
- **Limites de alarme:** edite a função **"avaliar limites"** (constante
  `LIM`) — calibre com o equipamento em condição normal.
- **Corrente:** substitua a função **"fonte de corrente"** pela leitura real.
  Consulte as opções em [`docs/hardware.md`](../docs/hardware.md).

## Verificar a chegada dos dados

```bash
mosquitto_sub -h localhost -t 'monitoramento/#' -v
```
