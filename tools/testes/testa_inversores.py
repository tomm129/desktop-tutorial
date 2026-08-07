"""Testa a logica PURA dos sidecars de inversor e da sonda de MCSA.

Nada aqui toca hardware. O que se verifica e o que da para verificar sem
drive: conversao de endereco, decodificacao de alarme, e se a analise
espectral acha (e deixa de achar) o que deveria.

    python tools/testes/testa_inversores.py
"""
import csv
import importlib.util
import math
import os
import random
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

falhas = 0


def ok(cond, nome, extra=""):
    global falhas
    if not cond:
        falhas += 1
    print(f"  [{'OK ' if cond else 'FALHA'}] {nome}{('  ' + extra) if extra else ''}")


def carregar(caminho, nome):
    """Importa um modulo por caminho, sem precisar de pacote."""
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


# =====================================================================
print("\n=== 1. Danfoss: conversao de parametro para registrador ===")
try:
    danfoss = carregar(RAIZ / "integracoes" / "danfoss_vlt" / "danfoss_mqtt.py",
                       "danfoss_mqtt")
except SystemExit as e:
    print(f"  PULADO: {e}")
    danfoss = None

if danfoss:
    # (PNU x 10) - 1. Se a bancada mostrar que a familia usa outra regra,
    # este teste tem de mudar JUNTO com o codigo -- e o proposito e que a
    # mudanca seja consciente, nao silenciosa.
    casos = [(1614, 16139), (1613, 16129), (1630, 16299), (1690, 16899)]
    for pnu, esperado in casos:
        obtido = danfoss.endereco_de(pnu)
        ok(obtido == esperado, f"PNU {pnu} -> registrador {esperado}",
           f"-> {obtido}")

    print("\n=== 2. Danfoss: decodificacao da palavra de alarme ===")
    # A palavra e um campo de BITS: varios alarmes ao mesmo tempo.
    cod, txt = danfoss.decodificar_alarmes(0)
    ok(cod == 0 and txt is None, "palavra zero = sem alarme")

    cod, txt = danfoss.decodificar_alarmes(1 << 13)
    ok(cod == 13, "bit 13 -> codigo 13", f"-> {cod}")
    ok(txt and "Sobrecorrente" in txt, "bit 13 traduz para Sobrecorrente",
       f"-> {txt}")

    # Dois alarmes juntos: nenhum pode ficar escondido.
    cod, txt = danfoss.decodificar_alarmes((1 << 9) | (1 << 29))
    ok(cod == 9, "com dois alarmes, o codigo e o menor bit", f"-> {cod}")
    ok(txt.count("|") == 1, "os dois textos aparecem", f"-> {txt}")

    cod, txt = danfoss.decodificar_alarmes(1 << 21)
    ok(cod == 21 and "ver manual" in txt,
       "bit desconhecido nao vira 'sem falha'", f"-> {txt}")

    print("\n=== 3. Danfoss: perfis por familia ===")
    # O grupo 16 difere entre familias, e ler um parametro inexistente
    # derrubava a leitura inteira. Estes testes travam a diferenca.
    fc302 = set(danfoss.PERFIS["fc302"])
    fc51 = set(danfoss.PERFIS["fc51"])

    for c in ("frequencia_hz", "corrente_a", "tensao_v", "dc_bus_v"):
        ok(c in fc302 and c in fc51, f"as duas familias leem {c}")

    ok("rpm" in fc302, "FC 301/302 le rpm (16-17)")
    ok("torque_nm" in fc302, "FC 301/302 le torque (16-16)")
    ok("rpm" not in fc51, "FC 51 NAO tem 16-17 Speed [RPM]")
    ok("torque_nm" not in fc51, "FC 51 NAO tem 16-16 Torque")
    ok(danfoss.PERFIS["fc301"] is danfoss.PERFIS["fc302"],
       "fc301 usa o mesmo perfil do fc302")
    ok(fc51 < fc302, "o perfil do FC 51 e subconjunto do FC 302")

    # Os essenciais tem de existir em todo perfil: sem eles o pacote nao
    # serve, e o codigo deixa a excecao subir de proposito.
    for perfil in ("fc302", "fc51"):
        ok(danfoss.ESSENCIAIS <= set(danfoss.PERFIS[perfil]),
           f"perfil {perfil} contem os campos essenciais")

# =====================================================================
print("\n=== 4. Sonda de MCSA: acha o que deve, ignora o que nao deve ===")
sonda = carregar(RAIZ / "tools" / "mcsa_sonda.py", "mcsa_sonda")

