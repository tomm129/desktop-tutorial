"""Compila-verifica a matematica de vibracao do firmware.

Extrai as funcoes de calculo direto do main.cpp (sem copiar a mao, que
envelhece), envolve em stubs minimos do Arduino e compila com o
cross-compiler da Espressif. Nao EXECUTA o codigo -- o algoritmo e validado
numericamente por testa_vibracao.py; aqui o que se checa e se o C++ como
escrito compila limpo, sem aviso.

Existe porque nao ha PlatformIO nesta maquina: sem isto, um erro de digitacao
na matematica so apareceria na bancada, com a placa na mao.

    python tools/testes/checa_firmware.py
"""
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
MAIN = RAIZ / "firmware" / "esp32-campo" / "src" / "main.cpp"
CFG = RAIZ / "firmware" / "esp32-campo" / "include" / "config.example.h"
SAIDA = Path(__file__).resolve().parent / "_vib_extraido.cpp"

# Qualquer g++ da Espressif serve para checar sintaxe e tipos; o alvo nao
# importa porque nada aqui e especifico de arquitetura.
PADROES = [
    r"C:\Espressif\tools\xtensa-esp-elf\*\xtensa-esp-elf\bin\xtensa-esp32s3-elf-g++.exe",
    r"C:\Espressif\tools\riscv32-esp-elf\*\riscv32-esp-elf\bin\riscv32-esp-elf-g++.exe",
]


def achar_compilador():
    import glob
    for p in PADROES:
        achados = sorted(glob.glob(p))
        if achados:
            return Path(achados[-1])
    for nome in ("g++", "clang++"):
        from shutil import which
        c = which(nome)
        if c:
            return Path(c)
    return None


def main():
    src = MAIN.read_text(encoding="utf-8")
    try:
        ini = src.index("struct ResultadoVibracao {")
        fim = src.rindex("// ===", 0, src.index("//  Amostra e buffer offline"))
    except ValueError as e:
        print(f"FALHA: nao achei os marcadores no main.cpp ({e})")
        print("       Se o arquivo foi reorganizado, ajuste os marcadores aqui.")
        return 1
    trecho = src[ini:fim]

    cfg = CFG.read_text(encoding="utf-8")
    defines = []
    for chave in ("VIB_AMOSTRAS", "VIB_AQUECIMENTO", "VIB_INTERVALO_US", "VIB_HP_HZ"):
        m = re.search(r"^#define\s+%s\s+(\S+)" % chave, cfg, re.M)
        if not m:
            print(f"FALHA: {chave} nao encontrado em config.example.h")
            return 1
        defines.append(f"#define {chave} {m.group(1)}")

    SAIDA.write_text("""// Gerado por checa_firmware.py -- nao editar, nao versionar.
#include <math.h>
#include <stdint.h>

%s

// --- Stubs do Arduino/Adafruit, so o bastante para compilar ---------------
struct _Accel { float x, y, z; };
struct sensors_event_t { _Accel acceleration; };
struct _ADXL { void getEvent(sensors_event_t *e) { e->acceleration.x = 0;
               e->acceleration.y = 0; e->acceleration.z = 9.8f; } };
static _ADXL adxl;
static unsigned long micros() { return 0; }
static void delayMicroseconds(unsigned int) {}

%s

// Forca a instanciacao para nada ser descartado por nao-uso.
extern "C" int _checagem(void);
int _checagem(void) {
    ResultadoVibracao r = medirVibracao();
    return (int)(r.rms_g + r.pico_g + r.crista + r.vel_mm_s + r.fs_hz);
}
""" % ("\n".join(defines), trecho), encoding="utf-8")

    print(f"extraido: {len(trecho.splitlines())} linhas de main.cpp")

    gxx = achar_compilador()
    if not gxx:
        print("PULADO: nenhum compilador C++ encontrado.")
        print("        Instale o ESP-IDF ou qualquer g++/clang++ no PATH.")
        return 0

    print(f"compilando com {gxx.name} (-Wall -Wextra -O2)\n")
    r = subprocess.run(
        [str(gxx), "-c", "-std=gnu++17", "-Wall", "-Wextra",
         "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
         "-O2", str(SAIDA), "-o", str(SAIDA.with_suffix(".o"))],
        capture_output=True, text=True)

    saida = (r.stdout + r.stderr).strip()
    if saida:
        print(saida)
        print()

    for lixo in (SAIDA, SAIDA.with_suffix(".o")):
        lixo.unlink(missing_ok=True)

    if r.returncode != 0:
        print(f"RESULTADO: FALHA DE COMPILACAO (codigo {r.returncode})")
        return r.returncode
    if saida:
        print("RESULTADO: compilou, mas COM AVISOS acima.")
        return 1
    print("RESULTADO: compilou limpo, sem avisos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
