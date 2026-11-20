# -*- coding: utf-8 -*-
"""KROK 2: model promotora z JEDNĄ minimalną modyfikacją: koszt krawędzi liczony jako suma składowych.

Funkcja ryzyka promotora zostaje bez zmian (R_base, g, I = 1 + κ/(1 + e^{-η(g-τ)}), u z R_min, macierz M i wagi α są wolnymi parametrami
kalibracji, jak w kroku 1). Zmienia się tylko to, przez co mnoży się ryzyko:

  C(krawędź) = L_xy · f(e_dystans) + q · [ ℓ_schody · f(e_schody)   (krawędź ze schodami, q kondygnacji)
                                         + ℓ_winda · f(e_jazda)     (jazda windą, q kondygnacji)
                                         + ℓ_czek · f(e_oczekiwanie) (wejście do kabiny, q = 1) ],   f(e) = R_base(e)·I(e)

czyli to samo „ryzyko razy rozmiar”, ale rozmiar składowej to dystans poziomy (m) albo ilość q (kondygnacje, zdarzenia) razy równoważnik długości ℓ
(m na jednostkę). Dodatkowe parametry: tylko 3 równoważniki ℓ. Brak b0, brak Λ, brak czasu d, brak funkcji φ.
Wariant A: bez wykluczeń. Wariant B: dla profili z U1 schody wyłączone z grafu (sugestia promotora).
Wzorzec dopasowania: model zastosowany (v6b), 10 profili. Wyjście: promotor_components_<A|B>.json.
Użycie: python promotor_components.py <katalog_wyjscia> [maxiter] [A|B] [workers]
"""
import sys, os, json, math
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from model_v3 import M_V3, M_PROMOTOR

ROOT = os.path.join(HERE, '..', '..')
g = json.load(open(os.path.join(ROOT, 'tools', 'graph_export.json'), encoding='utf-8'))
names = [n['name'] for n in g['nodes']]; ix = {n: i for i, n in enumerate(names)}; N = len(names)
E = g['edges']; NE = len(E)
fr = np.array([ix[e['from']] for e in E]); to = np.array([ix[e['to']] for e in E])
Lxy = np.array([e['L'] for e in E]); q = np.array([e.get('q', 0) for e in E]); d = np.array([e.get('d', 0) for e in E])
pre = np.array([e['preset'] for e in E])
CL = 'ABCDEFGHI'
H = np.array([[e.get('h' + c, 0) for c in CL] for e in E]); B = np.array([[e.get('b' + c, 0) for c in CL] for e in E])
vert = (pre == 'stairs') | (pre == 'elevator')
L3 = np.hypot(Lxy, np.where(vert, 3.5 * q, 0.0))          # długość drogi (jak RiskModel.edgeLength)
is_st = (pre == 'stairs') & (q > 0)                       # schody z pokonywaną kondygnacją
# typ odcinka dla modelu promotora: 0 korytarz, 1 schody, 2 jazda windą, 3 dojście do windy
TYP = np.zeros(NE, int); TYP[is_st] = 1; TYP[pre == 'elevator'] = 2; TYP[pre == 'elevator_access'] = 3
PROFILES = [('bez', 0), ('U1', 1), ('U3', 4), ('U5', 16), ('U1+U3', 5), ('U1+U3+U5', 21), ('wszystkie', 127)]
ALL10 = [('bez', 0)] + [('U%d' % (j + 1), 1 << j) for j in range(7)] + [('U1+U3', 5), ('wszystkie', 127)]
TAG = ''
PROFILES = ALL10; TAG = ''   # kalibracja pod wszystkie 10 profili

# ------------------------------------------------------------------ wzorzec: model zastosowany (v6b)
GAMMA, LB = 3.0, 300.0; LH = LB / 25
phi = lambda z: np.expm1(GAMMA * z) / np.expm1(GAMMA)
def ours_cost(mask):
    u = np.array([1.0 if mask >> j & 1 else 0.0 for j in range(7)])
    s = 1 - np.prod(1 - M_V3 * u[None, :], axis=1)
    return Lxy * (1 + LH * phi(s[None, :] * H).sum(1)) + q * (d + LB * phi(s[None, :] * B).sum(1))

# ------------------------------------------------------------------ trasy
def floyd(c, use):
    D = np.full((N, N), np.inf); nx = -np.ones((N, N), int); np.fill_diagonal(D, 0)
    for k in np.where(use)[0]:
        a, b = fr[k], to[k]
        if c[k] < D[a, b]: D[a, b] = c[k]; nx[a, b] = b
    ar = np.arange(N)
    for k in range(N):
        alt = D[:, [k]] + D[[k], :]
        better = alt < D - 1e-12
        D = np.where(better, alt, D)
        nx = np.where(better, nx[:, [k]] * np.ones((1, N), int), nx)
    return D, nx
