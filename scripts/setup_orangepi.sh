#!/usr/bin/env bash
# =====================================================================
#  setup_orangepi.sh — provisiona o painel (Orange Pi) do zero
#
#  Instala e configura, nesta ordem:
#    1. Mosquitto  — broker MQTT COM autenticacao e escutando na rede
#    2. Node-RED   — runtime + dashboard + o flows.json deste repositorio
#    3. PowerFlex  — sidecar pycomm3 em /opt/iot, como servico systemd
#    4. Historico   — PostgreSQL + TimescaleDB (opcional: --sem-banco pula)
#
#  Uso (no proprio Orange Pi, como usuario normal, NAO como root):
#      cd <repo>/scripts
#      ./setup_orangepi.sh
#
#  Idempotente: pode rodar de novo sem duplicar nada. Faz backup de
#  qualquer arquivo que for substituir.
#
#  NAO instala Grafana: ele le o mesmo banco e pode rodar noutra maquina.
#  Ver docs/visualizacao.md.
# =====================================================================
set -euo pipefail

# --sem-banco: instala so o "ao vivo", sem PostgreSQL/TimescaleDB.
SEM_BANCO=0
for arg in "$@"; do
    [[ "$arg" == "--sem-banco" ]] && SEM_BANCO=1
done

# --- Descobre o repositorio a partir da localizacao deste script ------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DESTINO_IOT="/opt/iot"
MOSQ_CONF="/etc/mosquitto/conf.d/monitoramento.conf"
MOSQ_PASSWD="/etc/mosquitto/passwd"
NODERED_DIR="${HOME}/.node-red"
CARIMBO="$(date +%Y%m%d-%H%M%S)"

# --- Saida legivel ----------------------------------------------------
azul()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()    { printf '    \033[0;32mOK\033[0m  %s\n' "$*"; }
aviso() { printf '    \033[0;33m!!\033[0m  %s\n' "$*"; }
erro()  { printf '\n\033[0;31mERRO: %s\033[0m\n' "$*" >&2; exit 1; }

# Faz backup antes de sobrescrever qualquer arquivo existente.
backup() {
    local alvo="$1"
    if [[ -e "$alvo" ]]; then
        local bkp="${alvo}.bak-${CARIMBO}"
        sudo cp -a "$alvo" "$bkp" 2>/dev/null || cp -a "$alvo" "$bkp"
        aviso "backup: ${bkp}"
    fi
}

# =====================================================================
#  Verificacoes previas
# =====================================================================
verificar_ambiente() {
    azul "Verificando o ambiente"

    [[ $EUID -ne 0 ]] || erro "Rode como usuario normal, nao como root. O script usa sudo onde precisa."
    command -v sudo >/dev/null || erro "sudo nao encontrado."
    command -v apt-get >/dev/null || erro "Este script assume Debian/Ubuntu (Armbian). apt-get nao encontrado."

    [[ -f "${REPO_DIR}/nodered/flows.json" ]] \
        || erro "Nao achei ${REPO_DIR}/nodered/flows.json — rode o script de dentro do repositorio."

    ok "usuario: $(whoami)"
    ok "repositorio: ${REPO_DIR}"
    ok "arquitetura: $(uname -m)"

    # Aquece o sudo uma vez, para nao pedir senha no meio da instalacao.
    sudo -v
}

# =====================================================================
#  Credenciais do MQTT
# =====================================================================
pedir_credenciais() {
    azul "Credenciais do MQTT"
    echo "    Estas credenciais serao usadas em TRES lugares:"
    echo "      - o broker Mosquitto (aqui)"
    echo "      - o config.env do sidecar do PowerFlex (aqui)"
    echo "      - o config.h do ESP32 (voce grava depois, no firmware)"
    echo

    read -rp "    Usuario MQTT [monitoramento]: " MQTT_USER
    MQTT_USER="${MQTT_USER:-monitoramento}"

    local senha1 senha2
    while :; do
        read -rsp "    Senha MQTT: " senha1; echo
        [[ -n "$senha1" ]] || { aviso "A senha nao pode ser vazia."; continue; }
        read -rsp "    Repita a senha: " senha2; echo
        [[ "$senha1" == "$senha2" ]] && break
        aviso "As senhas nao conferem. De novo."
    done
    MQTT_PASS="$senha1"
    ok "usuario MQTT: ${MQTT_USER}"
}

