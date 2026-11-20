# -*- coding: utf-8 -*-
"""
Model kosztu v3: postać z model_v2.py (aksjomaty A1–A6 tam opisane), dane przemyślane od zera.

  s_i = s0_i + Σ_j M_ij u_j
  C   = L·(1 + λ·Σ_i s_i h_i) + Λ·Σ_i s_i b_i

Znaczenie liczb (to jest sedno kalibrowalności):
  - h_i = 1   najgorszy realny odcinek klasy i na całej długości (np. zupełna ciemność, ścisk w tłumie);
  - b_i = 1   najgorsza realna przeszkoda punktowa klasy i (A: kondygnacja schodów, G: drzwi bez samozamykacza
              z siłą otwarcia ~60 N, H: kilka minut czekania, F: rozgałęzienie bez żadnej informacji);
  - M_ij = 1  ograniczenie j przy pełnym nasileniu czyni klasę i przeszkodą graniczną (do pokonania tylko z pomocą);
  - Λ         ile metrów obejścia jest warta przeszkoda graniczna (s·b = 1); λ: ile razy droższy jest metr
              granicznego odcinka liniowego (s·h = 1 daje koszt (1+λ) za metr);
  - s0        wrażliwość przeciętnej osoby sprawnej (wysiłek schodów, czas czekania, gubienie się).
Klasy (z aplikacji / opracowania promotora): A różnice poziomów, B nachylenia, C przestrzeń, D nawierzchnia,
E percepcja (oświetlenie, kontrast), F informacja i oznakowanie, G manipulacja (drzwi, przyciski),
H dynamika (tłok, ruch, czekanie), I ewakuacja.
Ograniczenia: U1 lokomocyjne, U2 manipulacyjne, U3 wzrokowe, U4 sensoryczne pozawzrokowe (słuch, dotyk),
U5 poznawcze, U6 stres i presja czasu, U7 zmęczeniowe.
"""
import sys
import numpy as np

CLS = 'ABCDEFGHI'
UC = ['U1', 'U2', 'U3', 'U4', 'U5', 'U6', 'U7']

M_PROMOTOR = np.array([
    [1, .2, 0, .2, 0, .2, .4], [1, .2, 0, 0, 0, .2, .4], [.6, .8, .2, 0, .2, .2, .3], [.8, .2, .2, .6, 0, .2, .4],
    [0, 0, 1, .4, .2, .2, 0], [0, 0, .9, .2, .8, .3, 0], [.2, 1, 0, 0, 0, .2, .2], [.2, .2, .2, 0, .4, .8, .4],
    [.4, .2, .2, 0, .4, 1, .4]])

# Macierz v3: wiersz = klasa zagrożenia, kolumna = ograniczenie. Uzasadnienie zmian względem promotora w komentarzach.
M_V3 = np.array([
    #  U1   U2   U3   U4   U5   U6   U7
    [1.0, 0.2, 0.3, 0.1, 0.0, 0.1, 0.6],  # A poziomy: osoba niewidoma pokonuje schody, ale ryzyko pierwszego stopnia (0→0,3); wysiłek przy zmęczeniu (0,4→0,6)
    [0.9, 0.2, 0.0, 0.0, 0.0, 0.1, 0.5],  # B nachylenia: pochylnia jest dostępną alternatywą, pełna stromizna niemal graniczna (1→0,9)
    [0.8, 0.2, 0.3, 0.0, 0.1, 0.3, 0.1],  # C przestrzeń: szerokość dla wózka (0,6→0,8); siła rąk nie zależy od szerokości (0,8→0,2); ciasnota a stres (0,2→0,3)
    [0.8, 0.1, 0.4, 0.3, 0.0, 0.1, 0.3],  # D nawierzchnia: osoba niewidoma traci prowadzenie fakturą (0,2→0,4); U4 dotyk/równowaga (0,6→0,3)
    [0.0, 0.0, 1.0, 0.2, 0.3, 0.2, 0.1],  # E percepcja: bez zmian co do istoty
    [0.0, 0.0, 0.8, 0.4, 1.0, 0.4, 0.0],  # F informacja: ograniczenie poznawcze jest tu główne (0,8→1,0); U4 komunikaty dźwiękowe (0,2→0,4)
    [0.6, 1.0, 0.3, 0.1, 0.1, 0.1, 0.3],  # G manipulacja: ciężkie drzwi z wózka (0,2→0,6); szukanie przycisków po omacku (0→0,3)
    [0.4, 0.2, 0.4, 0.2, 0.5, 1.0, 0.3],  # H dynamika: tłok dla wózka i osoby niewidomej (0,2→0,4); stres jest tu główny (0,8→1,0)
    [0.6, 0.2, 0.5, 0.3, 0.5, 1.0, 0.4],  # I ewakuacja: osoba niewidoma i na wózku w ewakuacji (0,4/0,2→0,6/0,5); U4 nie słyszy alarmu (0→0,3)
])

