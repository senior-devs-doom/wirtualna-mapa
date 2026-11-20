Prototyp i kontrola modelu kosztu (rozdz. V pracy): model promotora (wzory bez zmian) + kalibracja parametrów + krawedz jako suma skladowych.
Nic tu nie zapisuje w bazie ani w danych grafu. Wymaga: python 3, numpy, scipy (wykresy z archiwum: matplotlib). Stan na 2026-11-19.

AKTYWNE (uruchamiac z tego katalogu: python <skrypt>)
runda_testow.py              GLOWNY SKRYPT. Parametry (reprezentacja 'split' = model docelowy): alfa = 1/9, eta = 8, kappa = 8, tau = 0,725, eps = 0,05, R_min = 0,
                             u = 0/1, M = M_V3, Lambda_b = 300 m, Lambda_h = srodek przedzialu z oczekiwan (5,28). Wypisuje: 21 oczekiwan (20/21), A1/A2, podzial kondygnacji,
                             osoba bez ograniczen = L + d, odpornosc +-25%, zgodnosc tras z v6b (0,993), H1/H2, najdluzsze obejscie bez schodow (151 m). Reprezentacja 'wektor' dla porownania.
sprawdzenia_do_pracy.py      liczby z podrozdzialu 5.3 (wrazliwosc na Lambda_b i Lambda_h) i z uwagi dla promotora (laczenie U3 i U7, wplyw zmniejszenia M i kappa).
model_promotor_skladowe.py   klasa Model (model promotora + skladowe, sep = 'split') i testy aksjomatow (A1, A2, podzial kondygnacji).
ocena_promotor_skladowe.py   make_cost(...): ten sam model na grafie budynku (tools/graph_export.json), wszystkie 128 profili.
promotor_components.py       wczytanie grafu, floyd, route; ours_cost = dotychczasowy model v6b jako ODNIESIENIE (do porownan tras).
model_v3.py                  macierze M_PROMOTOR i M_V3 (zmiany pogrubione w Tabeli 2 pracy), profile uzytkownikow, wektory.
model_v4.py                  krawedzie typowe, 21 oczekiwan (expectations), tolerancja obejscia.
model_v5.py, model_v6.py     importowane przez runda_testow.py i model_promotor_skladowe.py (testy aksjomatow; v6 = dawny v6b, odniesienie).
Zgodnosc z aplikacja: koszt WirtualnaMapa/src/libs/riskModel.js = make_cost(8, 8, 0.725, 0.05, 0, 300, 5.275202127557135, sep='split'), roznica < 1e-12 m (5112 par x 10 profili).

ARCHIWUM
archiwum_v6b/               skrypty nieuzywane przez aktywne: iteracja_kalibracji.py (zestawy K0-K6), model_v5_odpornosc.py, model_v6_graf.py, porownanie_promotor_v5.py (+ graph_export_v5.json),
                            promotor_peak.py i promotor_peak_full.py (optymalizacja swobodna), ocena_promotor_czysty.py / czysty2.py, wykresy_porownanie_modeli.py, wymagania.py.
                            Uruchamianie: w tym katalogu (tools/kalibracja) PYTHONPATH=. python archiwum_v6b/<skrypt>.
archiwum_rundy_1_6/         stare rundy dopasowania (fit_*.py, warunki*.py, model_v2, model_nadwyzkowy*) - nieuzywane.
Wyniki i opis: docs/notatki_robocze/NOTATKA_model_promotora_stan.md; wyniki starych prob: docs/notatki_robocze/archiwum/.
