"""1) Confere se a mistura (7/8,1/8) continua boa em outras taxas de
   amostragem.  2) Roda a bateria completa de testes de medirVibracao()."""
import math
import cmath

C0, C1 = 7.0 / 8.0, 1.0 / 8.0
G = 9.80665
FC = 10.0
N = 384
AQUEC = 96


def ganho(c0, c1, f, fs):
    dt = 1.0 / fs
    w = 2.0 * math.pi * f * dt
    z1 = cmath.exp(-1j * w)
    h = dt * (c0 + c1 * z1) / (1.0 - z1)
    return abs(h) / (1.0 / (2.0 * math.pi * f))


print("=== Sensibilidade da mistura (7/8,1/8) a taxa de amostragem ===")
print("erro (%) da velocidade por frequencia\n")
freqs = [10, 20, 29.3, 58.6, 100]
print("fs (Hz)".ljust(10) + "".join(f"{f:>9.1f}" for f in freqs) + "   trapezio@100")
for fs_t in (250.0, 300.0, 370.0, 450.0, 600.0):
    errs = [(ganho(C0, C1, f, fs_t) - 1) * 100 for f in freqs]
    trap = (ganho(0.5, 0.5, 100, fs_t) - 1) * 100
    print(f"{fs_t:<10.0f}" + "".join(f"{e:>9.1f}" for e in errs) + f"{trap:>15.1f}")

# ---------------------------------------------------------------------


class Biquad:
    def __init__(self, fc, fs):
        w0 = 2.0 * math.pi * fc / fs
        alpha = math.sin(w0) / (2.0 * math.sqrt(0.5))
        cw = math.cos(w0)
        a0 = 1.0 + alpha
        self.b0 = ((1.0 + cw) / 2.0) / a0
        self.b1 = (-(1.0 + cw)) / a0
        self.b2 = self.b0
        self.a1 = (-2.0 * cw) / a0
        self.a2 = (1.0 - alpha) / a0
        self.x1 = self.x2 = self.y1 = self.y2 = 0.0
        self.ini = False

    def __call__(self, x):
        if not self.ini:
            self.ini = True
            self.x1 = self.x2 = x
        y = (self.b0 * x + self.b1 * self.x1 + self.b2 * self.x2
             - self.a1 * self.y1 - self.a2 * self.y2)
        self.x2, self.x1 = self.x1, x
        self.y2, self.y1 = self.y1, y
        return y


class Canal:
    def __init__(self, fs):
        self.hp_acel = Biquad(FC, fs)
        self.hp_vel = Biquad(FC, fs)
        self.acel_ant = 0.0
        self.vel = 0.0
        self.tem_ant = False

    def __call__(self, acel_ms2, dt):
        a = self.hp_acel(acel_ms2)
        if not self.tem_ant:
            self.acel_ant = a
            self.tem_ant = True
        self.vel += dt * (C0 * a + C1 * self.acel_ant)
        self.acel_ant = a
        return self.hp_vel(self.vel) * 1000.0


def medir(sinal_g, fs, fs_coef=None, n=N):
    dt = 1.0 / fs
    cv = [Canal(fs_coef or fs) for _ in range(3)]
    s, ss, sv, svv = [0.0] * 3, [0.0] * 3, [0.0] * 3, [0.0] * 3
    mn, mx = [1e30] * 3, [-1e30] * 3
    nval = 0
    for i in range(n):
        t = i * dt
        e = sinal_g(i, t)
        vel = [cv[k](e[k] * G, dt) for k in range(3)]
        if i >= AQUEC:
            for k in range(3):
                s[k] += e[k]; ss[k] += e[k] ** 2
                mn[k] = min(mn[k], e[k]); mx[k] = max(mx[k], e[k])
                sv[k] += vel[k]; svv[k] += vel[k] ** 2
            nval += 1
    m = [s[k] / nval for k in range(3)]
    var = [max(0.0, ss[k] / nval - m[k] ** 2) for k in range(3)]
    pico = [max(mx[k] - m[k], m[k] - mn[k]) for k in range(3)]
    mv = [sv[k] / nval for k in range(3)]
    vv = [max(0.0, svv[k] / nval - mv[k] ** 2) for k in range(3)]
    cr = [pico[k] / math.sqrt(var[k]) if var[k] > 1e-8 else 0.0 for k in range(3)]
    return {"rms_g": math.sqrt(sum(var)), "crista": max(cr),
            "vel_mm_s": math.sqrt(sum(vv))}


