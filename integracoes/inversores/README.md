# Serviço de inversores

**Um serviço só, para todas as marcas.** Lê a lista de inversores
cadastrados e publica a telemetria de cada um no contrato MQTT de sempre:

```
monitoramento/<id>/inversor     telemetria (mesmo JSON para qualquer marca)
monitoramento/<id>/status       online / offline
insightx/gateway/inversores/estado   o que foi aplicado e o que foi recusado
```

Substitui os dois sidecars avulsos (`powerflex525/`, `danfoss_vlt/`), que
continuam existindo como **drivers**: a conversa com cada marca — conferida
contra os manuais e testada contra os simuladores — é a deles.

> **Garantia de projeto: só lê.** Nenhum caminho deste serviço escreve
> parâmetro, dá partida ou muda referência num drive.

## Como ele é configurado

```
painel (menu Inversores)  ──grava──>  /opt/iot/dados/inversores.json  ──>  este serviço
          │                                                                  │
          └────────── os dois leem os modelos de catalogo.json ──────────────┘
```

- **`catalogo.json`** — os modelos suportados: marca, como se conecta, que
  campos o cadastro pede. É a **única** fonte: o serviço e o painel leem
  daqui, e nunca discordam sobre quais modelos existem.
- **`/opt/iot/dados/inversores.json`** — a lista de inversores desta planta.
  Quem a escreve é o **menu Inversores do painel**: escolha o modelo, o
  formulário pede só os campos daquele modelo, avisa conflito enquanto se
  digita, e ao salvar o gateway aplica em segundos. O formato abaixo é só
  referência — não é preciso editá-lo à mão.

O serviço **relê o arquivo sozinho** quando ele muda (a cada 2 s) — não
precisa reiniciar nada. Se o arquivo estiver corrompido (uma escrita pela
metade), ele mantém a configuração anterior rodando e avisa.

## Modelos suportados hoje

| `modelo` | Marca / modelo | Conexão |
|---|---|---|
| `pf525` | Allen-Bradley PowerFlex 525 | EtherNet/IP, com **Multi-Drive** (posição 0 a 4 no nó) |
| `danfoss_fc302` | Danfoss VLT FC 302 | Modbus RTU (RS-485) ou TCP |
| `danfoss_fc301` | Danfoss VLT FC 301 | Modbus RTU (RS-485) ou TCP |
| `danfoss_fc51` | Danfoss VLT Micro Drive FC 51 | Modbus RTU (RS-485) |

Siemens está fora por enquanto: depende de levantar os modelos da fábrica.

## Formato da lista (referência)

```json
{"inversores": [
  {"id": "inv-u11", "modelo": "pf525", "nome": "Exaustor 1", "tag": "U11",
   "conexao": {"tipo": "cip", "ip": "192.168.1.20", "posicao": 0}},

  {"id": "inv-u12", "modelo": "pf525", "nome": "Exaustor 2", "tag": "U12",
   "conexao": {"tipo": "cip", "ip": "192.168.1.20", "posicao": 1}},

  {"id": "inv-d1", "modelo": "danfoss_fc51", "nome": "Bomba", "tag": "D1",
   "conexao": {"tipo": "rtu", "porta_serial": "/dev/ttyUSB0", "endereco": 1,
               "baud": 9600, "paridade": "E"}},

  {"id": "inv-d2", "modelo": "danfoss_fc302", "nome": "Ventilador", "tag": "D2",
   "conexao": {"tipo": "tcp", "ip": "192.168.1.40", "porta": 502, "endereco": 1}}
]}
```

| Campo | |
|---|---|
| `id` | o id no painel; único |
| `modelo` | uma chave de `catalogo.json` |
| `conexao.tipo` | `cip` (EtherNet/IP), `rtu` (RS-485) ou `tcp` (Modbus TCP) — tem de ser um que o modelo aceite |
| `nome`, `tag` | aparecem no cadastro do painel para identificar o drive |
| `habilitado` | opcional; `false` desliga a leitura sem apagar o cadastro |
| `intervalo_s` | opcional; padrão 1 s, e **5 s** para PowerFlex encadeado |

## O que é recusado — e por quê

Cada item é validado sozinho: **um item errado é ignorado e reportado, e
nunca derruba os outros**. Numa lista escrita pela tela, um erro de um não
pode apagar a planta inteira.

| Recusado | Por quê |
|---|---|
| `id` repetido | um sobrescreveria o outro na tela |
| modelo fora do catálogo | não há driver para ele |
| conexão que o modelo não tem (ex.: FC 51 por TCP) | ele só tem RS-485 |
| IP inválido, posição fora de 0–4, endereço fora de 1–247 | — |
| posição 1–4 em modelo sem Multi-Drive | só o PowerFlex 525 encadeia |
| **mesmo drive duas vezes** (mesmo IP e posição) | seria lido em dobro — peso à toa na RS-485 |
| **mesmo endereço no mesmo barramento RS-485** | dois drives respondendo juntos corrompem a leitura dos dois |
| **velocidade ou paridade diferente no mesmo barramento** | todos os drives de um fio têm de falar igual; o sintoma é "às vezes funciona" |

Para conferir um arquivo sem rodar o serviço:

```bash
INVERSORES_ARQ=/opt/iot/dados/inversores.json python servico_inversores.py --validar
```

O `scripts/verifica_instalacao.sh` roda isso sozinho.

## Como os drives são lidos

Drives que dividem uma conexão são lidos **em sequência, nunca em
paralelo**, numa sessão só:

- um **nó EtherNet/IP** — o PowerFlex da rede e os encadeados atrás dele;
- um **barramento RS-485** — todos os Danfoss no mesmo adaptador USB;
- um **IP Modbus TCP**.

Um drive que para de responder vira `offline` sozinho, sem derrubar os
vizinhos. Se a conexão inteira cai (o drive 0 de um nó, o adaptador USB),
o grupo reconecta.

## Testes

```bash
python tools/testes/testa_servico_inversores.py
```

Valida as regras acima e lê, **ao mesmo tempo**, um nó PowerFlex com
encadeados e um Danfoss — dos simuladores de `tools/simuladores/` — pela
lista em arquivo. Depois muda a lista com o serviço no ar e confere que ele
aplica sozinho. O caminho RS-485 (serial) não é exercitado: não há porta
serial virtual no teste; a lógica de barramento é coberta pela validação.
