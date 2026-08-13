# =====================================================================
#  Grava o firmware iX Node no ESP32-C6 e abre o monitor serial.
#
#      .\gravar.ps1              # detecta a porta sozinho
#      .\gravar.ps1 -Porta COM7  # ou diga qual
#      .\gravar.ps1 -Apagar      # apaga a flash antes (limpa o NVS e
#                                #  forca o portal de configuracao)
# =====================================================================
param(
    [string]$Porta = "",
    [switch]$Apagar
)

# IDF_TARGET fica setado como esp32s3 nesta maquina (heranca do projeto do
# pendant) e SOBRESCREVE o alvo em silencio -- ja fez o primeiro build sair
# para o chip errado uma vez.
Remove-Item Env:IDF_TARGET -ErrorAction SilentlyContinue
. C:\esp\v5.4.4\esp-idf\export.ps1 | Out-Null
Remove-Item Env:IDF_TARGET -ErrorAction SilentlyContinue

Set-Location $PSScriptRoot

# --- Porta -----------------------------------------------------------
if (-not $Porta) {
    # O C6 tem USB-serial-JTAG nativo: aparece sozinho ao plugar, sem
    # conversor externo. COM1 e a porta legada da placa-mae, nunca e ele.
    $achadas = @(Get-CimInstance Win32_PnPEntity -EA SilentlyContinue |
        Where-Object { $_.Name -match '\(COM(\d+)\)' -and $_.Name -notmatch '\(COM1\)' } |
        ForEach-Object { if ($_.Name -match '\((COM\d+)\)') { $matches[1] } })

    if ($achadas.Count -eq 0) {
        Write-Output "Nenhuma porta serial nova encontrada."
        Write-Output "Plugue o C6 pela USB e rode de novo, ou passe -Porta COMx."
        exit 1
    }
    if ($achadas.Count -gt 1) {
        Write-Output "Mais de uma porta: $($achadas -join ', ')"
        Write-Output "Escolha com -Porta COMx (a COM6 e a placa FluidNC, nao o pendant)."
        exit 1
    }
    $Porta = $achadas[0]
}
Write-Output "Porta: $Porta"

# --- Grava -----------------------------------------------------------
if ($Apagar) {
    Write-Output "`n=== apagando a flash (limpa Wi-Fi/MQTT gravados) ==="
    idf.py -p $Porta erase-flash
    if (-not $?) { Write-Output "falhou ao apagar"; exit 1 }
}

Write-Output "`n=== gravando ==="
idf.py -p $Porta flash
if (-not $?) {
    Write-Output "`nFalhou. Se der 'Wrong boot mode' ou nao achar o chip:"
    Write-Output "  segure BOOT, aperte e solte RESET, solte BOOT, e rode de novo."
    exit 1
}

Write-Output "`n=== monitor (Ctrl+] para sair) ==="
Write-Output "Procure no log, nesta ordem:"
Write-Output "  1. 'auto-teste vibracao: PASSOU'   <- a matematica no chip real"
Write-Output "  2. 'LED de identificacao no GPIO8'"
Write-Output "  3. 'no virgem -- subindo portal'    <- se a flash foi apagada"
Write-Output "  4. 'ouvindo comandos em monitoramento/ixn-xxxxxx/cmd'"
Write-Output ""
idf.py -p $Porta monitor
