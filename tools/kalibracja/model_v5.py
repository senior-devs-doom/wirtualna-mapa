# -*- coding: utf-8 -*-
"""
Model kosztu v5 (kandydat docelowy).

  s_i = 1 − Π_j (1 − M_ij·u_j)                 wrażliwość na klasę i, w [0,1]: „szansa”, że któreś ograniczenie
                                                czyni klasę i przeszkodą; u_j ∈ [0,1] jak u promotora
  φ(z) = (e^{γz} − 1) / (e^γ − 1)              φ(0) = 0, φ(1) = 1, wypukła; γ ustala rozpiętość (≈ e^γ) między
                                                łagodnym a granicznym zagrożeniem tej samej klasy
  C = L + d + λ·L·Σ_i φ(s_i·h_i) + Λ·Σ_i φ(s_i·b_i)

Parametry globalne: Λ (koszt przeszkody granicznej w metrach obejścia), λ (koszt metra granicznego odcinka
liniowego), γ (rozpiętość). Dane: M (ograniczenie × klasa), u (profil), krawędzie (L, d, h, b).
Własności (dowody w notatce):
  A1  C nie maleje przy wzroście żadnego u_j (s_i rosnące w u_j, φ rosnąca, wagi nieujemne);
  A2  separowalność: C = Σ_i F_i(s_i), więc dołożenie ograniczenia j zmienia tylko składniki klas z M_ij > 0;
      różnica kosztów dwóch krawędzi nie zmienia się, jeśli różnią się one wyłącznie w klasach, na które j
      nie działa (oryginał to łamał: g i I wiązały wszystkie klasy krawędzi);
  A3  osoba bez ograniczeń: s = 0, C = L + d (najszybsza trasa);
  A4  przeszkody punktowe niezależne od L; A5 addytywność po krawędziach;
  A6  koszt ograniczony: C ≤ L + d + λL·Σh-klas + Λ·Σb-klas (przeszkoda z pomocą ma skończoną cenę).
"""
import sys
import itertools
import numpy as np
from model_v3 import M_PROMOTOR, M_V3, CLS, UC, vec, uvec, USERS
from model_v4 import EDGES, S, W, expectations


class Model:
    def __init__(self, M=M_V3, Lam=250.0, lam=None, gamma=4.0):
        self.M, self.Lam, self.gamma = M, Lam, gamma
        self.lam = Lam / 25 if lam is None else lam

    def s(self, u): return 1 - np.prod(1 - self.M * u, axis=1)

    def phi(self, z):
        g = self.gamma
        return z if g == 0 else np.expm1(g * z) / np.expm1(g)

    def cost(self, e, u):
        s = self.s(u)
        return e['L'] + e.get('d', 0) + self.lam * e['L'] * self.phi(s * e['h']).sum() + self.Lam * self.phi(s * e['b']).sum()


def axioms(m, edges=EDGES, grid=(0, .5, 1)):
    """A1 na siatce {0,.5,1}^7; A2: dołożenie u_j nie zmienia różnicy kosztów krawędzi różniących się tylko
    w klasach, na które j nie działa (sprawdzane na parach sztucznych krawędzi)."""
    v1 = n1 = 0
    E = list(edges.values())
    for u in itertools.product(grid, repeat=7):
        u = np.array(u, float)
        for j in range(7):
            if u[j] == grid[-1]: continue
            uj = u.copy(); uj[j] = grid[grid.index(u[j]) + 1]
            for e in E:
                n1 += 1
                if m.cost(e, uj) < m.cost(e, u) - 1e-9: v1 += 1
    v2 = n2 = 0
    rng = np.random.default_rng(0)
    for _ in range(3000):
        j = rng.integers(7)
        free = [i for i in range(9) if m.M[i, j] == 0]          # klasy, na które j nie działa
        if not free: continue
        base_h, base_b = rng.random(9) * .5, rng.random(9) * .5
        x = dict(L=10, h=base_h.copy(), b=base_b.copy()); y = dict(L=10, h=base_h.copy(), b=base_b.copy())
        for i in free: y['b'][i] = rng.random()                  # różnica tylko w klasach wolnych od j
        u = rng.random(7) * (rng.random(7) < .5); u[j] = 0; uj = u.copy(); uj[j] = 1
        n2 += 1
        if abs((m.cost(x, uj) - m.cost(y, uj)) - (m.cost(x, u) - m.cost(y, u))) > 1e-6: v2 += 1
    return v1, n1, v2, n2


def report(m, label, verbose=True):
    ex = expectations(m); ok = sum(lo <= v <= hi for _, v, (lo, hi) in ex)
    print('\n=========== %s ===========' % label)
    if verbose:
        print('A1 naruszenia %d/%d, A2 naruszenia %d/%d' % axioms(m))
        print('%-16s' % '', ''.join('%9s' % e[:8] for e in EDGES))
        for un, u in USERS.items():
            print('%-16s' % un, ''.join('%9.0f' % m.cost(EDGES[e], u) for e in EDGES))
        for name, v, (lo, hi) in ex:
            print('  [%s] %-66s %8.2f  oczekiwane %s' % ('OK' if lo <= v <= hi else '--', name, v, (lo, hi) if hi < 1e8 else '≥ %g' % lo))
    print('  spełnione %d/%d' % (ok, len(ex)))
    return ok, [n for n, v, (lo, hi) in ex if not lo <= v <= hi]


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    # przegląd parametrów globalnych (dane krawędzi, M i u są ustalone z góry i NIE są tu strojone)
    print('γ \\ Λ ', ''.join('%7.0f' % L for L in (150, 200, 250, 300, 400)))
    for g in (0, 2, 3, 4, 5, 6, 7):
        row = []
        for L in (150, 200, 250, 300, 400):
            ex = expectations(Model(gamma=g, Lam=L)); row.append(sum(lo <= v <= hi for _, v, (lo, hi) in ex))
        print('γ=%-4g' % g, ''.join('%7d' % r for r in row))
    report(Model(gamma=4, Lam=250), 'v5 γ = 4, Λ = 250 m')