# =====================================================================
#  1. Mosquitto
# =====================================================================
instalar_mosquitto() {
    azul "1/3  Mosquitto (broker MQTT)"

    sudo apt-get update -qq
    sudo apt-get install -y -qq mosquitto mosquitto-clients
    ok "pacotes instalados"

    # Arquivo de senhas. Sem -c se ja existir, senao apaga os outros usuarios.
    if [[ -f "$MOSQ_PASSWD" ]]; then
        sudo mosquitto_passwd -b "$MOSQ_PASSWD" "$MQTT_USER" "$MQTT_PASS"
    else
        sudo mosquitto_passwd -c -b "$MOSQ_PASSWD" "$MQTT_USER" "$MQTT_PASS"
    fi
    # Dono root, grupo mosquitto. O broker avisa (e a partir da 2.1 recusa)
    # password_file que nao pertenca ao root -- mas ele le o arquivo DEPOIS de
    # largar privilegio, entao root:root da EACCES e o servico morre com
    # status=13. root:mosquitto + 640 satisfaz o dono e mantem a leitura.
    sudo chown root:mosquitto "$MOSQ_PASSWD"
    sudo chmod 640 "$MOSQ_PASSWD"
    ok "usuario '${MQTT_USER}' gravado em ${MOSQ_PASSWD}"

    # O ponto do item 8 do review: sem um listener explicito, o Mosquitto 2.x
    # so escuta em localhost e o ESP32 nunca conecta (rc=-2 em loop no serial).
    backup "$MOSQ_CONF"
    sudo tee "$MOSQ_CONF" >/dev/null <<EOF
# Gerado por setup_orangepi.sh em ${CARIMBO}
#
# Sem um listener explicito, o Mosquitto 2.x escuta apenas em localhost e
# recusa conexao remota anonima -- o ESP32 nunca conectaria.
listener 1883 0.0.0.0

# Nada de anonimo: o barramento carrega dado de processo e, mais adiante,
# alimenta o historico e o Power BI.
allow_anonymous false
password_file ${MOSQ_PASSWD}

# NAO repetir 'persistence' nem 'persistence_location' aqui: o
# /etc/mosquitto/mosquitto.conf do Debian ja define os dois, e o include_dir
# carrega este arquivo DEPOIS. O Mosquitto 2.x trata chave repetida como erro
# fatal ("Duplicate persistence_location value") e o servico nao sobe.
EOF
    ok "configuracao: ${MOSQ_CONF}"

    sudo systemctl enable --now mosquitto
    sudo systemctl restart mosquitto
    sleep 1
    systemctl is-active --quiet mosquitto \
        || erro "Mosquitto nao subiu. Veja: journalctl -u mosquitto -n 40"
    ok "servico ativo"

    # Prova real: assina, publica e ve se a mensagem volta com as credenciais
    # novas. Se isso passa, o ESP32 tambem vai conseguir conectar.
    local sub_pid
    mosquitto_sub -h localhost -u "$MQTT_USER" -P "$MQTT_PASS" \
                  -t 'setup/teste' -C 1 -W 5 >/dev/null 2>&1 &
    sub_pid=$!
    sleep 1
    mosquitto_pub -h localhost -u "$MQTT_USER" -P "$MQTT_PASS" \
                  -t 'setup/teste' -m 'ok' >/dev/null 2>&1 || true
    if wait "$sub_pid" 2>/dev/null; then
        ok "autenticacao validada (publish + subscribe deram a volta)"
    else
        aviso "nao consegui validar o par publish/subscribe — confira na mao"
    fi
}

