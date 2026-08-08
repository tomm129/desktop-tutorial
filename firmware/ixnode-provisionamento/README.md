# iX Node — provisionamento (ESP-IDF)

Firmware **mínimo**, feito para validar em bancada o que tem mais risco de
surpresa: **portal cativo**, **gravação em NVS**, **identidade por MAC** e
**reconexão**. A medição (ADXL345 + MLX90614) e o buffer offline são
portados depois, do firmware Arduino que já existe e já foi testado.

> ✅ **Compila** para `esp32c6` com ESP-IDF v5.4.4 (1,04 MB, 32% de folga).
> ❌ **Não foi gravado nem executado** em placa nenhuma.

## O problema que ele resolve

No firmware Arduino atual, Wi-Fi, broker e `DEVICE_ID` são `#define` em
`config.h`. Trocar de rede, de IP do gateway ou de identidade exige
**recompilar e regravar**. Para dois nós de bancada, tudo bem. Para vinte
numa planta, inviável — e para vender, impossível.

## Como funciona

```
1. id = "ixn-" + 3 últimos bytes do MAC     ← sem configuração nenhuma
2. NVS tem Wi-Fi gravado?
     não → sobe portal cativo, grava, reinicia
3. conecta; falhou 5 vezes → apaga a config e volta ao portal
4. conecta no MQTT e publica um batimento
```

### 1. Identidade vem do hardware

`ixnode_id()` devolve `ixn-a1b2c3`, dos três últimos bytes do MAC do rádio.

**Uma firmware, igual em toda unidade.** Um `DEVICE_ID` em `config.h`
obrigaria a compilar uma imagem por nó — e um erro de digitação criaria dois
dispositivos publicando no mesmo tópico, que o painel lê como um só,
alternando entre duas máquinas.

O MAC usado é o `ESP_MAC_WIFI_STA`, o mesmo que aparece no roteador. Usar
outro faria o id impresso na etiqueta divergir do que o administrador de rede
vê.

### 2. Portal cativo

Sobe como ponto de acesso **`iX-Node-a1b2c3`** — mesmo sufixo do id, para
que com vários nós novos ligados dê para saber qual é qual, e para bater com
a etiqueta do invólucro.

Três peças:

| Peça | Por que existe |
|---|---|
| **SoftAP** | a rede à qual o celular se conecta |
| **Servidor DNS** | responde *qualquer* consulta com `192.168.4.1` — é isto que faz o celular **abrir a página sozinho** |
| **Servidor HTTP** | o formulário, e o redirecionamento das sondas de conectividade |

Sem o DNS, o usuário teria de saber que precisa digitar `192.168.4.1` no
navegador. Em campo, com o celular na mão, ninguém sabe.

O formulário traz a **lista de redes ao alcance com o RSSI**, em vez de
exigir o SSID digitado. Digitar SSID à mão é fonte garantida de erro — uma
maiúscula trocada, um espaço no fim — e o sintoma (não conecta) não diz qual
foi o engano.

**A rede do portal é aberta, de propósito.** Uma senha teria de ser conhecida
por quem instala, ou seria a mesma em todos os nós — o que não protege nada e
emperra a instalação. A janela de exposição é a de um nó virgem, e o que se
pode fazer nela é configurá-lo.

### 3. Rede que não conecta volta ao portal

Cinco tentativas e o nó **apaga a configuração e reinicia no portal**. Senha
trocada, roteador substituído, nó mudado de lugar — tudo isso se resolve com
o celular, sem cabo e sem PC.

## Como compilar e gravar

```powershell
# Carrega o ambiente (uma vez por terminal)
. C:\esp\v5.4.4\esp-idf\export.ps1

cd firmware\ixnode-provisionamento
idf.py set-target esp32c6      # ou esp32s3
idf.py build
idf.py -p COM7 flash monitor   # ajuste a porta
```

> ⚠️ **Se houver `IDF_TARGET` no ambiente, ela vence o `set-target` — em
> silêncio.** Aconteceu aqui: a máquina tinha `IDF_TARGET=esp32s3` de outro
> projeto, e o primeiro build saiu para S3 mesmo tendo pedido C6. O log só
> revela isso na linha final do `esptool`. Se desconfiar, confira:
>
> ```powershell
> Remove-Item Env:IDF_TARGET -ErrorAction SilentlyContinue
> ```
>
> O `sdkconfig` é **gitignored** pelo mesmo motivo: versioná-lo carregaria o
> target de quem compilou por último.

## Roteiro de teste em bancada

1. **Grave e abra o monitor.** Deve aparecer:
   ```
   iX Node  ixn-XXXXXX
   no virgem — subindo portal de configuracao
   portal no ar: rede 'iX-Node-XXXXXX', http://192.168.4.1/
   ```
2. **No celular**, conecte na rede `iX-Node-XXXXXX`. A página deve abrir
   **sozinha** — se abrir, o DNS está funcionando.
3. **Preencha** rede, senha e o IP do gateway. Salve.
4. O nó reinicia, conecta e o log mostra `MQTT conectado`.
5. **No painel**, tela de Configuração: `ixn-XXXXXX` aparece em *aguardando
   cadastro*.

O passo 5 é o teste de ponta a ponta: identidade → rede → broker → painel.

## O que ainda não tem

- [ ] Sensores (ADXL345, MLX90614) — portar do firmware Arduino
- [ ] Buffer offline com decimação — idem
- [ ] Botão físico para forçar o portal sem apagar a config
- [ ] Piscar LED sob comando, para identificar qual nó é qual no painel
- [ ] OTA pelo gateway
