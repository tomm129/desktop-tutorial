#!/usr/bin/env python3
"""Sonda de viabilidade para MCSA a partir da corrente do PowerFlex 525.

POR QUE ESTA FERRAMENTA EXISTE
==============================

A MCSA clássica procura bandas laterais em torno da frequência de linha, em
f_s·(1 ± 2ks). Para um motor de 4 polos, 60 Hz, 1760 rpm de placa:

    escorregamento s = (1800 - 1760) / 1800 = 0,0222
    banda lateral    = 60 · (1 ± 2·0,0222) = 57,3 Hz e 62,7 Hz

Separar uma raia a 2,7 Hz da fundamental exige resolução de 0,01 a 0,05 Hz,
o que significa janela de 20 a 100 s, e taxa de amostragem de ao menos 5 kHz
para pegar os 60 Hz sem aliasing.

**Nada disso é possível pelo inversor**, por dois motivos independentes:

  1. O parâmetro b003 é a corrente RMS -- um escalar que o próprio drive já
     integrou. A portadora de 60 Hz não está mais lá. Amostrar rápido não
     recupera o que já foi descartado.
  2. Mensageria explícita (UCMM) faz uma ida-e-volta por leitura. Não chega
     perto de 5 kHz; o sidecar hoje lê a 1 Hz.

A HIPÓTESE QUE ESTA SONDA TESTA
===============================

Barra de rotor quebrada não só cria bandas laterais: ela **modula a
amplitude** da corrente, e o envelope resultante oscila em 2·s·f_s -- no
motor acima, ~2,7 Hz. Isso é técnica reconhecida (envelope/demodulação).

E a corrente RMS que o drive publica **é**, essencialmente, esse envelope:
o cálculo de RMS é uma integração do módulo da corrente, ou seja, uma
demodulação. A portadora sumiu, mas a modulação pode ter sobrevivido.

Se sobreviveu, basta amostrar a corrente RMS a ~10-20 Hz por ~60 s e
procurar uma raia em 2·s·f_s. Isso o inversor talvez consiga entregar.

O QUE PODE MATAR A IDEIA (e é o que se mede aqui)
=================================================

  a) A taxa de leitura que o link realmente sustenta. Precisa de >= 6 Hz
     (Nyquist para 2,7 Hz) com folga -- na prática >= 10 Hz.
  b) O filtro interno do drive. Se ele média a corrente numa janela longa,
     age como passa-baixa e atenua os 2,7 Hz antes de nós vermos.
  c) A quantização de 0,01 A. Uma modulação de 1% em 12 A dá 0,12 A = 12
     degraus: visível. Uma de 0,3% dá 3 degraus: no limite.

USO
===

    # captura 60 s do drive e ja analisa
    python tools/mcsa_sonda.py --capturar 60 --ip 192.168.1.20

    # so analisa uma captura antiga
    python tools/mcsa_sonda.py --analisar captura.csv --rpm-placa 1760

O CSV tem duas colunas: t_s (segundos desde o início) e corrente_a.
"""
import argparse
import csv
import math
import os
import statistics
import sys
import time

# =====================================================================
#  Análise espectral
# =====================================================================


def dft_banda(t, x, f_ini, f_fim, n_bins):
    """DFT direta numa banda estreita, usando os INSTANTES REAIS de cada
    amostra.

    Não usa FFT de propósito. A FFT exige amostragem uniforme, e a leitura
    por rede tem jitter -- cada ida-e-volta demora um pouco diferente.
    Tratar amostra irregular como se fosse regular espalha energia e pode
    inventar raia onde não há. Somando com o t medido de cada amostra, o
    jitter deixa de ser erro e vira só ruído de fase.

    A banda é estreita (fração de Hz até poucos Hz), então o custo de uma
    DFT direta é irrelevante: alguns milhares de operações.
    """
    n = len(x)
    media = sum(x) / n
    xc = [v - media for v in x]          # tira o DC, que domina tudo

    saida = []
    for k in range(n_bins):
        f = f_ini + (f_fim - f_ini) * k / (n_bins - 1)
        re = im = 0.0
        for i in range(n):
            ang = 2.0 * math.pi * f * t[i]
            re += xc[i] * math.cos(ang)
            im -= xc[i] * math.sin(ang)
        # Amplitude de pico do senoide equivalente.
        amp = 2.0 * math.sqrt(re * re + im * im) / n
        saida.append((f, amp))
    return saida


def escorregamento(rpm_placa, polos, f_hz):
    """Escorregamento a partir da placa e da frequência de saída do drive."""
    if not rpm_placa or not polos or not f_hz:
        return None
    n_sinc = 120.0 * f_hz / polos
    if n_sinc <= 0:
        return None
    return (n_sinc - rpm_placa) / n_sinc


