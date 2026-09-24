#!/usr/bin/env bash
# =====================================================================
#  verifica_instalacao.sh — confere, item por item, se o gateway ficou
#  comissionado de verdade.
#
#  Existe porque "o script terminou sem erro" nao e a mesma coisa que
#  "o sistema funciona". No primeiro comissionamento real o setup chegou
#  ao fim dizendo "TimescaleDB habilitado" com a extensao instalada mas
#  NAO carregada, e "servico ativo" com o Node-RED incapaz de falar com
#  o broker. Os dois so apareceram na conferencia manual.
#
#  Uso (no proprio gateway):
#      ./verifica_instalacao.sh
#
#  Sai com 0 se tudo passou, 1 se houve FALHA. AVISO nao reprova.
# =====================================================================
set -uo pipefail

verde=$'\e[32m'; vermelho=$'\e[31m'; amarelo=$'\e[33m'; azul=$'\e[36m'; zero=$'\e[0m'
OK=0; FALHAS=0; AVISOS=0

secao() { printf '\n%s==> %s%s\n' "$azul" "$1" "$zero"; }
ok()    { printf '    %sOK%s    %s\n' "$verde" "$zero" "$1"; OK=$((OK+1)); }
falha() { printf '    %sFALHA%s %s\n' "$vermelho" "$zero" "$1"; FALHAS=$((FALHAS+1)); }
aviso() { printf '    %s!!%s    %s\n' "$amarelo" "$zero" "$1"; AVISOS=$((AVISOS+1)); }

# Cada teste recebe uma descricao e um comando; o comando decide.
checa() { local desc="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$desc"; else falha "$desc"; fi; }

NR_DIR="${HOME}/.node-red"

# Instalado com --sem-banco? Entao o PostgreSQL nao e falha, e escolha.
TEM_BANCO=1
command -v psql >/dev/null 2>&1 || TEM_BANCO=0

# Os logs do Node-RED contam so a partir do ULTIMO start: um problema ja
# corrigido (credencial preenchida, modulo instalado) continuava no
# journal por um dia e reprovava a conferencia mesmo resolvido.
NR_DESDE=$(systemctl show nodered -p ActiveEnterTimestamp --value 2>/dev/null)
[[ -n "$NR_DESDE" && "$NR_DESDE" != "n/a" ]] || NR_DESDE='-1 day'

# ---------------------------------------------------------------------
secao "Sistema"
. /etc/os-release 2>/dev/null || true
ok "distro: ${PRETTY_NAME:-desconhecida} ($(uname -m))"
raiz_dev=$(findmnt -no SOURCE / 2>/dev/null)
ok "raiz em ${raiz_dev} ($(df -h / | awk 'NR==2{print $4}') livres)"
usado_pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [[ "${usado_pct:-0}" -ge 90 ]]; then
    aviso "disco acima de 90% usado -- o banco vai sofrer"
fi

# ---------------------------------------------------------------------
secao "Servicos"
SERVICOS="mosquitto nodered"
[[ $TEM_BANCO -eq 1 ]] && SERVICOS="$SERVICOS postgresql"
for s in $SERVICOS; do
    if systemctl is-active --quiet "$s"; then
        ok "$s ativo"
    else
        falha "$s NAO esta ativo"
    fi
    if systemctl is-enabled --quiet "$s" 2>/dev/null; then
        ok "$s habilitado no boot"
    else
        falha "$s NAO sobe no boot (sudo systemctl enable $s)"
    fi
done

# Nome na rede: sem o avahi o painel so e achado pelo IP. Nao reprova --
# o sistema funciona --, mas numa rede nova vira caca ao IP no roteador.
if systemctl is-active --quiet avahi-daemon 2>/dev/null; then
    ok "nome na rede: http://$(hostname).local:1880/dashboard/"
else
    aviso "avahi-daemon inativo -- o painel so e acessivel pelo IP"
fi

# ---------------------------------------------------------------------
secao "Mosquitto"
if ss -ltn 2>/dev/null | grep -q ':1883'; then
    ok "escutando na porta 1883"
else
    falha "nada escutando na porta 1883"
fi

