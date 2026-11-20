# -*- coding: utf-8 -*-
"""Runda testów: NIEZMIENIONY wzór promotora (a = Σ M u, R = Σ α e a, g = R/(Σ α e + ε), I = 1 + κ σ(η(g − τ)))
+ dobudówka: krawędź = składowe bezwzględne (L, d; takie same dla każdego) + składowe ryzyka (rozmiar · Λ · R·I / f_ref).
Reprezentacje: 'wektor' (składowa = wektor h lub b z danych) i 'split' (składowa rozbita na klasy).
Parametry z zasady (bez optymalizacji tras): u = 0/1, R_min = 0, M = M_V3, α = 1/9, η = 8 (promotor);
κ, τ, ε z dopasowania krzywej f(a, e) do φ(a·e) (γ = 3); Λ_b = 300; Λ_h ze środka przedziału z oczekiwań liniowych.
Użycie: python runda_testow.py"""
import sys, copy, numpy as np
import model_v6, model_v5, model_promotor_skladowe as MP
import promotor_components as P, ocena_promotor_skladowe as O
from model_v3 import M_V3, USERS
from model_v4 import EDGES, S, W, expectations, tol
sys.stdout.reconfigure(encoding='utf-8')
M = np.asarray(M_V3); sig = lambda x: 1 / (1 + np.exp(-x)); ETA = 8.0; AL = 1 / 9.

# 1) kształt: f(a, e) dla jednej klasy vs φ(a·e)
A, Ev = np.meshgrid(np.linspace(0, 1, 41), np.linspace(0.05, 1, 20))
phi = np.expm1(3 * A * Ev) / np.expm1(3)
best = None
for eps in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5):
    for tau in np.linspace(0, 1, 41):
        for kap in np.linspace(0, 8, 81):
            z = AL * Ev * A; g = z / (AL * Ev + eps)
            f = z * (1 + kap * sig(ETA * (g - tau))); f1 = AL * (1 + kap * sig(ETA * (AL / (AL + eps) - tau)))
            r = float(np.sqrt(np.mean((f / f1 - phi) ** 2)))
            if best is None or r < best[0]: best = (r, eps, float(tau), float(kap))
RMSE, EPS, TAU, KAP = best
lin = float(np.sqrt(np.mean((A * Ev - phi) ** 2)))
print('KSZTAŁT: κ = %.2f, τ = %.3f, ε = %.3f, η = 8  (RMSE do φ %.3f; liniowo %.3f)' % (KAP, TAU, EPS, RMSE, lin))

def model(rep, Lh, Lb=300.0, Mx=M):
    return MP.Model(M=Mx, Lam=Lb, lam=Lh, kappa=KAP, eta=ETA, tau=TAU, eps=EPS, rmin=0, sep=('split' if rep == 'split' else False))

def lam_h(rep):
    m = model(rep, 1.0); lo, hi = 0, 1e9
    for u, e, a, b in (('wózek', 'korytarz wąski', 1.1, 1.8), ('wózek', 'chodnik śliski', 1.2, 2.0), ('słabowidząca', 'korytarz ciemny', 1.3, 3.0), ('wózek', 'pochylnia 6%', 1.0, 2.0)):
        F = m.F(EDGES[e]['h'], USERS[u]); lo = max(lo, (a - 1) / F); hi = min(hi, (b - 1) / F)
    return lo, hi

masks = range(128); us = {k: np.array([1.0 if k >> j & 1 else 0.0 for j in range(7)]) for k in masks}
LIFT_CLS = (EDGES[W]['b'] > 0) | (EDGES[W]['h'] > 0)
CORR = ['korytarz', 'korytarz wąski', 'korytarz ciemny', 'hol zatłoczony', 'chodnik śliski']

def corridor_vs_lift(m):
    """dołożenie ograniczenia j, które NIE dotyczy klas windy: czy korytarz tanieje względem windy?"""
    bad = tot = 0
    for k in masks:
        for j in range(7):
            if k >> j & 1 or (M[LIFT_CLS, j] > 0).any(): continue
            k2 = k | 1 << j
            for e in CORR:
                tot += 1
                r0 = m.cost(EDGES[e], us[k]) / m.cost(EDGES[W], us[k]); r1 = m.cost(EDGES[e], us[k2]) / m.cost(EDGES[W], us[k2])
                bad += r1 < r0 - 1e-9
    return bad, tot

def stacking(m):
    """bariera kondygnacji schodów: profile bez U1 droższe od samego wózka (U1) oraz maks. dla profili z U1"""
    bw = m.cost(EDGES[S], us[1]) - EDGES[S]['L'] - EDGES[S]['d']
    worse = [(k, m.cost(EDGES[S], us[k]) - EDGES[S]['L'] - EDGES[S]['d']) for k in masks if not k & 1]
    worse = [(k, c) for k, c in worse if c > bw]
    mx = max(m.cost(EDGES[S], us[k]) - EDGES[S]['L'] - EDGES[S]['d'] for k in masks if k & 1)
    return bw, worse, mx

