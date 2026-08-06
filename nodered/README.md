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

# Dashboard 2.0 (dentro de ~/.node-red)
cd ~/.node-red
npm install @flowfuse/node-red-dashboard
```

> ⚠️ É o **Dashboard 2.0** (`@flowfuse/node-red-dashboard`), não o
> `node-red-dashboard` antigo. Aquele foi descontinuado em junho de 2024 —
> roda sobre Angular v1 sem manutenção e só recebe correção pontual. Este
> `flows.json` usa os nós `ui-*` do 2.0; com o pacote antigo ele importa
> quebrado.

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
e o dashboard em `http://<IP_DO_ORANGE_PI>:1880/dashboard`.

## Importar o fluxo

1. No editor do Node-RED: menu (☰) → **Import**.
2. Selecione o arquivo [`flows.json`](flows.json) (ou cole o conteúdo).
3. Clique em **Import** e depois em **Deploy**.

## Duas telas

**1. Visão Geral** (`/dashboard/visao`) — uma **parede de cards**, um por
ativo principal. Cada card traz a TAG, a descrição, o estado (símbolo +
texto + faixa colorida na lateral), as três grandezas com barra contra o
limite, quantas partes tem e há quanto tempo foi visto.

**Clicar no card abre o detalhe daquele ativo.** Acima dos cards, uma faixa
de resumo diz se está tudo normal ou lista o que não está.

**2. Detalhe** (`/dashboard/detalhe`) — do ativo aberto:

- Cabeçalho com nome, estado e botão **← Todos os ativos**
- *Stat tiles* — valor, barra contra o limite, estado
- **Partes deste ativo** — tabela só com as partes dele, não da planta
  inteira. É também a *table view* que garante acesso a todo valor sem
  depender de cor
- Gráficos de temperatura, vibração RMS e corrente, uma série por
  dispositivo
- **Publicar agora** — força leitura imediata. Num ativo principal, dispara
  em **todas** as suas partes de uma vez

### Três estados, não dois

A tabela distingue coisas que costumam ser confundidas — e a diferença é o
que separa um painel útil de um que engana:

| Mostra | Significa |
|---|---|
| `44.8 °C` | leitura boa |
| `--` | o ativo **não tem** esse sensor — não é problema |
| `FALHA` | o sensor existe e **não respondeu** — vira ATENÇÃO |
| `○ SEM DADOS` | parou de publicar, ou o LWT marcou offline |

O caso `SEM DADOS` é um *watchdog*: se a telemetria some por mais de 20 s
(`SEM_DADOS_MS` na função **montar painel**), o ativo é marcado sozinho. Sem
isso, um ESP32 que morre deixa o último valor bom congelado na tela — que
lê exatamente como "está tudo bem".

## Cadastro de ativos e sub-ativos

Por padrão o painel faz **descoberta automática**: cada `device_id` que
publicar vira uma linha. É o modo útil enquanto a instalação está sendo
montada.

Quando a planta toma forma, preencha o `ATIVOS` no topo da função
**montar painel**. Ele resolve dois problemas de uma vez:

1. **Um equipamento, dois `device_id`.** Temperatura e vibração vêm do
   ESP32; a corrente vem do inversor. Sem o cadastro, o mesmo motor aparece
   em duas linhas, cada uma sem metade das grandezas.
2. **Um ativo principal com vários ESP32.** Uma linha de transporte, uma
   prensa ou um conjunto costuma ter um ESP32 por motor, por bomba, por
   redutor. São **sub-ativos**.

```javascript
const ATIVOS = {
    'U1': {
        descricao: 'Linha de Transporte 1',
        partes: {
            'Motor principal':  { esp32: 'motor-01', inversor: 'powerflex-01' },
            'Bomba hidraulica': { esp32: 'motor-02' },
            'Redutor':          { esp32: 'motor-03' }
        }
    }
};
```

Cada entrada de primeiro nível vira **um card** na visão geral. Abrindo o
card, a tabela de partes mostra:

```
U1 — Linha de Transporte 1     52.5 °C   0.905 g   10.77 A   ▲ ATENCAO
    └ Motor principal          52.5 °C   0.905 g   10.77 A   ▲ ATENCAO
    └ Bomba hidraulica         49.4 °C   0.167 g   --        ● OK
    └ Redutor                  50.4 °C   0.240 g   --        ● OK
```

O ativo principal **consolida**: cada grandeza vira o valor mais alto entre
as partes (o ponto mais quente da linha, a maior vibração) e o estado é o
pior entre elas. É o número pelo qual o ativo deve ser cobrado.

O alarme, porém, sai **uma vez só**, apontando a parte culpada — o pai não
repete o filho. Um ativo principal só gera alarme próprio quando ele inteiro
fica mudo.

> **Por que a TAG mora aqui e não no firmware.** Mesmo critério do
> [`docs/visualizacao.md`](../docs/visualizacao.md): o ESP32 carrega só um
> `device_id` estável. Trocar um ESP32 queimado é editar uma linha deste
> cadastro — sem regravar firmware e sem perder o histórico do ativo.

## Editar o fluxo

O `flows.json` é **gerado** por [`gera_flow.py`](gera_flow.py). Para
mudanças pequenas (limites, cadastro de ativos), edite pelo editor do
Node-RED normalmente. Para mudanças estruturais, prefira editar o gerador e
rodar:

```bash
python nodered/gera_flow.py nodered/flows.json
```

Assim o arquivo continua legível em diff, em vez de virar 700 linhas de
JSON escritas à mão.

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

O botão *Publicar agora* manda para o ativo escolhido no seletor. Para
testar pela linha de comando:

```bash
mosquitto_pub -h localhost -t 'monitoramento/motor-01/cmd' -m '{"comando":"publicar"}'
```

## Testar sem hardware

Há um simulador de campo no repositório — ele publica telemetria de vários
ESP32 e a corrente do inversor, sem precisar de nada ligado:

```bash
python tools/simulador_campo.py --ativos 3          # tudo normal
python tools/simulador_campo.py --cenario alarme    # vibração subindo até crítico
python tools/simulador_campo.py --cenario falha     # sensor de temperatura morto
python tools/simulador_campo.py --cenario mudo      # um ativo para de publicar
```

Os três últimos cenários são justamente os casos difíceis de reproduzir de
propósito no equipamento real, e são onde o painel precisa acertar.

## Ajustes importantes

- **Broker:** o nó `mqtt in` aponta para `localhost`. Se o Mosquitto estiver
  em outra máquina, edite o nó de configuração do broker.
- **Limites de alarme:** edite a constante `LIM` na função
  **"montar painel"** — calibre com o equipamento em condição normal. É o
  único lugar que decide estado e cor; muda ali e vale para a tabela, os
  alarmes e os *stat tiles*.
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