# wrażliwość osoby sprawnej: wysiłek schodów, nachylenie, czekanie/tłok, gubienie się
S0 = dict(A=.1, B=.05, F=.1, H=.4)


def vec(**kw):
    v = np.zeros(9)
    for k, x in kw.items(): v[CLS.index(k)] = x
    return v


def uvec(**kw):
    v = np.zeros(7)
    for k, x in kw.items(): v[UC.index(k)] = x
    return v


class Model:
    def __init__(self, M=M_V3, s0=S0, lam=1.0, Lam=200.0):
        self.M, self.s0, self.lam, self.Lam = M, vec(**s0), lam, Lam

    def s(self, u): return self.s0 + self.M @ u

    def parts(self, e, u):
        s = self.s(u)
        return e['L'], e['L'] * self.lam * (s * e['h']).sum(), self.Lam * (s * e['b']).sum()

    def cost(self, e, u): return sum(self.parts(e, u))


# 9 użytkowników: u_j ∈ [0,1] to nasilenie ograniczenia (aplikacja używa 0/1, model dopuszcza wartości pośrednie)
USERS = {
    'sprawna':            uvec(),
    'wózek':              uvec(U1=1.0, U7=.3),
    'kule':               uvec(U1=.6, U7=.5),
    'senior':             uvec(U1=.3, U3=.3, U4=.3, U5=.2, U7=.6),
    'niewidoma':          uvec(U3=1.0, U6=.3),
    'słabowidząca':       uvec(U3=.5),
    'poznawcza':          uvec(U5=.8, U6=.5),
    'wózek dziecięcy':    uvec(U1=.6, U2=.3),
    'wózek+niewidoma':    uvec(U1=1.0, U3=1.0, U6=.3, U7=.3),
}

# 12 krawędzi. h: zagrożenie na każdym metrze; b: przeszkoda raz na przejście.
EDGES = {
    'korytarz':           dict(L=20, h=vec(), b=vec()),
    'korytarz wąski':     dict(L=20, h=vec(C=.5), b=vec()),
    'korytarz ciemny':    dict(L=20, h=vec(E=.7, F=.2), b=vec()),
    'pochylnia 6%':       dict(L=10, h=vec(B=.4), b=vec()),
    'pochylnia 12%':      dict(L=5,  h=vec(B=.9, D=.1), b=vec()),
    'schody (1 kond.)':   dict(L=8,  h=vec(), b=vec(A=1.0, E=.1, I=.2)),
    'stopień 5 cm':       dict(L=1,  h=vec(), b=vec(A=.15, E=.1)),
    'drzwi ciężkie':      dict(L=2,  h=vec(), b=vec(G=.7, C=.2)),
    'winda (1 kond.)':    dict(L=3,  h=vec(), b=vec(H=.25, G=.1, C=.1, F=.1)),
    'hol zatłoczony':     dict(L=30, h=vec(H=.6, F=.2), b=vec()),
    'chodnik śliski':     dict(L=30, h=vec(D=.6), b=vec()),
    'hol bez oznakowania': dict(L=15, h=vec(), b=vec(F=.6, E=.1)),
    'schody ruchome':     dict(L=10, h=vec(), b=vec(A=1.0, G=.2, H=.2)),
}


def route(model, u, parts):
    tot = 0.0
    for name, L in parts:
        e = dict(EDGES[name])
        if L is not None: e['L'] = L
        tot += model.cost(e, u)
    return tot


def detour_tolerance(model, u, obstacle, alt, base_len=20.0):
    """Ile metrów korytarza można dołożyć do trasy z `alt`, żeby nadal była lepsza od trasy z `obstacle`
    (obie trasy tej samej długości base_len w rzucie)."""
    a = route(model, u, [('korytarz', base_len - EDGES[obstacle]['L']), (obstacle, None)])
    b = route(model, u, [('korytarz', base_len - EDGES[alt]['L']), (alt, None)])
    return a - b   # koszt korytarza = 1 m za 1 m, więc różnica kosztów = metry obejścia


