# -*- coding: utf-8 -*-
"""Liczby z podrozdziału 5.3 pracy (kontrola oczekiwań, wrażliwość na Λ_b i Λ_h) oraz z uwagi dla promotora
(łączenie ograniczeń U3 i U7, wpływ zmniejszenia M i κ). Model: runda_testow.py, reprezentacja 'split'.
Nic nie zapisuje; użycie: python sprawdzenia_do_pracy.py"""
import io, os, sys, contextlib
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
_out = sys.stdout
sys.stdout = open(os.devnull, 'w', encoding='utf-8')   # runda_testow drukuje własne wyniki przy imporcie
sys.stdout.reconfigure = lambda **k: None
import runda_testow as R
sys.stdout = _out
import promotor_components as P
import ocena_promotor_skladowe as O
import model_promotor_skladowe as MP
from model_v4 import expectations, EDGES, S

lo, hi = R.lam_h('split'); LH = (lo + hi) / 2
print('Λ_h: przedział [%.2f, %.2f], środek %.2f; κ=%g τ=%g ε=%g' % (lo, hi, LH, R.KAP, R.TAU, R.EPS))


def n_ok(m):
    ex = expectations(m)
    return sum(a <= v <= b for _, v, (a, b) in ex), [n[:32] for n, v, (a, b) in ex if not a <= v <= b]


print('\nΛ_b od 200 do 400 m (Λ_h stałe):')
for Lb in (200, 250, 300, 350, 400):
    print('  Λ_b = %d: %d/21 %s' % ((Lb,) + n_ok(R.model('split', LH, Lb=Lb))))
print('Λ_h × 0,5 … 2,0 (Λ_b = 300):')
for f in (0.5, 0.75, 1.0, 1.5, 2.0):
    print('  Λ_h × %.2f: %d/21 %s' % ((f,) + n_ok(R.model('split', LH * f))))

# koszt kondygnacji schodów ponad L + d dla wybranych profili
m = R.model('split', LH)
u = lambda mask: np.array([1.0 if mask >> j & 1 else 0.0 for j in range(7)])
print('\nkondygnacja schodów ponad L + d [m]:', {n: round(m.cost(EDGES[S], u(k)) - EDGES[S]['L'] - EDGES[S]['d'], 1) for n, k in (('U1', 1), ('U3', 4), ('U7', 64), ('U3+U7', 68), ('wszystkie', 127))})

# pary (nieuporządkowane) ze schodami dla U3, U7 osobno, bez schodów dla U3+U7
Dns, _ = P.floyd(P.L3, ~P.is_st)


def stairs_matrix(nx):
    a = np.zeros((P.N, P.N), bool)
    for s in range(P.N):
        for t in range(s + 1, P.N):
            if nx[s, t] >= 0:
                a[s, t] = P.is_st[P.route(nx, s, t)].any()
    return a


def uwaga(label, Mx, kap=R.KAP):
    mm = MP.Model(M=Mx, Lam=300, lam=LH, kappa=kap, eta=R.ETA, tau=R.TAU, eps=R.EPS, rmin=0, sep='split')
    ok, _ = n_ok(mm)
    O.M = Mx
    cost = O.make_cost(kap, R.ETA, R.TAU, R.EPS, 0, 300, LH, sep='split')
    st = {k: stairs_matrix(P.floyd(cost(k), P.ALLM)[1]) for k in (4, 64, 68)}
    print('  %-10s oczekiwań %d/21; U3 i U7 osobno ze schodami, U3+U7 bez schodów: %d par' % (label, ok, int((st[4] & st[64] & ~st[68]).sum())))


print('\nUwaga dla promotora (łączenie U3 i U7):')
M0 = np.asarray(R.M)
uwaga('bazowa', M0)
for f in (0.9, 0.8, 0.7):
    uwaga('M × %.1f' % f, M0 * f)
uwaga('κ = 4', M0, 4.0)
uwaga('κ = 2', M0, 2.0)
O.M = M0
print('najdłuższe obejście bez schodów (różnica długości): %.1f m' % float(np.max((Dns - P.floyd(P.L3, P.ALLM)[0])[np.isfinite(Dns) & P.OFF])))
