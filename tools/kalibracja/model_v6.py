# -*- coding: utf-8 -*-
"""
Model kosztu v6: warstwa modelu (koszt pojedynczej składowej) oddzielona od warstwy krawędzi (suma składowych).

  s_i  = 1 − Π_j (1 − M_ij·u_j)                       wrażliwość na klasę i (jak v5)
  φ(z) = (e^{γz} − 1) / (e^γ − 1)                     kara (jak v5)
  C(e) = L_xy·(1 + λ·Σ_i φ(s_i·h_i))  +  Σ_k [ q_k·d_k + c_k·Λ·Σ_i φ(s_i·b_ik) ]

  L_xy  dystans poziomy krawędzi [m]; h  zagrożenia liniowe (na metr)
  k     składowe punktowe krawędzi (kondygnacja schodów, jazda windą, oczekiwanie na windę, drzwi, próg)
  q_k   ilość składowej dla czasu (np. liczba kondygnacji |Δz|/3,5, może być ułamkowa)
  c_k   liczba barier składowej (całkowita: ile razy bariera jest pokonywana na tej krawędzi)
  d_k   czas jednostki [m ekwiwalentu], wspólny dla wszystkich; b_k  natężenie bariery składowej

Różnice względem v5: (1) L_xy zamiast długości 3D (wysokość niesie składowa); (2) czas skaluje się ilością q,
a bariera liczbą c, liczoną bez ułamków; (3) krawędź może mieć kilka składowych.
"""
import sys
import itertools
import numpy as np
from model_v3 import M_V3, CLS, UC, vec, uvec, USERS
import model_v4
from model_v4 import EDGES, S, W, expectations, tol, route
import model_v5


class Model:
    def __init__(self, M=M_V3, Lam=300.0, lam=None, gamma=3.0):
        self.M, self.Lam, self.gamma = M, Lam, gamma
        self.lam = Lam / 25 if lam is None else lam

    def s(self, u): return 1 - np.prod(1 - self.M * u, axis=1)

    def phi(self, z):
        return z if self.gamma == 0 else np.expm1(self.gamma * z) / np.expm1(self.gamma)

    def cost6(self, L, h, comps, u):
        s = self.s(u)
        c = L * (1 + self.lam * self.phi(s * h).sum())
        for q, cnt, d, b in comps:
            c += q * d + cnt * self.Lam * self.phi(s * b).sum()
        return c

    # adapter dla krawędzi testowych v4/v5: jedna składowa (q = c = 1) z d i b, dystans jak w teście
    def cost(self, e, u):
        comps = [(1, 1, e.get('d', 0), e['b'])] if (e.get('d', 0) or e['b'].any()) else []
        return self.cost6(e['L'], e['h'], comps, u)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    m6, m5 = Model(), model_v5.Model(gamma=3.0, Lam=300.0)

    print('1) 21 oczekiwań (te same krawędzie i użytkownicy co dla v5)')
    ok5, f5 = model_v5.report(m5, 'v5 γ=3, Λ=300', verbose=False)
    ok6, f6 = model_v5.report(m6, 'v6 γ=3, Λ=300', verbose=False)
    print('   niespełnione v5:', f5, '| v6:', f6)
    print('   największa różnica kosztu krawędzi testowej v5−v6: %.2e m' % max(
        abs(m5.cost(e, u) - m6.cost(e, u)) for e in EDGES.values() for u in USERS.values()))

    print('\n2) Aksjomaty (siatka {0, .5, 1}^7 i 3000 par krawędzi)')
    print('   v6: A1 naruszenia %d/%d, A2 naruszenia %d/%d' % model_v5.axioms(m6))

    print('\n3) Przegląd γ × Λ (płaskie maksimum?)')
    print('   γ \\ Λ ', ''.join('%6.0f' % L for L in (150, 200, 250, 300, 400)))
    for g in (0, 2, 3, 4, 5):
        print('   γ=%-3g' % g, ''.join('%6d' % sum(lo <= v <= hi for _, v, (lo, hi) in expectations(Model(gamma=g, Lam=L))) for L in (150, 200, 250, 300, 400)))

    print('\n4) Odporność: M, h, b zaburzone o ±25 % (300 losowań)')
    rng = np.random.default_rng(1)
    orig = {k: dict(v) for k, v in EDGES.items()}
    okc = []
    for _ in range(300):
        for k, v in orig.items():
            EDGES[k] = dict(v, h=np.clip(v['h'] * rng.uniform(.75, 1.25, 9), 0, 1), b=np.clip(v['b'] * rng.uniform(.75, 1.25, 9), 0, 1))
        m = Model(M=np.clip(M_V3 * rng.uniform(.75, 1.25, (9, 7)), 0, 1))
        okc.append(sum(lo <= v <= hi for _, v, (lo, hi) in expectations(m)))
    for k, v in orig.items(): EDGES[k] = v
    print('   spełnione średnio %.1f/21, min %d' % (np.mean(okc), min(okc)))

    print('\n5) Niezależność od podziału klatki (2 kondygnacje schodów, b_A = 1, b_E = 0,1, d = 10 na kondygnację)')
    bS = vec(A=1.0, E=.1)
    for un in ('sprawna', 'kule', 'wózek', 'niewidoma'):
        u = USERS[un]
        one = m6.cost6(10, vec(), [(2, 2, 10, bS)], u)                                   # jedna krawędź 0 → 7 m
        two = 2 * m6.cost6(5, vec(), [(1, 1, 10, bS)], u)                                # punkt na piętrze pośrednim
        landing = sum(m6.cost6(2.5, vec(), [(.5, c, 10, bS)], u) for c in (1, 0, 1, 0))  # podesty co pół kondygnacji
        once = m6.cost6(10, vec(), [(2, 1, 10, bS)], u)                                  # wariant: bariera raz na krawędź
        print('   %-10s jedna krawędź %7.1f | dwie %7.1f | z podestami %7.1f | (bariera raz: %7.1f)' % (un, one, two, landing, once))

    print('\n6) Oczekiwanie na windę (d = 25, bez bariery) jest takie samo dla każdego profilu:')
    wait = [m6.cost6(0, vec(), [(1, 1, 25, vec())], u) for u in USERS.values()]
    print('   ', sorted(set(np.round(wait, 9))))