# --- oczekiwane zachowania zapisane PRZED dobieraniem liczb (zakresy w metrach obejścia albo krotnościach)
def expectations(m):
    U, tol = USERS, lambda u, o, a: detour_tolerance(m, U[u], o, a)
    c = lambda u, e: m.cost(EDGES[e], U[u]) / EDGES[e]['L']
    pt = lambda u, e: m.cost(EDGES[e], U[u]) - EDGES[e]['L']   # nadwyżka ponad samą długość
    S, W = 'schody (1 kond.)', 'winda (1 kond.)'
    return [
        ('sprawna: schody zamiast windy, obejście windą nieopłacalne (tol < 0)', tol('sprawna', S, W), (-60, 0)),
        ('wózek: winda do kilkuset m obejścia, potem schody z pomocą', tol('wózek', S, W), (150, 400)),
        ('wózek dziecięcy: winda, ale wózek da się wnieść (mniej niż wózek)', tol('wózek dziecięcy', S, W), (40, 200)),
        ('kule: winda przy umiarkowanym obejściu', tol('kule', S, W), (50, 250)),
        ('senior: winda przy umiarkowanym obejściu', tol('senior', S, W), (20, 120)),
        ('niewidoma: schody i winda porównywalne (|tol| małe)', tol('niewidoma', S, W), (-50, 50)),
        ('poznawcza: schody i winda porównywalne', tol('poznawcza', S, W), (-50, 50)),
        ('wózek: pochylnia 6% akceptowalna (≤ 2× długości)', c('wózek', 'pochylnia 6%'), (1.0, 2.0)),
        ('wózek: pochylnia 12% wyraźnie gorsza od 6% (krotność)', c('wózek', 'pochylnia 12%') / c('wózek', 'pochylnia 6%'), (1.5, 4)),
        ('wózek: stopień 5 cm do pokonania (10–60 m)', pt('wózek', 'stopień 5 cm'), (10, 60)),
        ('wózek: ciężkie drzwi uciążliwe (20–150 m)', pt('wózek', 'drzwi ciężkie'), (20, 150)),
        ('drzwi: wózek ≥ wózek dziecięcy', pt('wózek', 'drzwi ciężkie') - pt('wózek dziecięcy', 'drzwi ciężkie'), (0, 1e9)),
        ('wózek: schody ruchome ≈ schody (≥ 0,9×)', pt('wózek', 'schody ruchome') / pt('wózek', S), (0.9, 1.5)),
        ('niewidoma: hol bez oznakowania kosztowny (50–250 m)', pt('niewidoma', 'hol bez oznakowania'), (50, 250)),
        ('poznawcza: hol bez oznakowania najdroższy dla niej z 9 osób', pt('poznawcza', 'hol bez oznakowania') - max(pt(k, 'hol bez oznakowania') for k in U if k != 'poznawcza'), (0, 1e9)),
        ('niewidoma: ciemny korytarz ≤ słabowidząca? nie – niewidoma ≥ słabowidzącej', c('niewidoma', 'korytarz ciemny') - c('słabowidząca', 'korytarz ciemny'), (0, 1e9)),
        ('sprawna: każdy odcinek liniowy ≤ 1,3× długości', max(c('sprawna', e) for e in EDGES if EDGES[e]['b'].sum() == 0), (1.0, 1.3)),
        ('sprawna: schody kosztują 10–30 m nadwyżki', pt('sprawna', S), (10, 30)),
        ('sprawna: czekanie na windę 10–40 m', pt('sprawna', W), (10, 40)),
        ('wózek: śliski chodnik 1,2–2×', c('wózek', 'chodnik śliski'), (1.2, 2.0)),
        ('poznawcza / stres: tłok 1,3–2,5×', c('poznawcza', 'hol zatłoczony'), (1.3, 2.5)),
    ]


def check_axioms(m, edges=EDGES):
    """A1 monotoniczność i A2 brak rozrzedzenia, wyczerpująco na profilach 0/1 (128) i krawędziach."""
    v1 = v2 = 0
    for mask in range(128):
        u = np.array([mask >> j & 1 for j in range(7)], float)
        for j in range(7):
            if mask >> j & 1: continue
            u2 = u.copy(); u2[j] = 1
            for e in edges.values():
                if m.cost(e, u2) < m.cost(e, u) - 1e-12: v1 += 1
                # A2: część kosztu przypisana do każdego ograniczenia k (M_ik u_k) nie zależy od u_j, j≠k
                for k in range(7):
                    if u[k]:
                        part = lambda uu: (m.M[:, k] * uu[k] * (e['L'] * m.lam * e['h'] + m.Lam * e['b'])).sum()
                        if abs(part(u2) - part(u)) > 1e-12: v2 += 1
    return v1, v2


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    for label, m in (('M promotora', Model(M=M_PROMOTOR)), ('M v3', Model())):
        print('\n=========== %s (λ=%.1f, Λ=%.0f m) ===========' % (label, m.lam, m.Lam))
        print('A1/A2 naruszenia (128 profili × dołożenie U × krawędzie):', check_axioms(m))
        print('%-17s' % '', ''.join('%9s' % e[:8] for e in EDGES))
        for un, u in USERS.items():
            print('%-17s' % un, ''.join('%9.0f' % m.cost(EDGES[e], u) for e in EDGES))
        ok = 0; ex = expectations(m)
        for name, val, (lo, hi) in ex:
            good = lo <= val <= hi; ok += good
            print('  [%s] %-70s %8.2f  oczekiwane %s' % ('OK' if good else '--', name, val, (lo, hi) if hi < 1e8 else '≥ %g' % lo))
        print('  spełnione %d/%d' % (ok, len(ex)))