def chk(nome, obtido, esperado, tol):
    err = abs(obtido - esperado) / esperado * 100 if esperado else 0
    ok = err <= tol
    print(f"  [{'OK ' if ok else 'FALHA'}] {nome:36s} {obtido:8.4f} vs {esperado:8.4f}"
          f"  erro {err:5.1f}%  (tol {tol}%)")
    return ok


fs = 370.0
A = 0.10
res = []
vel_de = lambda amp, f: amp * G * 1000.0 / (2 * math.pi * f * math.sqrt(2))

print("\n\n=== Bateria completa (fs = 370 Hz) ===")
r30 = medir(lambda i, t: (A * math.sin(2 * math.pi * 30 * t), 0, 0), fs)
res.append(chk("RMS aceleracao 30 Hz (g)", r30["rms_g"], A / math.sqrt(2), 2))
res.append(chk("crista de senoide (=1,414)", r30["crista"], math.sqrt(2), 5))
res.append(chk("velocidade 30 Hz (mm/s)", r30["vel_mm_s"], vel_de(A, 30), 4))

r60 = medir(lambda i, t: (A * math.sin(2 * math.pi * 60 * t), 0, 0), fs)
res.append(chk("velocidade 60 Hz (mm/s)", r60["vel_mm_s"], vel_de(A, 60), 4))
res.append(chk("razao v30/v60 (=2,0)", r30["vel_mm_s"] / r60["vel_mm_s"], 2.0, 4))

r100 = medir(lambda i, t: (A * math.sin(2 * math.pi * 100 * t), 0, 0), fs)
res.append(chk("velocidade 100 Hz (mm/s)", r100["vel_mm_s"], vel_de(A, 100), 6))

c = math.sqrt(0.5)
rg = medir(lambda i, t: (A * c * math.sin(2 * math.pi * 30 * t),
                         A * c * math.sin(2 * math.pi * 30 * t), 0), fs)
res.append(chk("invariancia a orientacao (mm/s)", rg["vel_mm_s"], r30["vel_mm_s"], 2))

rdc = medir(lambda i, t: (A * math.sin(2 * math.pi * 30 * t) + 0.5, 0, 0), fs)
res.append(chk("imune a offset DC de 0,5 g", rdc["vel_mm_s"], r30["vel_mm_s"], 1))

f1 = 29.3
r2x = medir(lambda i, t: (A * math.sin(2 * math.pi * f1 * t)
                          + 0.5 * A * math.sin(2 * math.pi * 2 * f1 * t), 0, 0), fs)
res.append(chk("1x + 2x (desalinhamento)", r2x["vel_mm_s"],
               math.sqrt(vel_de(A, f1) ** 2 + vel_de(0.5 * A, 2 * f1) ** 2), 4))

r3 = medir(lambda i, t: (A * math.sin(2 * math.pi * 3 * t), 0, 0), fs)
at = r3["vel_mm_s"] / vel_de(A, 3)
ok = at < 0.10
print(f"  [{'OK ' if ok else 'FALHA'}] {'3 Hz rejeitado pelo passa-alta':36s} "
      f"{at*100:5.1f}% do valor sem filtro (alvo <10%)")
res.append(ok)

ri = medir(lambda i, t: (0.01 * math.sin(2 * math.pi * 137 * t)
                         + (0.5 if i % 40 == 0 else 0), 0, 0), fs)
ok = ri["crista"] > 4
print(f"  [{'OK ' if ok else 'FALHA'}] {'crista sobe com impacto':36s} "
      f"{ri['crista']:5.2f}  (senoide = 1,41)")
res.append(ok)

rerr = medir(lambda i, t: (A * math.sin(2 * math.pi * 30 * t), 0, 0), 340.0,
             fs_coef=370.0)
res.append(chk("coef. de fs 8% errada", rerr["vel_mm_s"], vel_de(A, 30), 5))

print("\n" + "=" * 72)
print(f"RESULTADO: {sum(1 for x in res if x)}/{len(res)} verificacoes passaram")