# Anonimo TEM que ser recusado: se conectar, o barramento esta aberto.
if timeout 8 mosquitto_sub -h localhost -t 'teste/anon' -C 1 -W 3 >/dev/null 2>&1; then
    falha "conexao ANONIMA aceita -- o broker esta sem autenticacao"
else
    ok "conexao anonima recusada (autenticacao ativa)"
fi

if [[ -f /etc/mosquitto/passwd ]]; then
    dono=$(stat -c '%U:%G' /etc/mosquitto/passwd)
    if [[ "$dono" == "root:mosquitto" ]]; then
        ok "dono do passwd: $dono"
    else
        # root:root da EACCES (o broker le o arquivo DEPOIS de largar
        # privilegio) e qualquer outro dono dispara o aviso do Mosquitto.
        aviso "dono do passwd e '$dono'; o esperado e root:mosquitto"
    fi
else
    falha "/etc/mosquitto/passwd nao existe"
fi

# ---------------------------------------------------------------------
secao "Node-RED"
checa "node instalado" command -v node
checa "node-red instalado" command -v node-red
checa "Dashboard 2.0 (@flowfuse/node-red-dashboard)" test -d "${NR_DIR}/node_modules/@flowfuse/node-red-dashboard"
checa "no do PostgreSQL" test -d "${NR_DIR}/node_modules/node-red-contrib-postgresql"
checa "flows.json presente" test -s "${NR_DIR}/flows.json"
checa "credenciais gravadas (flows_cred.json)" test -s "${NR_DIR}/flows_cred.json"
checa "httpStatic configurado" grep -qE '^[[:space:]]*httpStatic[[:space:]]*:' "${NR_DIR}/settings.js"
checa "cadastro em /opt/iot/dados" test -e /opt/iot/dados/ativos.json

for rota in / /dashboard/; do
    cod=$(curl -s -o /dev/null -w '%{http_code}' -L --max-time 15 "http://127.0.0.1:1880${rota}")
    if [[ "$cod" == "200" ]]; then
        ok "HTTP ${rota} -> 200"
    else
        falha "HTTP ${rota} -> ${cod}"
    fi
done

# O fluxo so vale se nenhum tipo de no estiver faltando: com um unico
# tipo ausente o Node-RED nao inicia fluxo NENHUM e o dashboard da 404.
if journalctl -u nodered --since "$NR_DESDE" --no-pager 2>/dev/null | grep -q 'missing types'; then
    falha "ha tipos de no faltando (journalctl -u nodered | grep -A5 'missing types')"
else
    ok "nenhum tipo de no faltando"
fi

# Estado MQTT: vale a ULTIMA mensagem, nao a existencia de falhas antigas.
ult=$(journalctl -u nodered --since "$NR_DESDE" --no-pager 2>/dev/null \
      | grep -oE 'Connected to broker|Connection failed to broker' | tail -1)
if [[ "$ult" == "Connected to broker" ]]; then
    ok "Node-RED conectado ao broker"
elif [[ -n "$ult" ]]; then
    falha "Node-RED NAO conecta ao broker -- faltam credenciais no no MQTT"
else
    aviso "sem registro de conexao MQTT no log"
fi

# ---------------------------------------------------------------------
secao "Servico de inversores"
INV_DIR=/opt/iot/integracoes/inversores
if systemctl is-active --quiet insightx-inversores; then ok "insightx-inversores ativo"; else falha "insightx-inversores NAO esta ativo"; fi
if systemctl is-enabled --quiet insightx-inversores 2>/dev/null; then
    ok "insightx-inversores sobe no boot"
else
    falha "insightx-inversores NAO sobe no boot (sudo systemctl enable insightx-inversores)"
fi
# O sidecar antigo lendo em paralelo leria o mesmo drive duas vezes --
# peso a mais na RS-485 do Multi-Drive, que o CLP usa para comandar.
if systemctl is-active --quiet powerflex525-corrente 2>/dev/null; then
    falha "sidecar antigo powerflex525-corrente ainda ativo (sudo systemctl disable --now powerflex525-corrente)"
