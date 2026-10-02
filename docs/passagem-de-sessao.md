# Passagem de sessão — estado em 2026-10-01

Documento para continuar o trabalho em outra máquina com o Claude Code.
**Leia inteiro antes de agir.** Não contém senha nenhuma.

## Feito em 2026-10-01 (no notebook)

- **Primeiro inversor real no InsightX, de ponta a ponta.** PowerFlex 525
  (0,5 HP, 460 V) em `192.168.1.30`, lido pelo Orange Pi na rede do drive,
  cadastrado pelo **menu Inversores** (`inv-svb1`, tag `svb1`) e atribuído
  pela tela **Configuração** a um ativo novo, *Esteira de saida / Bancada de
  testes / Motor 1*. Card **OK, verde, 0,66 A, "rodando"**, com o motor a
  ~23,5 Hz pelo teclado. Valores conferidos contra o teclado do drive
  (b001, b003, b005).
- **Defeito achado na bancada e corrigido** (commit `3f01d60`, enviado e
  instalado em `/opt/iot` no Orange Pi; backup da versão anterior em
  `~/backup-powerflex-20261001`): a falha ativa vinha do *DPI Fault Object*
  0x97/4, que no drive real é o **ponteiro da fila de falhas** e fica em 1
  para sempre — o ativo apareceria **CRÍTICO** com o motor girando
  normalmente. Indicador certo, medido provocando F004: status do
  **Identity** (0x01/1/5), bit 10 — `0x0030` → `0x0430` → `0x0030`. O drive
  real **recusa Unconnected Send** (o modo `auto` resolve sozinho). Detalhes
  no README de `integracoes/powerflex525`.
- **Orange Pi de volta à rede.** Ele "sumia" por **fonte fraca** (não
  terminava de subir a rede); com a fonte trocada, voltou normal.
  - Wi-Fi: rede do hotspot do celular **POCOX4** acrescentada em
    `/etc/netplan/30-wifis-dhcp.yaml` (senha gravada só como hash PSK),
    mantendo a rede de casa. Backup: `30-wifis-dhcp.yaml.bak-20261001`.
    No hotspot ele ficou em `10.116.129.24`.
  - Cabo: **IP fixo extra `192.168.1.50`** para a rede do inversor, em
    `/etc/netplan/20-cabo-inversor.yaml`, mantendo o DHCP.
  - **Atenção:** cada `netplan apply` pode trocar o IP do cabo (DHCP). Fazer
    mudanças de rede pelo Wi-Fi e confirmar o IP depois.
- **Acesso SSH do notebook configurado**: chave `~/.ssh/id_orangepi`
  (impressão digital do host conferida). Ligando o cabo direto no notebook,
  o compartilhamento de internet do Windows dá IP `192.168.137.x` ao Orange Pi.
- **Ambiente do notebook instalado**: Python 3.12 (com `pycomm3`,
  `pymodbus`, `paho-mqtt`, `numpy`), ESP-IDF v5.4.4 (alvos C6/C3), PlatformIO.
  Suíte `tools/testes/` passando inteira.
- **Bancada ESP32-C6 (`ixn-37ab58`) gravada pelo notebook**: autoteste de
  vibração passou no chip; o brownout é da **alimentação da placa** —
  estável só até **13 dBm** de potência de rádio (varredura 20→10 dBm). O
  usuário vai trocar por **ESP32-S3 Super Mini**; para alcance, preferir
  placa com conector U.FL (ex. XIAO ESP32S3).

## Regras combinadas com o usuário

- **Configuração pela interface, quase zero edição de arquivo.** Tudo que
  hoje exige editar arquivo deve virar menu no painel.
- **Nós ESP32 são provisionados pelo portal no primeiro boot**
  (`firmware/ixnode-provisionamento`): Wi-Fi, gateway e usuário/senha do
  MQTT. O nome do nó é dado **no painel**, no fluxo de adição de
  dispositivo (tela Configuração). **Não** preparar `config.h`: o
  `firmware/esp32-campo` é legado.
- **Senhas quem digita é o usuário.** O Claude não digita senha em prompt
  nenhum (sudo, setup, portal) e não copia credencial para arquivo
  versionado. Acesso à placa só por chave SSH.
- Nunca versionar: `config.h`, `config.env`, `dados/ativos.json`,
  `dados/inversores.json`, `flows_cred.json`, chaves.
- Siemens fica de fora até o levantamento na fábrica. PowerFlex é só o 525
  (inclusive encadeados em Multi-Drive).

## Gateway (Orange Pi 3 LTS)

- Recomissionado em **24/09**: `setup_orangepi.sh` completo e
  `verifica_instalacao.sh` com **35 OK, 0 falhas**.
- Usuário Linux `tom`. Usuário MQTT **`qmd`** (senha: só o usuário sabe).
- Nome na rede: `insightx.local` (avahi). Em 2026-10-01: Wi-Fi POCOX4
  `10.116.129.24`, cabo com IP fixo extra `192.168.1.50` (rede do inversor).
  O `insightx.local` não resolveu no notebook — usar o IP.
- Verificar/trocar a **fonte** se a placa voltar a não aparecer na rede.
- Backup da versão anterior na placa: `~/iot-monitoramento.bak-20260924`.
- Sudo sem senha está liberado (`/etc/sudoers.d/010-tom-nopasswd`);
  reverter quando o usuário pedir.
