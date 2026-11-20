# -*- coding: utf-8 -*-
"""
Model kosztu v4.

  z_i = s_i·h_i (odcinek liniowy) albo s_i·b_i (przeszkoda punktowa),  s_i = Σ_j M_ij u_j
  φ(z) = z·(1 + κ·σ(η(z − τ)))            wzmocnienie promotora, liczone osobno w każdej klasie
                                          z bezwzględnego dopasowania z zamiast z udziału g = R/Σαe
  C = L + d + λ·L·Σ_i φ(s_i h_i) + Λ·Σ_i φ(s_i b_i)

  L  długość [m];  d  czas przejścia ponad marsz, wspólny dla wszystkich [m ekwiwalentu]: czekanie na windę,
     wejście po schodach, zwolnienie w tłoku. Osoba bez ograniczeń (s = 0) ma C = L + d, czyli wybiera trasę
     najszybszą; to zastępuje stałą marszu b0 i wrażliwość bazową s0.
  h, b  natężenie zagrożenia jako ułamek przeszkody granicznej (1 = do pokonania tylko z pomocą przy pełnym
     ograniczeniu); M_ij = 1: ograniczenie j przy pełnym nasileniu czyni klasę i graniczną.
  Λ  koszt przeszkody granicznej w metrach obejścia; λ  koszt metra granicznego odcinka liniowego (λ = Λ/25:
     25 m takiego odcinka ≈ jedna przeszkoda graniczna).
  κ, η, τ  z opracowania promotora (1, 8, 0,25); κ jest jedynym parametrem kształtu do kalibracji.
"""
import sys
import numpy as np
from model_v3 import M_PROMOTOR, M_V3, CLS, UC, vec, uvec, USERS

sig = lambda x: 1 / (1 + np.exp(-x))


class Model:
    def __init__(self, M=M_V3, Lam=250.0, lam=None, kappa=1.0, eta=8.0, tau=.25):
        self.M, self.Lam, self.kappa, self.eta, self.tau = M, Lam, kappa, eta, tau
        self.lam = Lam / 25 if lam is None else lam

    def phi(self, z): return z * (1 + self.kappa * sig(self.eta * (z - self.tau)))

    def cost(self, e, u):
        s = self.M @ u
        return e['L'] + e.get('d', 0) + self.lam * e['L'] * self.phi(s * e['h']).sum() + self.Lam * self.phi(s * e['b']).sum()


EDGES = {
    'korytarz':            dict(L=20, h=vec(), b=vec()),
    'korytarz wąski':      dict(L=20, h=vec(C=.3), b=vec()),
    'korytarz ciemny':     dict(L=20, h=vec(E=.6, F=.2), b=vec()),
    'pochylnia 6%':        dict(L=10, h=vec(B=.3), b=vec()),
    'pochylnia 12%':       dict(L=5,  h=vec(B=.9), b=vec()),
    'schody (1 kond.)':    dict(L=8,  d=10, h=vec(), b=vec(A=1.0, E=.1)),
    'stopień 5 cm':        dict(L=1,  h=vec(), b=vec(A=.2, E=.1)),
    'drzwi ciężkie':       dict(L=2,  d=2, h=vec(), b=vec(G=.7, C=.2)),
    'winda (1 kond.)':     dict(L=3,  d=25, h=vec(), b=vec(C=.1, G=.15, F=.1, H=.05)),
    'hol zatłoczony':      dict(L=30, d=10, h=vec(H=.5, F=.1), b=vec()),
    'chodnik śliski':      dict(L=30, h=vec(D=.4), b=vec()),
    'hol bez oznakowania': dict(L=15, d=5, h=vec(), b=vec(F=.6, E=.1)),
    'schody ruchome':      dict(L=10, h=vec(), b=vec(A=1.0, G=.1, H=.3)),
}
S, W = 'schody (1 kond.)', 'winda (1 kond.)'


def route(m, u, parts):
    tot = 0.0
    for name, L in parts:
        e = dict(EDGES[name])
        if L is not None: e['L'] = L
        tot += m.cost(e, u)
    return tot


def tol(m, u, obstacle=S, alt=W, base=20.0):
    a = route(m, u, [('korytarz', base - EDGES[obstacle]['L']), (obstacle, None)])
    b = route(m, u, [('korytarz', base - EDGES[alt]['L']), (alt, None)])
    return a - b


