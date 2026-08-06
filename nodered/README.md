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

## Três telas

**1. Visão Geral** (`/dashboard/visao`) — uma **parede de cards**, um por
ativo principal. Cada card traz a TAG, a descrição, o estado (símbolo +
texto + faixa colorida na lateral), as três grandezas com barra contra o
limite, quantas partes tem e há quanto tempo foi visto.

**Clicar no card abre o detalhe daquele ativo.** Acima dos cards, uma faixa
de resumo diz se está tudo normal ou lista o que não está.

**2. Cadastro** (`/dashboard/cadastro`) — todo ESP32 ou inversor que começa a
publicar aparece aqui até ser atribuído a um ativo. Ligue o dispositivo na
rede e ele surge sozinho; escolha o ativo e a parte, e pronto. **Não há nada
a digitar antes, nem arquivo a editar.**

**3. Detalhe** (`/dashboard/detalhe`) — do ativo aberto:

- Cabeçalho com nome, estado e botão **← Todos os ativos**
- *Stat tiles* — valor, barra contra o limite, estado
- **Partes deste ativo** — tabela só com as partes dele, não da planta
  inteira. É também a *table view* que garante acesso a todo valor sem
  depender de cor
- **Dados de placa e sobressalentes** — ficha do motor, foto da plaqueta e
  lista de peças de reposição (ver abaixo)
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

O cadastro vive **inteiro** em `dados/ativos.json` — mapeamento de hardware
e dados de placa no mesmo lugar — e a tela de **Cadastro** escreve nele.
Você não precisa editar o arquivo à mão para associar um dispositivo; só
para o que a tela não cobre (placa e sobressalentes).

> Antes o mapeamento morava numa constante no fluxo e a placa no arquivo,
> com as chaves tendo de bater manualmente. Além de frágil, impedia a tela
> de existir: nenhuma tela edita constante de código.

Por padrão o painel faz **descoberta automática**: cada `device_id` que
publicar vira uma linha solta, e a tela de Cadastro serve para atribuí-lo.

O cadastro resolve dois problemas de uma vez:

1. **Um equipamento, dois `device_id`.** Temperatura e vibração vêm do
   ESP32; a corrente vem do inversor. Sem o cadastro, o mesmo motor aparece
   em duas linhas, cada uma sem metade das grandezas.
2. **Um ativo principal com vários ESP32.** Uma linha de transporte, uma
   prensa ou um conjunto costuma ter um ESP32 por motor, por bomba, por
   redutor. São **sub-ativos**.

```json
{
  "Transporte 1": {
    "local": "Galpao 2 — lateral norte",
    "partes": {
      "Motor 1": {
        "esp32": "esp-a1b2c3",
        "inversor": "powerflex-01",
        "tag_inversor": "U1",
        "placa": { "corrente_nominal_a": 8.2, "...": "..." },
        "sobressalentes": [ { "item": "Rolamento dianteiro", "codigo": "6208-ZZ", "qtd": 1 } ]
      },
      "Motor 2": { "esp32": "esp-d4e5f6" }
    }
  }
}
```

Cada entrada de primeiro nível vira **um card** na visão geral. Abrindo o
card, a tabela de partes mostra:

```
Ativo               Temperatura  Vibracao   Corrente  Inversor  Estado
Transporte 1          52.5 °C     0.905 g   10.77 A             ▲ ATENCAO
    └ Motor 1         52.5 °C     0.905 g   10.77 A     U1      ▲ ATENCAO
    └ Motor 2         49.4 °C     0.167 g       --      --      ● OK
```

### Por que o inversor não é um terceiro nível

A tentação é aninhar mais: ativo → motor → temperatura / inversor U1. Não
fiz assim, e a razão é que **os dois últimos não são ativos, são fontes**.

"Temperatura" não pode estar OK ou CRÍTICA por si — ela é uma *propriedade*
do motor. E um inversor não fica crítico: quem fica é o motor que ele
aciona. Transformá-los em linha própria criaria itens com estado, alarme e
histórico para coisas que não têm condição própria — e o operador passaria
a navegar por três níveis para chegar a um número que cabia em dois.

Então a hierarquia de **ativos** para em dois níveis (ativo → parte), e o
inversor aparece como **procedência**: a coluna `Inversor` na tabela, o
`(U1)` no card, e a linha de origem no cabeçalho do detalhe
(`sensor motor-01 · inversor U1 (powerflex-01)`). É o que o eletricista
precisa para achar o drive no painel, sem inventar um ativo que não existe.