# =====================================================================
#  2. Node-RED
# =====================================================================
instalar_nodered() {
    azul "2/3  Node-RED + dashboard"

    if command -v node-red >/dev/null; then
        ok "Node-RED ja instalado ($(node-red --version 2>/dev/null | head -1))"
    else
        aviso "O instalador oficial e interativo — responda as perguntas dele."
        bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)
        command -v node-red >/dev/null || erro "Node-RED nao ficou disponivel no PATH."
        ok "Node-RED instalado"
    fi

    # Dashboard 2.0 (@flowfuse/node-red-dashboard), NAO o node-red-dashboard
    # antigo: aquele foi descontinuado em jun/2024, roda sobre Angular v1 sem
    # manutencao e nao recebe mais correcao. O flows.json deste repo usa os
    # nos ui-* do 2.0; instalar o antigo faria o fluxo importar quebrado.
    mkdir -p "$NODERED_DIR"
    ( cd "$NODERED_DIR" && npm install --no-fund --no-audit @flowfuse/node-red-dashboard )
    ok "Dashboard 2.0 instalado"

    # Para o servico antes de mexer no flows.json, senao ele reescreve por cima.
    sudo systemctl stop nodered 2>/dev/null || true

    backup "${NODERED_DIR}/flows.json"
    cp "${REPO_DIR}/nodered/flows.json" "${NODERED_DIR}/flows.json"
    ok "flows.json importado de ${REPO_DIR}/nodered/"

    # O fluxo procura o cadastro em $IOT_DADOS/ativos.json (padrao
    # /opt/iot/dados). Um LINK, e nao copia, para a pasta do repo faz o
    # painel enxergar as edicoes na hora -- sem repetir a copia a cada
    # motor cadastrado.
    sudo mkdir -p "${DESTINO_IOT}"
    sudo chown "$(id -u):$(id -g)" "${DESTINO_IOT}"
    if [[ ! -e "${DESTINO_IOT}/dados" ]]; then
        ln -s "${REPO_DIR}/dados" "${DESTINO_IOT}/dados"
        ok "cadastro ligado: ${DESTINO_IOT}/dados -> ${REPO_DIR}/dados"
    else
        aviso "${DESTINO_IOT}/dados ja existe — mantido"
    fi

    if [[ ! -f "${REPO_DIR}/dados/ativos.json" ]]; then
        cp "${REPO_DIR}/dados/ativos.example.json" "${REPO_DIR}/dados/ativos.json"
        aviso "criado dados/ativos.json a partir do exemplo — preencha com os seus motores"
    fi

    # Serve dados/fotos/ em /fotos para o painel de dados de placa. Sem
    # isso a foto da plaqueta nao carrega -- o navegador pede /fotos/x.jpg
    # e o Node-RED responde 404, sem erro visivel no log do fluxo.
    local settings="${NODERED_DIR}/settings.js"
    # Numa instalacao NOVA o settings.js so e criado no primeiro start do
    # servico. Sem isto o patch do httpStatic abaixo cai sempre no ramo
    # "ausente" e as fotos de plaqueta nunca sao servidas -- falha silenciosa,
    # porque o script segue e diz "servico ativo" logo adiante.
    if [[ ! -f "$settings" ]]; then
        sudo systemctl start nodered 2>/dev/null || true
        for _ in $(seq 1 20); do [[ -f "$settings" ]] && break; sleep 1; done
        sudo systemctl stop nodered 2>/dev/null || true
    fi
    # Procura a CHAVE de configuracao, nao a palavra: o settings.js padrao
    # cita "httpStatic" nos comentarios, e um grep solto acha o comentario e
    # conclui que ja esta configurado.
    if [[ -f "$settings" ]] && ! grep -qE '^[[:space:]]*httpStatic[[:space:]]*:' "$settings"; then
        backup "$settings"
        # Insere logo apos "module.exports = {" para nao depender do resto
        # do arquivo, que muda entre versoes do Node-RED.
        python3 - "$settings" "${REPO_DIR}/dados/fotos" <<'PY'