- **Não tem NetworkManager** (`nmcli`/`nmtui` não existem) — a doc de
  comissionamento ainda manda usar `nmtui`: corrigir.
- Pendente no painel: senha do nó PostgreSQL "InsightX" continua manual
  (fase 5).

### Acesso SSH a partir do notebook

**Já configurado no notebook** em 2026-10-01: `ssh -i ~/.ssh/id_orangepi
tom@10.116.129.24`. Em outra máquina, repetir (o usuário roda, digitando a
senha do `tom` uma vez):

```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\id_orangepi -N '""'
type $HOME\.ssh\id_orangepi.pub | ssh tom@<IP-do-Orange-Pi> "cat >> ~/.ssh/authorized_keys"
```

Na primeira conexão, conferir a impressão digital da chave do host antes de
aceitar: ED25519 `SHA256:lfCr3CvpfsTCFmvGnjN0E1fsOSKQBTgd/WmgdbvMyA4`.

**O Orange Pi não tem `git`**: o setup copia o repositório para
`~/iot-monitoramento` e instala em `/opt/iot`. Atualização de código = copiar
o(s) arquivo(s) para os dois lugares (com backup) e reiniciar o serviço.

## Próximos passos

1. ~~Testar um inversor real~~ — **FEITO** em 2026-10-01 (ver topo).
2. **Revisar os drivers dos inversores contra drive real** (etapa 3 da
   revisão): o Danfoss ainda só foi testado em simulador.
3. **Multi-Drive**: sem indicador conhecido de falha ativa para drives
   encadeados (o Identity é um por nó) — eles publicam só a última falha.
4. **Doc de comissionamento**: trocar `nmtui` por netplan e registrar o IP
   fixo extra para rede de inversor (como foi feito hoje).
5. Placas ESP32-S3 Super Mini (quando chegarem): instalar o alvo `esp32s3`
   no ESP-IDF, LED WS2812 provavelmente no GPIO48, escolher pinos I²C que
   existam na placa e repetir a varredura de potência de rádio.

## Revisão do projeto (pedida pelo usuário, por etapas)

| Etapa | Estado |
|---|---|
| 1. Painel | ✅ feita (widgets cortando conteúdo; gráficos do Detalhe mostravam a planta inteira) |
| 2. Gateway | ✅ feita e validada na placa (setup quebrava no passo 2; sudo; dialout; etc.) |
| 3. Firmware | ✅ firmwares corrigidos e compilados; ✅ **PowerFlex 525 validado em drive real** (falha ativa corrigida); ⬜ Danfoss ainda só em simulador |
| 4. Documentação | ⬜ acentos nos nomes das páginas ("Visao Geral", "Configuracao"…), `nmtui`, contagens |

## Firmware — estado da bancada

- **iX Node** (`ixnode-provisionamento`, ESP32-C6): compila sem avisos.
  Corrigido em 24/09: credenciais MQTT no portal; não apaga mais a config
  quando a rede some no boot (portal por 3 min com a config mantida);
  reconecta para sempre depois de conectado; lista de redes ficava fora do
  `<form>` (o portal nunca salvava).
- Gravado numa placa **ESP32-C6 com CH343** → id **`ixn-37ab58`**.
  Identidade e autoteste de vibração **passaram no chip**. O brownout na
  calibração de RF é da **alimentação da placa** (confirmado em 2026-10-01
  no notebook, sem nada ligado nela): instável de 20 a 14 dBm, estável em
  13 dBm e abaixo, com o portal `iX-Node-37ab58` no ar. A placa ficou com
  um build de teste a 13 dBm (fora do repositório). Conserto: capacitor de
  100–470 µF entre 3V3 e GND, ou outra placa (S3 Super Mini a caminho).
  Ligação correta do ADXL no C6: VCC→3V3, GND→GND, SDA→GPIO6, SCL→GPIO7,
  CS→3V3, SDO→GND.
- **Firmware de campo** (legado): build completo com PlatformIO OK;
  corrigido endereço do MLX90614 (era procurado em 0x2E), comandos
  identificar/reiniciar e reconexão sem travar o loop.

## Fases da configuração pela interface

1. Catálogo + serviço único de inversores — ✅
2. Menu Inversores no painel — ✅
3. Senha única nas telas de configuração (validada no servidor) — ⬜
4. Botão "Testar conexão" — ⬜
5. Credenciais do MQTT e do banco no Node-RED automáticas (Admin API) — ⬜

Em espera: executável Windows do simulador multi-instância; redesenho
visual do painel no estilo do simulador (protótipo antes de aplicar).

## Ambiente de desenvolvimento no notebook

- Python 3.12+ e Node 20+. Testes: ver `tools/testes/README.md`
  (os com simulador precisam de `pymodbus`, `pycomm3`, `paho-mqtt`).
- Firmware iX Node: ESP-IDF **v5.4.4**; remover `IDF_TARGET` do ambiente
  antes de compilar (ver README do firmware).
- No notebook o Git do repositório usa autor "Tom Dutra" (configurado só
  neste repositório em 2026-10-01).
- Commitar assim que cada parte compilar/passar: nesta máquina um
  "Teleport auto-stash" do Claude Code já reverteu arquivos não
  commitados uma vez (recuperados com `git stash pop`).
