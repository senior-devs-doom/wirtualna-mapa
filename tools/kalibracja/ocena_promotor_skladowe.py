# -*- coding: utf-8 -*-
"""Ocena (BEZ kalibracji): model promotora + składowe na grafie budynku, wszystkie 128 profili, wzorzec v6b.
C = L_xy(1 + Λ_h F(h)) + q (d + Λ_b F(b)),  F = f/f_ref,  f = R·I (funkcja promotora), M = M_V3, α = 1/9, R_min = 0.
Użycie: python ocena_promotor_skladowe.py   (parametry zestawów w SETS poniżej: stałe promotora lub wyprowadzone z reguł, nie z optymalizacji)"""
import sys, itertools
import numpy as np
import promotor_components as P
from model_v3 import M_V3
sys.stdout.reconfigure(encoding='utf-8')
M = np.asarray(M_V3); sig = lambda x: 1 / (1 + np.exp(-x))

def Ffun(V, u, kappa, eta, tau, eps, rmin, fref=None, sep=False, orsens=False):
    up = rmin + (1 - rmin) * u
    a = (1 - np.prod(1 - M * up[None, :], axis=1)) if orsens else M @ up
    if sep == 'split': z = V / 9.0 * a[None, :]; g = z / (V / 9.0 + eps); return (z * (1 + kappa * sig(eta * (g - tau)))).sum(1)
    if sep == 'z': z = V * a[None, :]; return (z / 9.0 * (1 + kappa * sig(eta * (z - tau)))).sum(1)
    if sep: return (V / 9.0 * a[None, :] * (1 + kappa * sig(eta * (a[None, :] - tau)))).sum(1)
    R = (V * a[None, :]).sum(1) / 9.0
    g = R / ((V / 9.0).sum(1) + eps)
    return R * (1 + kappa * sig(eta * (g - tau)))

def make_cost(kappa, eta, tau, eps, rmin, LB, LH, sep=False, orsens=False):
    eA = np.zeros((1, 9)); eA[0, 0] = 1; u1 = np.zeros(7); u1[0] = 1
    fref = Ffun(eA, u1, kappa, eta, tau, eps, rmin, sep=sep, orsens=orsens)[0]
    def cost(mask):
        u = np.array([1.0 if mask >> j & 1 else 0.0 for j in range(7)])
        return P.Lxy * (1 + LH * Ffun(P.H, u, kappa, eta, tau, eps, rmin, sep=sep, orsens=orsens) / fref) + P.q * (P.d + LB * Ffun(P.B, u, kappa, eta, tau, eps, rmin, sep=sep, orsens=orsens) / fref)
    return cost

def stats(nx, mask):
    zs = 0
    N = P.N
    for s in range(N):
        for t in range(s + 1, N):
            if nx[s, t] >= 0 and P.is_st[P.route(nx, s, t)].any(): zs += 1
    return zs

SETS = {
    'stałe promotora, Λ_h = 12': dict(kappa=1, eta=8, tau=.25, eps=.01, rmin=0, LB=300, LH=12),
    'Λ_h = 3 (z przedziału oczekiwań), ε = 0,1': dict(kappa=1, eta=8, tau=.25, eps=.1, rmin=0, LB=300, LH=3),
}
if __name__ == '__main__':
    refs = {m: P.REF[m] if m in P.REF else P.floyd(P.ours_cost(m), P.ALLM) for m in range(128)}
    for name, kw in SETS.items():
        cost = make_cost(**kw)
        agree = []
        for m in range(128):
            D, nx = P.floyd(cost(m), P.ALLM); agree.append(float(np.mean(nx[P.OFF] == refs[m][1][P.OFF])))
        agree = np.array(agree); inn = np.array([m in dict(P.ALL10[i][::-1] for i in range(len(P.ALL10))) for m in range(128)])
        print('\n=== %s ===' % name)
        print('zgodność pierwszego kroku z v6b: średnia 128 profili %.3f, min %.3f (maska %d), mediana %.3f' % (agree.mean(), agree.min(), int(agree.argmin()), np.median(agree)))
        print('profile < 0,90: %d z 128' % int((agree < .9).sum()))
        print('%-10s %5s %5s | %s' % ('profil', 'v6b', 'model', 'zgodność'))
        for nm, m in P.ALL10:
            D, nx = P.floyd(cost(m), P.ALLM)
            print('%-10s %5d %5d | %.3f' % (nm, stats(refs[m][1], m), stats(nx, m), agree[m]))