def analisar(t, x, rpm_placa, polos, f_saida):
    dur = t[-1] - t[0]
    n = len(x)
    fs = (n - 1) / dur if dur > 0 else 0.0

    # Jitter: quanto o intervalo entre leituras varia. Importa porque é ele
    # que decide se dá para confiar no espectro.
    dts = [t[i + 1] - t[i] for i in range(n - 1)]
    dt_med = statistics.mean(dts)
    dt_dp = statistics.pstdev(dts) if len(dts) > 1 else 0.0

    print("\n" + "=" * 68)
    print("AQUISIÇÃO")
    print("=" * 68)
    print(f"  amostras          : {n}")
    print(f"  duração           : {dur:.1f} s")
    print(f"  taxa média        : {fs:.2f} Hz")
    print(f"  intervalo         : {dt_med*1000:.1f} ms  (desvio {dt_dp*1000:.1f} ms)")
    print(f"  banda útil (Nyq.) : {fs/2:.2f} Hz")
    print(f"  resolução (1/T)   : {1.0/dur:.4f} Hz" if dur > 0 else "")

    corr_med = statistics.mean(x)
    corr_dp = statistics.pstdev(x)
    print(f"  corrente média    : {corr_med:.3f} A")
    print(f"  variação (desvio) : {corr_dp:.4f} A  "
          f"({100*corr_dp/corr_med:.2f}% da média)" if corr_med else "")

    # Quantização: quantos degraus de 0,01 A a variação ocupa. Abaixo de
    # uns poucos degraus, o que se vê é o degrau do conversor, não o motor.
    degraus = corr_dp / 0.01 if corr_dp else 0
    print(f"  degraus de 0,01 A : {degraus:.1f}", end="")
    if degraus < 3:
        print("   <-- NO LIMITE: a variação mal sai da quantização")
    else:
        print()

    s = escorregamento(rpm_placa, polos, f_saida)
    f_esperada = 2.0 * s * f_saida if s else None

    print("\n" + "=" * 68)
    print("HIPÓTESE")
    print("=" * 68)
    if f_esperada:
        print(f"  placa {rpm_placa:.0f} rpm, {polos} polos, saída {f_saida:.2f} Hz")
        print(f"  escorregamento s  : {s*100:.2f}%")
        print(f"  2·s·fs esperado   : {f_esperada:.2f} Hz  <-- é esta raia "
              f"que a barra quebrada produz")
    else:
        print("  sem dados de placa: procurando em toda a banda plausível")

    if fs < 6.0:
        print(f"\n  ATENÇÃO: taxa de {fs:.2f} Hz não alcança nem o Nyquist de "
              f"uma raia de 2,7 Hz.")
        print("  Qualquer pico abaixo pode ser rebatimento (aliasing), não sinal.")

    # Banda de busca: escorregamento plausível de 0,5% a 6% num motor de
    # indução; 2sf fica então entre ~0,6 e ~7,2 Hz a 60 Hz.
    f_ini = 0.3
    f_fim = min(7.5, fs / 2.0 * 0.95) if fs > 1 else 7.5
    if f_fim <= f_ini:
        print("\n  Taxa baixa demais para analisar. Aumente a taxa de leitura.")
        return

    espectro = dft_banda(t, x, f_ini, f_fim, 220)
    amps = [a for _, a in espectro]
    mediana = statistics.median(amps)
    pico_f, pico_a = max(espectro, key=lambda p: p[1])

    print("\n" + "=" * 68)
    print(f"ESPECTRO DO ENVELOPE  ({f_ini:.1f} a {f_fim:.1f} Hz)")
    print("=" * 68)

    # Gráfico ASCII: comunica forma melhor que uma lista de números.
    largura = 46
    passo = max(1, len(espectro) // 34)
    for i in range(0, len(espectro), passo):
        f, a = espectro[i]
        barras = int(largura * a / pico_a) if pico_a > 0 else 0
        marca = ""
        if f_esperada and abs(f - f_esperada) < (f_fim - f_ini) / 34:
            marca = "  <== 2·s·fs"
        print(f"  {f:5.2f} Hz |{'#' * barras}{' ' * (largura - barras)}| "
              f"{a*1000:7.2f} mA{marca}")

    razao = pico_a / mediana if mediana > 0 else 0
    print("\n  pico em          : %.2f Hz, %.1f mA" % (pico_f, pico_a * 1000))
    print("  piso (mediana)   : %.1f mA" % (mediana * 1000))
    print("  razão pico/piso  : %.1f x" % razao)

    print("\n" + "=" * 68)
    print("VEREDITO")
    print("=" * 68)
    if fs < 6.0:
        print("  INCONCLUSIVO — taxa de leitura insuficiente.")
        print("  Reduza PF525_INTERVALO_S, leia SÓ a corrente, e repita.")
        print("  Se ainda assim não passar de ~6 Hz, o caminho pelo inversor")
        print("  está fechado: só com TC no cabo + ADC do ESP32.")
    elif razao < 4:
        # Ordem importa: primeiro o que se OBSERVOU, depois as duas leituras
        # possíveis. Dizer só "inconclusivo" a cada motor sadio -- que é a
        # maioria -- ensina quem opera a ignorar a ferramenta.
        print("  NENHUMA MODULAÇÃO DETECTADA (pico só %.1fx o piso)." % razao)
        print()
        print("  Isso tem DUAS leituras, e daqui não dá para separá-las:")
        print("   • o motor está sadio — é o resultado esperado; ou")
        print("   • o filtro interno do drive apagou a modulação antes de")
        print("     ela chegar até nós.")
        if degraus < 3:
            print()
            print("  E atenção: a variação da corrente (%.1f degraus de "
                  "0,01 A)" % degraus)
            print("  mal supera a quantização. Sob carga baixa a modulação")
            print("  encolhe junto — repita com o motor carregado.")
        print()
        print("  Só uma captura num motor com defeito CONHECIDO separa as")
        print("  duas hipóteses. Até lá, o método não está validado.")
    else:
        print("  RAIA DETECTADA — pico %.1fx acima do piso, em %.2f Hz."
              % (razao, pico_f))
        if f_esperada and abs(pico_f - f_esperada) < 0.5:
            print("  E ela COINCIDE com o 2·s·fs esperado (%.2f Hz)."
                  % f_esperada)
            print("  É o resultado que torna o método viável. Confirme")
            print("  repetindo com carga estável e comparando com a linha")
            print("  de base do mesmo motor.")
        else:
            print("  Mas NÃO coincide com o 2·s·fs esperado.")
            print("  Provável origem mecânica ou de processo (variação de")
            print("  carga), não barra de rotor.")


# =====================================================================
#  Captura
# =====================================================================


def capturar(ip, segundos, instancia, escala, arquivo):
    try:
        from pycomm3 import CIPDriver, Services, DataType
    except ImportError:
        print("Falta o pycomm3. Instale com: pip install pycomm3")
        sys.exit(1)

    t = []
    x = []
    print(f"conectando em {ip} ...")
    with CIPDriver(ip) as drive:
        print(f"lendo o parâmetro {instancia} o mais rápido possível "
              f"por {segundos:.0f}s")
        print("(sem pausa entre leituras: queremos a taxa MÁXIMA do link)\n")
        t0 = time.monotonic()
        prox_aviso = 5.0
        while True:
            agora = time.monotonic() - t0
            if agora >= segundos:
                break
            resp = drive.generic_message(
                service=Services.get_attribute_single,
                class_code=0x0F, instance=instancia, attribute=1,
                data_type=DataType.int, connected=False,
                unconnected_send=True)
            if resp:
                t.append(time.monotonic() - t0)
                x.append(resp.value * escala)
            if agora >= prox_aviso:
                taxa = len(t) / agora if agora else 0
                print(f"  {agora:5.1f}s  {len(t):5d} amostras  "
                      f"({taxa:.1f} Hz)")
                prox_aviso += 5.0

    if not t:
        print("nenhuma leitura obtida.")
        sys.exit(1)

    with open(arquivo, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "corrente_a"])
        for ti, xi in zip(t, x):
            w.writerow([f"{ti:.6f}", f"{xi:.3f}"])
    print(f"\ngravado: {arquivo}  ({len(t)} amostras)")
    return t, x