EDGE = {(fr[k], to[k]): k for k in range(NE)}
def route(nx, s, t):
    r = []; c = s
    while c != t:
        n = nx[c, t]; r.append(EDGE[(c, n)]); c = n
    return r
ALLM = np.ones(NE, bool)
REF = {}            # profil -> (D, nx) modelu zastosowanego
for _, m in ALL10 + PROFILES: REF[m] = floyd(ours_cost(m), ALLM)
ar = np.arange(N); SS, TT = np.meshgrid(ar, ar, indexing='ij'); OFF = SS != TT
EDGEIDX = -np.ones((N, N), int)
for k in range(NE): EDGEIDX[fr[k], to[k]] = k

def regret(nx, mask, cost_ref):
    """średni względny koszt ponad optimum (w kosztach modelu zastosowanego) wzdłuż tras wybranych przez badany model"""
    D0, _ = REF[mask]
    cur = SS.copy(); acc = np.zeros((N, N))
    for _ in range(N):
        act = (cur != TT) & OFF
        if not act.any(): break
        nxt = nx[cur, TT]
        e = EDGEIDX[cur, np.where(nxt < 0, 0, nxt)]
        acc = acc + np.where(act, cost_ref[np.where(e < 0, 0, e)], 0.0)
        cur = np.where(act, nxt, cur)
    return float(np.mean((acc[OFF] - D0[OFF]) / D0[OFF]))

# ------------------------------------------------------------------ model promotora
RMIN = 0.02
def split(x):
    kappa, eta, tau, eps, uon, uoff, rmin = x[:7]
    vec = np.asarray(x[7:43]).reshape(4, 9)
    alpha = np.asarray(x[43:52]); M = np.asarray(x[52:115]).reshape(9, 7)
    uon = np.asarray(x[115:122])          # osobna wartość „zaznaczone” dla każdego ograniczenia U1..U7
    return kappa, eta, tau, eps, uon, uoff, rmin, vec, alpha, M
def per_metre(mask, x):
    kappa, eta, tau, eps, uon, uoff, rmin, vec, alpha, M = split(x)
    xs = np.array([uon[j] if mask >> j & 1 else uoff for j in range(7)])
    u = rmin + (1 - rmin) * np.clip(xs, 0, 1)
    w = alpha * (M @ u)
    R = (vec * w[None, :]).sum(1)
    gg = R / ((vec * alpha[None, :]).sum(1) + eps)
    I = 1 + kappa / (1 + np.exp(-eta * (gg - tau)))
    return R * I                                               # koszt na metr dla 4 typów
IS_STAIRS = is_st.astype(float); IS_RIDE = (pre == 'elevator').astype(float); IS_WAIT = ((pre == 'elevator_access') & (q > 0)).astype(float)
def prom_cost(mask, x):
    f = per_metre(mask, x)                      # f(e) dla 4 składowych: dystans, schody, jazda windą, oczekiwanie
    l_st, l_ride, l_wait = x[122:125]
    return Lxy * f[0] + q * (l_st * f[1] * IS_STAIRS + l_ride * f[2] * IS_RIDE + l_wait * f[3] * IS_WAIT)

def dilution_rate(x):
    """udział naruszeń wymagania b): iloraz kosztu na metr (schody/korytarz, schody/winda) nie maleje po dołożeniu ograniczenia (128 profili × 7 dołożeń)"""
    pm = np.array([per_metre(m, x) for m in range(128)])
    cor, st, lift = pm[:, 0], pm[:, 1], pm[:, 2]
    bad = tot = 0
    for m in range(128):
        for j in range(7):
            if m >> j & 1: continue
            m2 = m | 1 << j
            for num, den in ((st, cor), (st, lift), (lift, cor)):
                tot += 1
                if num[m2] / den[m2] < num[m] / den[m] - 1e-9: bad += 1
    return bad / tot

def objective(x, variant='A'):
    tot = 0.0
    for _, m in PROFILES:
        use = ALLM
        if variant == 'B' and m & 1: use = ~is_st
        c = prom_cost(m, x)
        D, nx = floyd(c, use)
        # ocena wg kosztów wzorca, ale w grafie z tymi samymi ograniczeniami dostępu
        cref = ours_cost(m)
        if variant == 'B' and m & 1:
            cref = np.where(is_st, 1e9, cref)
            D0, nx0 = floyd(cref, ALLM); REF_B = D0
            tot += float(np.mean(nx[OFF] != nx0[OFF]))
            continue
        tot += float(np.mean(nx[OFF] != REF[m][1][OFF])) + 0.5 * regret(nx, m, cref)
    return tot / len(PROFILES) + 0.5 * dilution_rate(x)