def robust(make, n=200, seed=1):
    rng = np.random.default_rng(seed); e0 = copy.deepcopy(EDGES); res = []
    for _ in range(n):
        Mp = np.clip(M * rng.uniform(.75, 1.25, M.shape), 0, 1)
        for key, e in EDGES.items():
            e['h'] = e0[key]['h'] * rng.uniform(.75, 1.25, 9); e['b'] = e0[key]['b'] * rng.uniform(.75, 1.25, 9)
        ex = expectations(make(Mp)); res.append(sum(lo <= v <= hi for _, v, (lo, hi) in ex))
    for key in EDGES: EDGES[key]['h'], EDGES[key]['b'] = e0[key]['h'], e0[key]['b']
    return float(np.mean(res)), int(min(res))

# największe obejście windą w budynku (m) dla par, w których istnieje trasa bez schodów: granica stabilności
Dlen, _ = P.floyd(P.L3, P.ALLM); Dns, _ = P.floyd(P.L3, ~P.is_st)
fin = np.isfinite(Dns) & P.OFF
max_detour = float(np.max(Dns[fin] - Dlen[fin]))
print('BUDYNEK: najdłuższe obejście bez schodów (różnica długości) = %.1f m' % max_detour)

refs = {k: P.floyd(P.ours_cost(k), P.ALLM) for k in masks}
for rep in ('wektor', 'split'):
    lo, hi = lam_h(rep); LH = (lo + hi) / 2 if lo <= hi else lo
    m = model(rep, LH)
    print('\n================ reprezentacja: %s   Λ_h z przedziału [%.2f, %.2f] → %.2f, Λ_b = 300 ================' % (rep, lo, hi, LH))
    ex = expectations(m); bad = [n[:34] for n, v, (a, b) in ex if not a <= v <= b]
    print(' 21 oczekiwań: %d/21  %s' % (21 - len(bad), bad))
    c = MP.checks(m); print(' A1 %s  A2 %s (maks. zmiana %s m)  podział kondygnacji %s' % (c['A1 naruszenia'], c['A2 naruszenia'], c['A2 największa zmiana różnicy [m]'], c['podział kondygnacji, maks. różnica [m]']))
    print(' osoba bez ograniczeń: schody ponad L+d = %.2f m;  min(C − L) = %.3f' % (c['sprawna: koszt schodów ponad L+d [m]'], min(m.cost(e, us[k]) - e['L'] for e in EDGES.values() for k in masks)))
    print(' tolerancja obejścia wózka %.0f m; kondygnacja dla U1 %.0f m' % (tol(m, USERS['wózek']), m.cost(EDGES[S], us[1]) - EDGES[S]['L'] - EDGES[S]['d']))
    b, t = corridor_vs_lift(m); print(' T1 korytarz tanieje względem windy po ograniczeniu niedotyczącym windy: %d/%d' % (b, t))
    bw, worse, mx = stacking(m)
    print(' T2 nakładanie: U1 sam %.0f m; profili bez U1 droższych od wózka: %d %s; maks. z U1: %.0f m' % (bw, len(worse), [(k, round(cc)) for k, cc in sorted(worse, key=lambda x: -x[1])[:4]], mx))
    mean, mn = robust(lambda Mx: model(rep, LH, Mx=Mx)); print(' odporność ±25%%: %.1f / najmniej %d   (v6b: 17,1 / 13)' % (mean, mn))
    cost = O.make_cost(KAP, ETA, TAU, EPS, 0, 300, LH, sep=('split' if rep == 'split' else False))
    ag = []; st = {}
    for k in masks:
        D, nx = P.floyd(cost(k), P.ALLM); ag.append(float(np.mean(nx[P.OFF] == refs[k][1][P.OFF])))
        if k in (0, 1, 2, 4, 8, 16, 32, 64, 127): st[k] = O.stats(nx, k)
    print(' graf: zgodność z v6b śr %.3f min %.3f' % (np.mean(ag), np.min(ag)))
    print(' pary ze schodami bez %d U1 %d U2 %d U3 %d U4 %d U5 %d U6 %d U7 %d wsz %d  (v6b 1697 278 1215 741 1323 1705 1492 368 278)' % tuple(st[k] for k in (0, 1, 2, 4, 8, 16, 32, 64, 127)))
    c1 = cost(1); D, nx = P.floyd(c1, P.ALLM); viol = sum(1 for s in range(P.N) for t in range(s + 1, P.N) if nx[s, t] >= 0 and P.is_st[P.route(nx, s, t)].any() and np.isfinite(Dns[s, t]))
    print(' H1: U1 ze schodami mimo obejścia %d' % viol)
    nx0 = P.floyd(cost(0), P.ALLM)[1]
    print(' H2: inna trasa niż bez ograniczeń: U3 %.1f%%, U5 %.1f%%, U1 %.1f%%' % tuple(100 * np.mean(P.floyd(cost(k), P.ALLM)[1][P.OFF] != nx0[P.OFF]) for k in (4, 16, 1)))