import sys, io
caminho, fotos = sys.argv[1], sys.argv[2]
s = io.open(caminho, encoding="utf-8").read()
marca = "module.exports = {"
import re
ja = re.search(r"^\s*httpStatic\s*:", s, re.M)
if marca in s and not ja:
    bloco = (marca + "
"
             "    httpStatic: [
"
             "        { path: '%s', root: '/fotos/' }
"
             "    ],
" % fotos)
    s = s.replace(marca, bloco, 1)
    io.open(caminho, "w", encoding="utf-8").write(s)
    print("httpStatic configurado")
else:
    print("httpStatic ja presente ou marcador nao encontrado")
PY
        ok "fotos de plaqueta servidas em /fotos"
    else
        aviso "httpStatic ja estava configurado — nada a fazer"
    fi

    sudo systemctl enable --now nodered
    sleep 2
    systemctl is-active --quiet nodered \
        || aviso "Node-RED nao subiu. Veja: journalctl -u nodered -n 40"
    ok "servico ativo"
}

# =====================================================================
#  3. Sidecar do PowerFlex 525
# =====================================================================
instalar_powerflex() {
    azul "3/3  Sidecar do PowerFlex 525 (EtherNet/IP -> MQTT)"

    sudo apt-get install -y -qq python3 python3-venv python3-pip
    sudo mkdir -p "${DESTINO_IOT}"
    sudo chown "$(id -u):$(id -g)" "${DESTINO_IOT}"

    local destino="${DESTINO_IOT}/integracoes/powerflex525"
    mkdir -p "${DESTINO_IOT}/integracoes"
    cp -r "${REPO_DIR}/integracoes/powerflex525" "${DESTINO_IOT}/integracoes/"
    ok "codigo em ${destino}"

    python3 -m venv "${destino}/.venv"
    "${destino}/.venv/bin/pip" install --quiet --upgrade pip
    "${destino}/.venv/bin/pip" install --quiet -r "${destino}/requirements.txt"
    ok "dependencias instaladas (pycomm3, paho-mqtt)"

    # config.env: preserva o que ja existir, so preenche o MQTT.
    local cfg="${destino}/config.env"
    if [[ -f "${cfg}" ]]; then
        aviso "config.env ja existe — mantido como esta"
    else
        cp "${destino}/config.example.env" "${cfg}"
        # Comentario so em linha propria: o EnvironmentFile do systemd nao
        # corta comentario no fim da linha (ver README da integracao).
        sed -i \
            -e "s|^MQTT_USER=.*|MQTT_USER=${MQTT_USER}|" \
            -e "s|^MQTT_PASS=.*|MQTT_PASS=${MQTT_PASS}|" \
            "${cfg}"
        chmod 600 "${cfg}"
        ok "config.env criado (credenciais MQTT ja preenchidas)"
        aviso "AJUSTE PF525_IP no ${cfg} — hoje esta no valor de exemplo"
    fi

    # Unit gerado com o usuario e os caminhos reais desta maquina.
    backup /etc/systemd/system/powerflex525-corrente.service
    sudo tee /etc/systemd/system/powerflex525-corrente.service >/dev/null <<EOF
[Unit]
Description=Leitura de corrente do PowerFlex 525 (EtherNet/IP) -> MQTT
After=network-online.target mosquitto.service
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=${destino}
EnvironmentFile=${cfg}
ExecStart=${destino}/.venv/bin/python powerflex_mqtt.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    ok "unit systemd instalado"

    # Nao damos "enable --now": sem o IP do drive configurado ele so entraria
    # em loop de reconexao. O usuario liga depois de ajustar o config.env.
    aviso "servico NAO iniciado de proposito — ajuste o PF525_IP primeiro"
}