# Motor de referencia: 4 polos, 60 Hz, 1760 rpm -> s = 2,22% -> 2sf = 2,67 Hz
F_2SF = 2.0 * ((1800.0 - 1760.0) / 1800.0) * 60.0
ok(abs(F_2SF - 2.67) < 0.01, "2·s·fs do motor de referencia = 2,67 Hz",
   f"-> {F_2SF:.2f} Hz")

s = sonda.escorregamento(1760, 4, 60.0)
ok(abs(s - 0.0222) < 0.0005, "escorregamento calculado da placa",
   f"-> {s*100:.2f}%")


def sintetico(mod_amp, mod_f, dur=60.0, taxa=12.0, media=12.0, semente=7):
    """Serie com jitter e quantizacao de 0,01 A, como o dado real."""
    rnd = random.Random(semente)
    t, x, tempo = [], [], 0.0
    while tempo < dur:
        v = media
        if mod_amp:
            v += media * mod_amp * math.sin(2 * math.pi * mod_f * tempo)
        v += rnd.gauss(0, 0.02)
        x.append(round(v / 0.01) * 0.01)
        t.append(tempo)
        tempo += 1.0 / taxa + rnd.gauss(0, 0.012)
    return t, x


def pico_em(t, x, f_ini=0.3, f_fim=7.5):
    esp = sonda.dft_banda(t, x, f_ini, f_fim, 220)
    import statistics
    amps = [a for _, a in esp]
    pf, pa = max(esp, key=lambda p: p[1])
    return pf, pa / statistics.median(amps)

# Barra quebrada: modulacao de 1,5% em 2,67 Hz
t, x = sintetico(0.015, F_2SF)
pf, razao = pico_em(t, x)
ok(abs(pf - F_2SF) < 0.15, "acha a raia de barra quebrada em 2,67 Hz",
   f"-> {pf:.2f} Hz")
ok(razao > 10, "e ela se destaca do piso", f"-> {razao:.0f}x")

# Defeito incipiente de 0,4%: o caso dificil, perto da quantizacao
t, x = sintetico(0.004, F_2SF)
pf, razao = pico_em(t, x)
ok(abs(pf - F_2SF) < 0.15 and razao > 5,
   "acha defeito incipiente de 0,4%", f"-> {pf:.2f} Hz, {razao:.0f}x")

# Oscilacao de carga em 0,8 Hz: existe raia, mas NAO e barra de rotor.
t, x = sintetico(0.020, 0.8)
pf, razao = pico_em(t, x)
ok(razao > 10, "acha a oscilacao de carga", f"-> {pf:.2f} Hz")
ok(abs(pf - F_2SF) > 0.5,
   "e NAO a confunde com 2·s·fs (evita falso positivo)",
   f"-> {pf:.2f} Hz vs {F_2SF:.2f} Hz esperado")

# Motor sadio: so ruido. Nao pode inventar raia.
t, x = sintetico(0.0, 0.0)
pf, razao = pico_em(t, x)
ok(razao < 4, "motor sadio nao produz raia falsa", f"-> {razao:.1f}x")

print("\n=== 5. Sonda: amostragem irregular nao desloca a raia ===")
# Jitter alto de proposito: e o que a leitura por rede realmente faz. A DFT
# usa o instante medido de cada amostra justamente para isto.
rnd = random.Random(11)
t, x, tempo = [], [], 0.0
while tempo < 60.0:
    x.append(round((12.0 + 12.0 * 0.015 * math.sin(2 * math.pi * F_2SF * tempo)
                    + rnd.gauss(0, 0.02)) / 0.01) * 0.01)
    t.append(tempo)
    tempo += 1.0 / 12.0 + abs(rnd.gauss(0, 0.035))   # jitter de 35 ms
pf, razao = pico_em(t, x)
ok(abs(pf - F_2SF) < 0.2, "com jitter de 35 ms a raia continua no lugar",
   f"-> {pf:.2f} Hz, {razao:.0f}x")

print("\n=== 6. Sonda: le e escreve CSV ===")
with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "c.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "corrente_a"])
        for ti, xi in zip(t[:50], x[:50]):
            w.writerow([f"{ti:.6f}", f"{xi:.3f}"])
    t2, x2 = sonda.ler_csv(p)
    ok(len(t2) == 50 and abs(t2[10] - t[10]) < 1e-6, "CSV de ida e volta")

print()
print("RESULTADO: todas as verificacoes passaram." if not falhas
      else f"RESULTADO: {falhas} falha(s).")
sys.exit(1 if falhas else 0)