def objective_A(x): return objective(x, 'A')
def objective_B(x): return objective(x, 'B')

# ------------------------------------------------------------------ raport dla danego zestawu parametrów
def report(x, variant='A'):
    out = {}
    for name, m in ALL10:
        use = ALLM if not (variant == 'B' and m & 1) else ~is_st
        c = prom_cost(m, x); D, nx = floyd(c, use)
        Df, nxf = floyd(c, ~is_st)
        Dl, nxl = floyd(L3, ALLM)
        Dref, nxref = REF[m]
        used = viol = 0; tol = 0.0; tolerated = 0; lens = []; st_routes = 0; unreach = 0
        for s in range(N):
            for t in range(s + 1, N):
                if nx[s, t] < 0: unreach += 1; continue      # para nieosiągalna po wykluczeniu schodów (wariant B)
                r = route(nx, s, t); Lr = L3[r].sum(); lens.append(Lr)
                hs = is_st[r].any(); st_routes += hs
                if hs:
                    used += 1
                    if np.isfinite(Df[s, t]): viol += 1
                else:
                    rl = route(nxl, s, t)
                    if is_st[rl].any(): tolerated += 1; tol = max(tol, Lr / Dl[s, t])
        same_first = float(np.mean(nx[OFF] == nxref[OFF]))
        out[name] = dict(zeSchodami=int(used), schodyMimoObejscia=int(viol), maxTolerowaneObejscie=round(float(tol), 2),
                         sredniaDlugosc=round(float(np.mean(lens)), 1), parNieosiagalnych=int(unreach), zgodnoscPierwszegoKrokuZModelemZastosowanym=round(same_first, 3))
    return out

BASELINE = None
def baseline_x():
    """parametry z przykładu promotora (rozdz. 5.2 pracy): κ=1, η=8, τ=0,25, ε=0,01; u = 0,85/0,10; schody e=(.9,.3,.1,.2,.1,.1,.1,.1,.2), korytarz 0,05"""
    st = [.9, .3, .1, .2, .1, .1, .1, .1, .2]; cor = [.05] * 9
    return np.array([1.0, 8.0, 0.25, 0.01, 0.85, 0.10, 0.02] + cor + st + cor + cor + [1 / 9.0] * 9 + list(np.asarray(M_PROMOTOR).ravel()) + [0.85] * 7 + [8.0, 3.5, 5.0])

def bounds():
    b = [(0.05, 60.0), (0.5, 60.0), (0.0, 1.0), (0.001, 0.5), (0.3, 1.0), (0.0, 0.4), (0.0, 0.1)]
    b += [(0.0, 1.0)] * 36 + [(0.01, 1.0)] * 9 + [(0.0, 1.0)] * 63 + [(0.3, 1.0)] * 7 + [(1.0, 40.0), (0.1, 20.0), (1.0, 80.0)]
    return b

if __name__ == '__main__':
    import time
    from scipy.optimize import differential_evolution
    OUT = sys.argv[1] if len(sys.argv) > 1 else '.'
    maxiter = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    variant = sys.argv[3] if len(sys.argv) > 3 else 'A'
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 7
    x0 = baseline_x(); f = objective_A if variant == 'A' else objective_B
    res = {'baseline': dict(parametry=x0.tolist(), J=f(x0), dilution=dilution_rate(x0), raport=report(x0, variant))}
    print('baseline J %.4f dilution %.3f' % (res['baseline']['J'], res['baseline']['dilution']), flush=True)
    best = [1e9]
    def cb(xk, convergence=None):
        v = f(xk)
        if v < best[0] - 1e-5: best[0] = v; print('  J %.4f' % v, flush=True)
    t0 = time.time()
    r = differential_evolution(f, bounds(), maxiter=maxiter, popsize=8, tol=1e-8, seed=11, workers=workers, updating='deferred',
                               polish=False, x0=x0, mutation=(0.4, 1.0), recombination=0.85, callback=cb)
    res['peak'] = dict(wariant=variant, parametry=r.x.tolist(), J=float(r.fun), dilution=dilution_rate(r.x), raport=report(r.x, variant),
                       iteracje=int(r.nit), sekundy=round(time.time() - t0))
    print('peak', variant, 'J %.4f dilution %.3f (%d iter, %.0f s)' % (r.fun, res['peak']['dilution'], r.nit, time.time() - t0), flush=True)
    json.dump(res, open(os.path.join(OUT, 'promotor_components_%s.json' % variant), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=float)