# =====================================================================
#  Resumo final
# =====================================================================
resumo() {
    local ip
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    ip="${ip:-<ip-do-orange-pi>}"

    azul "Pronto"
    cat <<EOF

  Dashboard ao vivo   http://${GATEWAY_NOME}.local:1880/dashboard/
                      http://${ip}:1880/dashboard/   (pelo IP, se o .local falhar)
  Editor do Node-RED  http://${GATEWAY_NOME}.local:1880
  Broker MQTT         ${ip}:1883  (usuario: ${MQTT_USER})

  FALTA FAZER, nesta ordem:

  1. Node-RED — credenciais do broker
     O flows.json vem sem senha. Abra o editor, clique em qualquer no MQTT,
     edite o broker "Mosquitto local", aba Security, preencha usuario e
     senha, e faca Deploy. E uma vez so.

  2. PowerFlex — IP do inversor
     nano ${DESTINO_IOT}/integracoes/powerflex525/config.env
       PF525_IP=<ip real do drive>
     Depois:
       sudo systemctl enable --now powerflex525-corrente
       journalctl -u powerflex525-corrente -f
     Se falhar na ABERTURA da conexao (nao na leitura), o parametro esta
     certo e a classe CIP e que muda: PF525_CLASSE=0x93.

  3. ESP32 — as mesmas credenciais
     Em firmware/esp32-campo/include/config.h:
       #define MQTT_HOST     "${ip}"
       #define MQTT_USER     "${MQTT_USER}"
       #define MQTT_PASSWORD "<a senha que voce digitou>"

  4. Conferir o barramento
     mosquitto_sub -h localhost -u ${MQTT_USER} -P '<senha>' -t 'monitoramento/#' -v

  NAO instalado (camada de historico, ver docs/visualizacao.md):
     PostgreSQL + TimescaleDB, Grafana.

EOF
}

# =====================================================================
# =====================================================================
#  4. PostgreSQL + TimescaleDB
# =====================================================================
instalar_banco() {
    azul "4/4  PostgreSQL + TimescaleDB (historico)"

    if [[ "${SEM_BANCO:-}" == "1" ]]; then
        aviso "pulado por --sem-banco"
        return
    fi

    sudo apt-get install -y -qq postgresql postgresql-contrib gnupg
    ok "PostgreSQL instalado"

    # O TimescaleDB nao vem no repositorio padrao do Debian/Ubuntu.
    if ! sudo -u postgres psql -tAc          "SELECT 1 FROM pg_available_extensions WHERE name='timescaledb'"          | grep -q 1; then
        local codinome; codinome="$(lsb_release -cs)"
        # O caminho do repositorio segue a distro-BASE, nao o codinome:
        # a imagem Armbian pode ser Debian (trixie) ou Ubuntu (resolute),
        # e apontar /ubuntu/ num Debian devolve 404 no apt-get update.
        local distro; distro="$(. /etc/os-release 2>/dev/null && echo "${ID:-debian}")"
        [[ "$distro" == "debian" || "$distro" == "ubuntu" ]] || distro="debian"
        echo "deb https://packagecloud.io/timescale/timescaledb/${distro}/ ${codinome} main"             | sudo tee /etc/apt/sources.list.d/timescaledb.list >/dev/null
        curl -sL https://packagecloud.io/timescale/timescaledb/gpgkey             | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/timescaledb.gpg
        sudo apt-get update -qq
        # A versao do pacote acompanha a do PostgreSQL instalado.
        local pgver; pgver="$(psql --version | grep -oE '[0-9]+' | head -1)"
        # timescaledb-tools traz o timescaledb-tune, que e quem poe
        # 'timescaledb' em shared_preload_libraries. Sem o tune, a extensao
        # instala mas NAO carrega, e o CREATE EXTENSION derruba a conexao.
        sudo apt-get install -y -qq "timescaledb-2-postgresql-${pgver}" timescaledb-tools || {
            aviso "TimescaleDB nao instalou para o PG ${pgver}."
            aviso "O esquema ainda funciona SEM ele, com uma tabela comum:"
            aviso "  comente as linhas de create_hypertable/compression em sql/01-esquema.sql"
            SEM_TIMESCALE=1
        }
    fi

    if [[ "${SEM_TIMESCALE:-}" != "1" ]]; then
        sudo timescaledb-tune --quiet --yes || aviso "timescaledb-tune falhou; segue com o padrao"
        sudo systemctl restart postgresql
        ok "TimescaleDB habilitado"
    fi

    # Usuario e banco. A senha reaproveita a do MQTT so para nao pedir
    # outra ao usuario; troque depois se o banco for exposto na rede.
    #
    # Dobra aspas simples antes de interpolar no SQL: uma aspa solta na
    # senha encerraria a string e o resto viraria comando.
    local senha_sql
    senha_sql=$(printf '%s' "$MQTT_PASS" | sed "s/'/''/g")

    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='insightx'" | grep -q 1; then
        sudo -u postgres psql -c "CREATE ROLE insightx LOGIN PASSWORD '${senha_sql}'"
        ok "usuario 'insightx' criado"
    else
        aviso "usuario 'insightx' ja existia — senha mantida"
    fi

    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='insightx'" | grep -q 1; then
        sudo -u postgres createdb -O insightx insightx
        ok "banco 'insightx' criado"
    else
        aviso "banco 'insightx' ja existia"
    fi

    # Por STDIN, nao com -f: o psql roda como o usuario "postgres", que nao
    # atravessa /home/<user> (modo 0700 no Debian) e devolveria "Permissao
    # negada" no arquivo. Aqui quem le e o shell, que ainda e o usuario dono.
    if sudo -u postgres psql -d insightx -v ON_ERROR_STOP=1             < "${REPO_DIR}/sql/01-esquema.sql" >/dev/null; then
        ok "esquema aplicado"
    else
        erro "falha ao aplicar sql/01-esquema.sql"
    fi

    sudo -u postgres psql -d insightx -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO insightx; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO insightx;" >/dev/null
    ok "permissoes concedidas"

    # No do Node-RED que fala com o banco.
    ( cd "$NODERED_DIR" && npm install --no-fund --no-audit node-red-contrib-postgresql )
    ok "node-red-contrib-postgresql instalado"

    aviso "a senha do banco precisa ser preenchida no no 'InsightX' do editor"
}