def expectations(m):
    U = USERS
    c = lambda u, e: m.cost(EDGES[e], U[u]) / EDGES[e]['L']
    pt = lambda u, e: m.cost(EDGES[e], U[u]) - m.cost(EDGES[e], U['sprawna'])   # nadwyżka ponad osobę sprawną
    return [
        ('sprawna: schody, winda opłaca się dopiero gdy krótsza (tol < 0)', tol(m, U['sprawna']), (-60, 0)),
        ('wózek: winda do kilkuset m obejścia, potem schody z pomocą', tol(m, U['wózek']), (150, 400)),
        ('wózek dziecięcy: winda, mniej stanowczo niż wózek', tol(m, U['wózek dziecięcy']), (40, 200)),
        ('kule: winda przy umiarkowanym obejściu', tol(m, U['kule']), (50, 250)),
        ('senior: winda przy umiarkowanym obejściu', tol(m, U['senior']), (20, 120)),
        ('niewidoma: schody i winda porównywalne', tol(m, U['niewidoma']), (-50, 50)),
        ('poznawcza: schody i winda porównywalne', tol(m, U['poznawcza']), (-50, 50)),
        ('wózek: pochylnia 6% akceptowalna (≤ 2× długości)', c('wózek', 'pochylnia 6%'), (1.0, 2.0)),
        ('wózek: pochylnia 12% wyraźnie gorsza od 6% (krotność za metr)', c('wózek', 'pochylnia 12%') / c('wózek', 'pochylnia 6%'), (2, 10)),
        ('wózek: stopień 5 cm do pokonania (10–60 m)', pt('wózek', 'stopień 5 cm'), (10, 60)),
        ('wózek: ciężkie drzwi uciążliwe (20–150 m)', pt('wózek', 'drzwi ciężkie'), (20, 150)),
        ('drzwi: wózek ≥ wózek dziecięcy', pt('wózek', 'drzwi ciężkie') - pt('wózek dziecięcy', 'drzwi ciężkie'), (0, 1e9)),
        ('wózek: schody ruchome ≈ schody (≥ 0,9×)', pt('wózek', 'schody ruchome') / pt('wózek', S), (0.9, 1.5)),
        ('sprawna: schody ruchome tańsze od schodów', m.cost(EDGES[S], U['sprawna']) - m.cost(EDGES['schody ruchome'], U['sprawna']), (0, 1e9)),
        ('niewidoma: hol bez oznakowania kosztowny (50–250 m)', pt('niewidoma', 'hol bez oznakowania'), (50, 250)),
        ('poznawcza: hol bez oznakowania kosztowny (50–250 m)', pt('poznawcza', 'hol bez oznakowania'), (50, 250)),
        ('słabowidząca: ciemny korytarz 1,3–3×', c('słabowidząca', 'korytarz ciemny'), (1.3, 3)),
        ('wózek: wąski korytarz 1,1–1,8×', c('wózek', 'korytarz wąski'), (1.1, 1.8)),
        ('wózek: śliski chodnik 1,2–2×', c('wózek', 'chodnik śliski'), (1.2, 2.0)),
        ('poznawcza: tłok 1,3–2,5× (ponad samą długość i czas)', (m.cost(EDGES['hol zatłoczony'], U['poznawcza']) - 10) / 30, (1.3, 2.5)),
        ('wózek+niewidoma: schody ≥ wózek (bez rozrzedzenia)', pt('wózek+niewidoma', S) - pt('wózek', S), (0, 1e9)),
    ]


def axioms(m, edges=EDGES, grid=(0, .5, 1)):
    """A1: koszt nie maleje przy wzroście dowolnego u_j. A2': przyrost kosztu od u_k nie maleje, gdy dołożono
    inne ograniczenie (brak rozrzedzenia). Profile z siatki {0, .5, 1}^7."""
    import itertools
    v1 = v2 = n = 0
    edges = list(edges.values())
    for u in itertools.product(grid, repeat=7):
        u = np.array(u, float)
        for j in range(7):
            if u[j] == grid[-1]: continue
            uj = u.copy(); uj[j] = grid[grid.index(u[j]) + 1]
            for e in edges:
                c0, c1 = m.cost(e, u), m.cost(e, uj)
                n += 1
                if c1 < c0 - 1e-9: v1 += 1
                k = (j + 3) % 7                      # inne ograniczenie k: czy jego wkład zmalał po dołożeniu j?
                if u[k] > 0:
                    uk0 = u.copy(); uk0[k] = 0; ujk0 = uj.copy(); ujk0[k] = 0
                    if (c1 - m.cost(e, ujk0)) < (c0 - m.cost(e, uk0)) - 1e-6: v2 += 1
    return v1, v2, n


def report(m, label, verbose=True):
    ex = expectations(m); ok = sum(lo <= v <= hi for _, v, (lo, hi) in ex)
    print('\n=========== %s ===========' % label)
    print('A1 / A2 naruszenia / sprawdzeń:', axioms(m))
    if verbose:
        print('%-16s' % '', ''.join('%9s' % e[:8] for e in EDGES))
        for un, u in USERS.items():
            print('%-16s' % un, ''.join('%9.0f' % m.cost(EDGES[e], u) for e in EDGES))
    for name, v, (lo, hi) in ex:
        print('  [%s] %-66s %8.2f  oczekiwane %s' % ('OK' if lo <= v <= hi else '--', name, v, (lo, hi) if hi < 1e8 else '≥ %g' % lo))
    print('  spełnione %d/%d' % (ok, len(ex)))
    return ok


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    report(Model(kappa=0), 'v4 liniowe (κ = 0)')
    report(Model(kappa=1), 'v4 κ = 1 (promotor)')
    report(Model(kappa=3), 'v4 κ = 3')
