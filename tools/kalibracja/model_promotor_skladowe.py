# -*- coding: utf-8 -*-
"""
Model promotora + składowe, BEZ kalibracji (kontrola poprawności, nie strojenie).

  f(v, u):  R = Σ α_i v_i (M u')_i,  g = R / (Σ α_i v_i + ε),  I = 1 + κ σ(η (g − τ)),  f = R·I      (jak u promotora)
            u' = R_min + (1 − R_min)·u;  κ = 1, η = 8, τ = 0,25, ε = 0,01, α = 1/9, R_min = 0,02
  F(v, u) = f(v, u) / f_ref        jednostka: f_ref = f dla pojedynczej klasy A (v = e_A) przy pełnym U1 (u = e_1),
                                   czyli F = 1 to „przeszkoda graniczna"; nie jest to parametr do strojenia
  C = L_xy·(1 + Λ_h·F(h)) + Σ_k [ q_k·d_k + c_k·Λ_b·F(b_k) ]        (składowe jak w v6/v6b; Λ_b = 300, Λ_h = Λ_b/25)
"""
import sys
import itertools
import numpy as np
from model_v3 import M_PROMOTOR, M_V3, USERS
import model_v4
from model_v4 import EDGES, S, W, expectations, tol, route
import model_v5

sig = lambda x: 1 / (1 + np.exp(-x))


class Model:
    def __init__(self, M=M_V3, Lam=300.0, lam=None, kappa=1.0, eta=8.0, tau=0.25, eps=0.01, alpha=1 / 9., rmin=0.02, sep=False, orsens=False):
        self.sep = sep; self.orsens = orsens
        self.M, self.Lam, self.kappa, self.eta, self.tau, self.eps, self.alpha, self.rmin = M, Lam, kappa, eta, tau, eps, alpha, rmin
        self.lam = Lam / 25 if lam is None else lam
        eA = np.zeros(9); eA[0] = 1; u1 = np.zeros(7); u1[0] = 1  # f_ref: pojedyncza klasa A przy pełnym U1
        self.fref = self._f(eA, u1)

    def _f(self, v, u):
        up = self.rmin + (1 - self.rmin) * u
        a = (1 - np.prod(1 - self.M * up, axis=1)) if self.orsens else self.M @ up
        if self.sep == 'split':   # składowa rozbita na klasy: wzór promotora bez zmian, osobno dla każdej klasy
            z = self.alpha * v * a
            g = np.divide(z, self.alpha * v + self.eps)
            return float((z * (1 + self.kappa * sig(self.eta * (g - self.tau)))).sum())
        if self.sep == 'z':   # wzmocnienie na iloczynie z = a·v (jak φ(s·h) w v6b)
            z = a * v
            return float((self.alpha * z * (1 + self.kappa * sig(self.eta * (z - self.tau)))).sum())
        if self.sep:   # wzmocnienie liczone osobno w każdej klasie (klasy niezależne)
            return float((self.alpha * v * a * (1 + self.kappa * sig(self.eta * (a - self.tau)))).sum())
        R = float((self.alpha * v * a).sum())
        g = R / (float((self.alpha * v).sum()) + self.eps)
        return R * (1 + self.kappa * sig(self.eta * (g - self.tau)))

    def F(self, v, u): return self._f(v, u) / self.fref

    def cost6(self, L, h, comps, u):
        c = L * (1 + self.lam * self.F(h, u))
        for q, cnt, d, b in comps:
            c += q * d + cnt * self.Lam * self.F(b, u)
        return c

    def cost(self, e, u):
        comps = [(1, 1, e.get('d', 0), e['b'])] if (e.get('d', 0) or e['b'].any()) else []
        return self.cost6(e['L'], e['h'], comps, u)


def checks(m):
    out = {}
    # A1: koszt nie maleje przy wzroście u_j (siatka {0, .5, 1}^7)
    v = n = 0
    for u in itertools.product((0, .5, 1), repeat=7):
        u = np.array(u, float)
        for j in range(7):
            if u[j] == 1: continue
            uj = u.copy(); uj[j] = {0: .5, .5: 1}[u[j]]
            for e in EDGES.values():
                n += 1
                if m.cost(e, uj) < m.cost(e, u) - 1e-9: v += 1
    out['A1 naruszenia'] = (v, n)
    # A2: dołożenie u_j nie zmienia różnicy kosztów krawędzi różniących się tylko w klasach wolnych od j
    rng = np.random.default_rng(0); v = n = 0; mx = 0.0
    for _ in range(3000):
        j = rng.integers(7); free = [i for i in range(9) if m.M[i, j] == 0]
        if not free: continue
        bh, bb = rng.random(9) * .5, rng.random(9) * .5
        x = dict(L=10, h=bh.copy(), b=bb.copy()); y = dict(L=10, h=bh.copy(), b=bb.copy())
        for i in free: y['b'][i] = rng.random()
        u = rng.random(7) * (rng.random(7) < .5); u[j] = 0; uj = u.copy(); uj[j] = 1
        n += 1; dd = abs((m.cost(x, uj) - m.cost(y, uj)) - (m.cost(x, u) - m.cost(y, u))); mx = max(mx, dd)
        if dd > 1e-6: v += 1
    out['A2 naruszenia'] = (v, n); out['A2 największa zmiana różnicy [m]'] = round(mx, 1)
    # niezależność od podziału kondygnacji: 2 kondygnacje jako jedna składowa q = 2 vs dwie składowe q = 1 (bariera liczona raz na krawędź)
    b = EDGES[S]['b']; err = 0.0
    for u in USERS.values():
        one = m.cost6(8, np.zeros(9), [(2, 1, 10, b)], u)
        two = m.cost6(8, np.zeros(9), [(1, 1, 10, b), (1, 0, 10, b)], u)
        err = max(err, abs(one - two))
    out['podział kondygnacji, maks. różnica [m]'] = round(err, 9)
    # osoba bez ograniczeń: koszt zależy tylko od L i d, a nie od zagrożeń (A3 modelu v5)
    sp = USERS['sprawna']
    out['sprawna: koszt schodów ponad L+d [m]'] = round(m.cost(EDGES[S], sp) - EDGES[S]['L'] - EDGES[S]['d'], 2)
    # ograniczoność kosztu (A6)
    return out


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for name, M in (('M_V3 (nasza)', M_V3), ('M_PROMOTOR', M_PROMOTOR)):
        m = Model(M=np.asarray(M))
        print('\n######## promotor + składowe, bez strojenia, %s, f_ref=%.4f' % (name, m.fref))
        ok, bad = model_v5.report(m, name, verbose=False)
        print('  niespełnione:', bad)
        ex = expectations(m)
        for nm, v, (lo, hi) in ex:
            if not lo <= v <= hi: print('    --', nm, round(v, 2), (lo, hi) if hi < 1e8 else '≥ %g' % lo)
        for k, v in checks(m).items(): print('  ', k, v)
    m6 = __import__('model_v6').Model()
    print('\n######## odniesienie: nasz v6b')
    ok, bad = model_v5.report(m6, 'v6', verbose=False); print('  niespełnione:', bad)
    print('  ', checks.__name__, {k: v for k, v in checks(m6).items()})