# =====================================================================
#  Nome na rede (mDNS)
# =====================================================================
# Sem isto, ligar o gateway numa rede nova obriga a caçar o IP no
# roteador -- que na fábrica quase nunca é seu. Com o avahi o painel
# responde por NOME em qualquer rede:
#
#     http://insightx.local:1880/dashboard/
#
# Windows 10/11, macOS, iOS e Linux resolvem .local sozinhos. Android
# depende da versão -- lá, o IP continua valendo.
#
# Mais de um gateway no mesmo cliente? Rode com GATEWAY_NOME=insightx-linha2
# para os nomes não colidirem.
GATEWAY_NOME="${GATEWAY_NOME:-insightx}"

configurar_nome_na_rede() {
    azul "Nome na rede: ${GATEWAY_NOME}.local"

    if [[ "$(hostname)" != "$GATEWAY_NOME" ]]; then
        local antigo; antigo="$(hostname)"
        sudo hostnamectl set-hostname "$GATEWAY_NOME"
        # O /etc/hosts do Debian aponta 127.0.1.1 para o nome antigo; sem
        # trocar, o sudo passa a demorar segundos esperando resolver o
        # próprio nome.
        sudo sed -i "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1\t${GATEWAY_NOME}/" /etc/hosts
        grep -q "^127\.0\.1\.1" /etc/hosts \
            || echo -e "127.0.1.1\t${GATEWAY_NOME}" | sudo tee -a /etc/hosts >/dev/null
        ok "hostname: ${antigo} -> ${GATEWAY_NOME}"
    else
        ok "hostname ja e ${GATEWAY_NOME}"
    fi

    sudo apt-get install -y -qq avahi-daemon
    sudo systemctl enable --now avahi-daemon
    # Reinicia para anunciar o nome NOVO -- o avahi lê o hostname ao subir.
    sudo systemctl restart avahi-daemon
    systemctl is-active --quiet avahi-daemon \
        && ok "avahi ativo: http://${GATEWAY_NOME}.local:1880/dashboard/" \
        || aviso "avahi nao subiu -- o painel continua acessivel pelo IP"
}

main() {
    verificar_ambiente
    pedir_credenciais
    instalar_mosquitto
    instalar_nodered
    instalar_powerflex
    instalar_banco
    configurar_nome_na_rede
    resumo
}

main "$@"