Se um dia um ativo tiver partes com partes (um conjunto dentro de outro),
aí sim vale um terceiro nível — mas aí ele carregaria equipamentos de
verdade, não sensores.

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

## Dados de placa e sobressalentes

Ficam em **`dados/ativos.json`** (copie de `ativos.example.json`), fora do
fluxo: é conteúdo de engenharia, muda por motivos diferentes da lógica, e
pode ser editado **sem deploy** — o painel relê o arquivo a cada 60 s.

As chaves têm de bater com as do cadastro `ATIVOS` na função **montar
painel** — é por elas que os dois se encontram.

```json
{
  "Transporte 1": {
    "local": "Galpao 2 — lateral norte",
    "partes": {
      "Motor 1": {
        "placa": {
          "fabricante": "WEG", "modelo": "W22 IR3 Premium",
          "potencia_cv": 10, "corrente_nominal_a": 25.6,
          "rpm": 1760, "carcaca": "132S/M", "grau_protecao": "IP55",
          "foto": "transporte1-motor1.jpg"
        },
        "sobressalentes": [
          { "item": "Rolamento dianteiro", "codigo": "6208-ZZ", "qtd": 1,
            "obs": "lado do acoplamento" },
          { "item": "Rolamento traseiro", "codigo": "6206-ZZ", "qtd": 1 }
        ]
      }
    }
  }
}
```

Todo campo é opcional — o painel mostra o que existir e omite o resto.

### O campo que muda comportamento: `corrente_nominal_a`

Com a **In da placa** preenchida, os limites de alarme de corrente daquele
ativo passam a ser **90% e 110% dela**, em vez dos valores fixos do código.

Isso importa porque corrente é a única grandeza aqui cujo limite não pode
ser universal: **12 A é operação normal num motor de 15 A e sobrecarga num
de 10 A**. É a regra que o [`docs/arquitetura.md`](../docs/arquitetura.md)
sempre recomendou e que, sem o dado de placa, ficava chutada.

O painel mostra o limite em vigor na própria ficha
(`Limite de alarme: 7.4 / 9.0 A (90% / 110% da In)`), para quem olha saber
se o alarme daquele ativo é calibrado ou genérico.

### Fotos das plaquetas

Ficam em `dados/fotos/` e são citadas só pelo nome do arquivo. O Node-RED
as serve em `/fotos/` via `httpStatic` — o `setup_orangepi.sh` configura
isso; se instalar na mão, acrescente ao `settings.js`:

```javascript
httpStatic: [
    { path: '/opt/iot/dados/fotos', root: '/fotos/' }
],
```

> Fotografe de frente, com luz, **sem flash direto** — o reflexo no metal
> apaga justamente os números gravados, que é o que você foi fotografar.

### Onde o fluxo procura o cadastro

Em `$IOT_DADOS/ativos.json`, com `IOT_DADOS` valendo `/opt/iot/dados` por
padrão. Caminho absoluto de propósito: o nó `file in` resolve caminho
relativo contra o diretório do **processo**, então um caminho relativo
dependeria de onde o serviço foi iniciado — e falharia calado, sem sintoma
no painel além de "sem dados de placa".

### Por que rolamento é o item que mais importa

Além de ser o sobressalente clássico, o **código do rolamento é o que o
degrau 3 do roadmap vai precisar**: o diagnóstico espectral de vibração
calcula as frequências de falha (BPFO, BPFI, BSF, FTF) a partir da
geometria do rolamento. Cadastrar isso agora é acumular o dado antes de
precisar dele.

## Como cadastrar um dispositivo novo

1. Ligue o ESP32 (ou suba o sidecar do inversor) na rede
2. Abra `http://<ip-do-pi>:1880/dashboard/cadastro` — do celular serve
3. Ele aparece em **Aguardando cadastro**, com as leituras ao vivo, o que
   ajuda a confirmar que é o dispositivo certo antes de atribuir
4. Clique nele, escolha o ativo (ou crie um novo), dê nome à parte
5. **Cadastrar**

O card aparece na visão geral em segundos. Para desfazer, o botão
*remover* na lista de já cadastrados — o ativo some sozinho quando fica
sem partes.

> A tela distingue **ESP32** de **inversor** pelo tópico em que cada um
> publica, e só pede a TAG do drive quando é inversor. Assim não dá para
> cadastrar um drive onde se espera um sensor.

### O que a tela não faz

Dados de placa e sobressalentes continuam sendo edição do
`dados/ativos.json`. É conteúdo que vem da plaqueta e do almoxarifado, não
do dispositivo — um formulário com vinte campos na tela de cadastro
atrapalharia o que ela faz bem, que é atribuir rápido.

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