fi
LISTA=/opt/iot/dados/inversores.json
if [[ -f "$LISTA" ]]; then
    if res=$(cd "$INV_DIR" && INVERSORES_ARQ="$LISTA" .venv/bin/python servico_inversores.py --validar 2>&1); then
        ok "lista de inversores do painel: $(echo "$res" | head -1)"
    else
        falha "lista de inversores com erro: $(echo "$res" | tail -n +2 | head -3 | tr '\n' ' ')"
    fi
    # O menu Inversores do painel GRAVA este arquivo. Se o Node-RED nao
    # puder escrever, o "Salvar" da tela falha.
    if [[ -w "$LISTA" && -w "$(dirname "$(readlink -f "$LISTA")")" ]]; then
        ok "painel pode gravar a lista de inversores"
    else
        falha "sem permissao de escrita em $LISTA -- o menu Inversores nao consegue salvar"
    fi
else
    aviso "lista de inversores nao existe ($LISTA) -- rode o setup de novo"
fi

# ---------------------------------------------------------------------
secao "PostgreSQL + TimescaleDB"
if [[ $TEM_BANCO -eq 0 ]]; then
    aviso "PostgreSQL nao instalado (setup com --sem-banco?) -- sem historico"
else
psqlq()  { sudo -u postgres psql -tAc "$1" 2>/dev/null; }
psqlqd() { sudo -u postgres psql -d insightx -tAc "$1" 2>/dev/null; }

if [[ "$(psqlq "SELECT 1 FROM pg_database WHERE datname='insightx'")" == "1" ]]; then
    ok "banco 'insightx' existe"
else
    falha "banco 'insightx' nao existe"
fi
if [[ "$(psqlq "SELECT 1 FROM pg_roles WHERE rolname='insightx'")" == "1" ]]; then
    ok "usuario 'insightx' existe"
else
    falha "usuario 'insightx' nao existe"
fi

# A extensao pode estar INSTALADA sem estar CARREGADA: sem 'timescaledb'
# em shared_preload_libraries o CREATE EXTENSION derruba a conexao.
pre=$(psqlq "SHOW shared_preload_libraries")
if [[ "$pre" == *timescaledb* ]]; then
    ok "timescaledb em shared_preload_libraries"
else
    falha "timescaledb NAO carregado (sudo timescaledb-tune --quiet --yes && sudo systemctl restart postgresql)"
fi

ver=$(psqlqd "SELECT extversion FROM pg_extension WHERE extname='timescaledb'")
if [[ -n "$ver" ]]; then
    ok "extensao timescaledb ${ver} ativa"
else
    falha "extensao timescaledb ausente no banco insightx"
fi

for h in medicoes eventos; do
    if [[ "$(psqlqd "SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name='${h}'")" == "1" ]]; then
        ok "hypertable '${h}'"
    else
        falha "hypertable '${h}' ausente"
    fi
done

if [[ -n "$(psqlqd "SELECT 1 FROM timescaledb_information.continuous_aggregates LIMIT 1")" ]]; then
    ok "agregado continuo presente"
else
    aviso "nenhum agregado continuo -- o historico longo fica mais lento"
fi

linhas=$(psqlqd "SELECT count(*) FROM medicoes")
if [[ "${linhas:-0}" -gt 0 ]]; then
    ok "ja ha ${linhas} medicoes gravadas"
else
    aviso "tabela 'medicoes' vazia -- nenhum dispositivo publicou ainda"
fi
fi   # TEM_BANCO

# ---------------------------------------------------------------------
printf '\n%s==> Resultado%s\n' "$azul" "$zero"
if [[ $FALHAS -gt 0 ]]; then cor="$vermelho"; else cor="$verde"; fi
printf '    %d passaram, %s%d falharam%s, %d avisos\n' "$OK" "$cor" "$FALHAS" "$zero" "$AVISOS"
if [[ $FALHAS -eq 0 ]]; then
    printf '    %sGateway comissionado.%s  Painel: http://%s:1880/dashboard/\n\n' \
           "$verde" "$zero" "$(hostname -I | awk '{print $1}')"
    exit 0
fi
printf '    %sHa falhas -- o gateway NAO esta pronto.%s\n\n' "$vermelho" "$zero"
exit 1