def ler_csv(caminho):
    t, x = [], []
    with open(caminho, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            t.append(float(linha["t_s"]))
            x.append(float(linha["corrente_a"]))
    return t, x


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capturar", type=float, metavar="SEG",
                    help="captura por SEG segundos direto do drive")
    ap.add_argument("--analisar", metavar="CSV",
                    help="analisa um CSV já capturado")
    ap.add_argument("--ip", default=os.getenv("PF525_IP", "192.168.1.20"))
    ap.add_argument("--arquivo", default="mcsa_captura.csv")
    ap.add_argument("--instancia", type=int, default=3,
                    help="parâmetro a ler (3 = b003 corrente de saída)")
    ap.add_argument("--escala", type=float, default=0.01)
    ap.add_argument("--rpm-placa", type=float, default=1760,
                    help="rpm nominal da plaqueta")
    ap.add_argument("--polos", type=int, default=4)
    ap.add_argument("--f-saida", type=float, default=60.0,
                    help="frequência de saída do drive durante a captura")
    a = ap.parse_args()

    if not a.capturar and not a.analisar:
        ap.error("use --capturar SEG ou --analisar CSV")

    if a.analisar:
        t, x = ler_csv(a.analisar)
    else:
        t, x = capturar(a.ip, a.capturar, a.instancia, a.escala, a.arquivo)

    if len(t) < 20:
        print("amostras de menos para analisar.")
        sys.exit(1)
    analisar(t, x, a.rpm_placa, a.polos, a.f_saida)


if __name__ == "__main__":
    main()
