# Passagem de sessão — estado em 2026-09-28

Documento para continuar o trabalho em outra máquina (o notebook) com o
Claude Code. **Leia inteiro antes de agir.** Não contém senha nenhuma.

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
- Nome na rede: `insightx.local` (avahi). Na rede antiga tinha cabo
  `192.168.3.30` e Wi-Fi `192.168.3.23`; **mudou de rede desde então**.
- Backup da versão anterior na placa: `~/iot-monitoramento.bak-20260924`.
- Sudo sem senha está liberado (`/etc/sudoers.d/010-tom-nopasswd`);
  reverter quando o usuário pedir.
- **Não tem NetworkManager** (`nmcli`/`nmtui` não existem) — a doc de
  comissionamento ainda manda usar `nmtui`: corrigir.
- Pendente no painel: senha do nó PostgreSQL "InsightX" continua manual
  (fase 5).

### Acesso SSH a partir do notebook

Chave própria do notebook (o usuário roda, digitando a senha do `tom` uma
vez):

```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\id_orangepi -N '""'
type $HOME\.ssh\id_orangepi.pub | ssh tom@insightx.local "cat >> ~/.ssh/authorized_keys"
```

Depois: `ssh -i ~/.ssh/id_orangepi tom@insightx.local`. Na primeira
conexão, conferir a impressão digital da chave do host antes de aceitar:
ED25519 `SHA256:lfCr3CvpfsTCFmvGnjN0E1fsOSKQBTgd/WmgdbvMyA4`.

## Próximo passo imediato: testar um inversor real

O usuário quer ligar um inversor (provavelmente **PowerFlex 525**,
EtherNet/IP) na mesma rede do Orange Pi e do notebook. Ainda **sem
inversor conectado** no momento desta passagem.

1. Achar o Orange Pi na rede do notebook (`insightx.local` ou varredura
   da porta 22).
2. Achar o drive e confirmar EtherNet/IP (porta 44818). No PF525: `C128`
   [EN Addr Sel] = 1 para IP fixo por parâmetro (de fábrica é BOOTP),
   `C129–C132` IP, `C133–C136` máscara; religar o drive.
3. Cadastrar pelo **menu Inversores** do painel; conferir
   `journalctl -u insightx-inversores` e as leituras no dashboard.
4. Se não houver roteador: IP fixo adicional na porta de cabo do Orange Pi
   (via netplan/systemd-networkd, mantendo o DHCP) e acesso ao painel por
   hotspot do celular ou switch simples. Verificar se o Wi-Fi do OPi3 LTS
   (UWE5622) suporta modo AP antes de prometer rede própria.

## Revisão do projeto (pedida pelo usuário, por etapas)

| Etapa | Estado |
|---|---|
| 1. Painel | ✅ feita (widgets cortando conteúdo; gráficos do Detalhe mostravam a planta inteira) |
| 2. Gateway | ✅ feita e validada na placa (setup quebrava no passo 2; sudo; dialout; etc.) |
| 3. Firmware | ✅ firmwares corrigidos e compilados; ⬜ **drivers dos inversores ainda não revisados** |
| 4. Documentação | ⬜ acentos nos nomes das páginas ("Visao Geral", "Configuracao"…), `nmtui`, contagens |

## Firmware — estado da bancada

- **iX Node** (`ixnode-provisionamento`, ESP32-C6): compila sem avisos.
  Corrigido em 24/09: credenciais MQTT no portal; não apaga mais a config
  quando a rede some no boot (portal por 3 min com a config mantida);
  reconecta para sempre depois de conectado; lista de redes ficava fora do
  `<form>` (o portal nunca salvava).
- Gravado numa placa **ESP32-C6 com CH343** → id **`ixn-37ab58`**.
  Identidade e autoteste de vibração **passaram no chip**. Mas a placa
  entra em **brownout** na calibração de RF do Wi-Fi, nas duas portas USB.
  O ADXL estava com ligação errada (curto/inversão: com ele eram 480 resets
  de hardware); sem ele sobra o brownout do rádio. Próximo teste: fonte de
  celular (ver se a rede `iX-Node-37ab58` aparece) e/ou capacitor de
  100–470 µF entre 3V3 e GND. Ligação correta do ADXL no C6: VCC→3V3,
  GND→GND, SDA→GPIO6, SCL→GPIO7, CS→3V3, SDO→GND.
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
- Commitar assim que cada parte compilar/passar: nesta máquina um
  "Teleport auto-stash" do Claude Code já reverteu arquivos não
  commitados uma vez (recuperados com `git stash pop`).
