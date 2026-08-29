# Comissionamento do gateway — do cartão em branco ao painel no ar

Procedimento validado em hardware real em **2026-08-29**, num Orange Pi 3 LTS.
Cada armadilha listada aqui **aconteceu**; nenhuma é hipotética.

Tempo total: cerca de 40 minutos, quase tudo de espera.

---

## 1. Gravar o cartão

Baixe pelo **Armbian Imager** e escolha, para o Orange Pi 3 LTS:

```
Trixie_current_minimal
```

**`minimal`, não `xfce_desktop`.** O gateway é headless; um desktop só consome
a RAM e o cartão que o PostgreSQL vai querer.

**`Trixie` (Debian 13 estável), não `Resolute`, `Forky` ou `Sid`.** A máquina
roda meses sem ninguém olhando. As variantes `*-omv`, `*-homeassistant` e
`*-openhab` trazem pilha própria que conflita com a nossa.

> **Cartão SD ou eMMC?** O SD é maior (30 GB contra 7,3 GB) e, principalmente,
> **substituível** — o eMMC é soldado. Como o banco escreve continuamente, um
> meio que se troca por trinta reais vale mais que um que mata a placa. Rode do
> SD.

## 2. Primeiro acesso

Crie o usuário no primeiro boot do Armbian e descubra o IP no seu roteador.

Configure **chave SSH** antes de qualquer outra coisa — senha em terminal é
lenta e não permite automação:

```bash
ssh-copy-id -i ~/.ssh/<sua_chave>.pub <usuario>@<ip>
```

> Isso precisa de uma **janela de terminal de verdade**. O `ssh` lê a senha
> direto do terminal, não da entrada padrão: por um pipe ou por prompt sem TTY
> ele falha com `Permission denied` sem nem chegar a perguntar.

## 3. Copiar o projeto

Do PC, sem depender de git na placa:

```bash
cd <repo>
tar --exclude-vcs --exclude=node_modules --exclude=__pycache__ --exclude=build -cz . \
  | ssh <usuario>@<ip> 'mkdir -p ~/iot-monitoramento && tar -xz -C ~/iot-monitoramento'
```

> **Os `.sh` precisam chegar com LF.** O `.gitattributes` deste repositório
> força isso. Com CRLF o bash morre em `$'\r': command not found`, erro que
> não aponta a causa.

## 4. Provisionar

```bash
cd ~/iot-monitoramento/scripts && ./setup_orangepi.sh
```

Ele pede **usuário e senha do MQTT** logo no começo. Essa senha vai para três
lugares — Mosquitto, `config.env` do PowerFlex e `config.h` do ESP32 — e ainda
vira a senha do usuário do PostgreSQL. Escolha uma **sem acentos e sem
espaços**: ela é embutida numa string C no firmware.

O script é **idempotente**: pode rodar de novo à vontade. Se algo falhar no
meio, corrija e repita — ele pula o que já está pronto.

## 5. Credenciais do MQTT dentro do Node-RED

**Este passo é manual e o script não faz.** Sem ele o Node-RED fica em
`Connection failed to broker` a cada 15 s e nenhum dado chega à tela.

1. Abra `http://<ip>:1880/`
2. Duplo clique em qualquer nó MQTT roxo
3. Lápis ao lado do broker → aba **Security**
4. Usuário e senha do passo 4 → **Update** → **Deploy**

O nó passa a mostrar **connected** em verde.

## 6. Conferir

```bash
./scripts/verifica_instalacao.sh
```

São 30 checagens: serviços ativos *e* habilitados no boot, autenticação do
broker de fato recusando anônimo, fluxo sem nós faltando, rotas HTTP,
TimescaleDB **carregado** (não apenas instalado) e as hypertables.

Sai com `0` se passou tudo. **Rode sempre** — foi ele que expôs, no primeiro
comissionamento real, dois problemas que o `setup_orangepi.sh` tinha declarado
como concluídos.

---

## Armadilhas já resolvidas

Todas vieram do mesmo lugar: o script foi escrito supondo Ubuntu e nunca havia
rodado num Debian de verdade. Estão corrigidas — a lista serve para
reconhecer o sintoma se algo parecido voltar.

| # | Sintoma | Causa |
|---|---|---|
| 1 | `404` no `apt-get update` do TimescaleDB | caminho do repositório fixo em `/ubuntu/`; o certo vem do `ID` do `/etc/os-release` |
| 2 | Mosquitto não sobe; `Start request repeated too quickly` | `persistence_location` **duplicado**: o `mosquitto.conf` do Debian já define, e o `include_dir` carrega o nosso depois. Chave repetida é erro fatal no 2.x |
| 3 | `/dev/fd/63: 404: comando não encontrado` | URL do instalador do Node-RED desatualizada. O correto é `deb/update-nodejs-and-nodered`, sem extensão |
| 4 | Mosquitto morre com `status=13` | `password_file` como `root:root`. O broker lê o arquivo **depois** de largar privilégio → `EACCES`. Use `root:mosquitto` com `640` |
| 5 | `CREATE EXTENSION` derruba a conexão | extensão instalada mas **não carregada**. Falta `timescaledb` em `shared_preload_libraries`, que quem põe é o `timescaledb-tune` — do pacote `timescaledb-tools` |
| 6 | `psql: Permissão negada` no `.sql` | `psql -f` roda como `postgres`, que não atravessa `/home/<user>` (modo `0700`). Aplique por **stdin** |
| 7 | Fotos de plaqueta não aparecem | patch do `httpStatic` rodava antes do primeiro start do Node-RED, quando o `settings.js` ainda não existe — falha silenciosa |

**O padrão que se repete:** o script dizia "OK" em dois pontos onde nada
funcionava. Terminar sem erro não é o mesmo que funcionar — é por isso que o
`verifica_instalacao.sh` existe.

---

## Depois do gateway

- **Grave um ESP32** com o mesmo usuário/senha MQTT e `MQTT_HOST = <ip do gateway>`.
  A `medicoes` deixa de estar vazia e o ativo aparece na tela.
- **PowerFlex** fica parado de propósito até você ajustar `PF525_IP` no
  `/opt/iot/integracoes/powerflex525/config.env`. Ele fala **EtherNet/IP**, que
  quer a placa na rede cabeada dos drives — Wi-Fi não serve.
- **Reverta o sudo sem senha**, se você o tiver liberado para automação:
  `sudo rm /etc/sudoers.d/010-<usuario>-nopasswd`
