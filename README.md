# WirtualnaMapa

> **Status: WIP.** Demonstrator z pracy inżynierskiej (Akademia WSB). Działa end-to-end, ale parametry modelu są szacunkowe, a profil użytkownika jest dwustanowy. Interfejs i dane mogą się jeszcze zmieniać.

Wirtualna mapa wnętrza budynku uczelni: 72 zdjęcia sferyczne 360° połączone grafem, wyszukiwanie miejsc i trasa **dobrana do ograniczeń użytkownika** (siedem klas podatności, U1–U7).

## Abstract

**PL.** Praca przedstawia system, który pozwala obejrzeć wnętrze budynku uczelni na 72 zdjęciach sferycznych 360° połączonych grafem i wyznaczyć trasę do wybranego miejsca z uwzględnieniem ograniczeń użytkownika (siedem klas podatności). Punktem wyjścia jest model kosztu przejścia krawędzi z opracowania promotora, w którym zagrożenia środowiskowe są ważone podatnościami użytkownika. Model zastosowano bez zmiany wzorów: skalibrowano jego parametry (wartości profilu użytkownika, próg i siłę wzmocnienia, macierz powiązań, skalę kosztu w metrach obejścia), a w implementacji zapisano krawędź jako sumę składowych: dystansu poziomego i przeszkód punktowych (kondygnacji schodów, jazdy windą i oczekiwania na windę). Na grafie 72 punktów i 196 krawędzi skierowanych, dla 5112 par węzłów, trasa osoby z ograniczeniem lokomocyjnym zawiera schody w 10,9% przypadków (osoby bez ograniczeń w 62,9%), a wyznaczenie trasy trwa średnio 20 µs. Zdjęcia przechowywane w sieci IPFS dostarcza się bez widocznej zwłoki dzięki pamięci podręcznej i pobieraniu w tle. Parametry modelu są szacunkowe; praca stanowi dowód wykonalności.

**EN.** The work presents a system that lets the user view the interior of a university building on 72 spherical 360° photographs linked by a graph and find a route to a chosen place that accounts for the user's limitations (seven vulnerability classes). The starting point is the edge traversal cost model from the supervisor's study, in which environmental hazards are weighted by user vulnerabilities. The model was applied without changing its formulas: its parameters were calibrated (user profile values, threshold and strength of the amplification, association matrix and the cost scale in metres of detour), and in the implementation an edge is stored as a sum of components: horizontal distance and point obstacles (floors of stairs, lift ride and waiting for the lift). On a graph of 72 points and 196 directed edges, for 5112 node pairs, the route of a person with a locomotor limitation contains stairs in 10.9% of cases (62.9% for a person without limitations), and a route is computed in 20 µs on average. Photographs stored in the IPFS network are delivered without visible delay thanks to a cache and background downloading. The model parameters are estimates; the work is a proof of feasibility.

## Uruchomienie

Wymagany Node.js ≥ 20.

```bash
cd WirtualnaMapa
npm install
npm start          # http://localhost:3000
npm test           # 48 testów
```

Bez konfiguracji aplikacja czyta dołączony graf `WirtualnaMapa/data/graph_export.json` (tryb plikowy, bez bazy). Zdjęcia pobiera z bram IPFS po identyfikatorach z grafu, więc wymagają dostępu do internetu.

Tryb bazy (opcjonalnie): skopiuj `WirtualnaMapa/.env.example` do `WirtualnaMapa/.env`, ustaw `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, a graf wczytaj poleceniem `python tools/migrate_to_neo4j.py` (domyślnie czyści docelową bazę; opcja `--no-clear`). Po zmianie danych trzeba zrestartować serwer, bo graf jest pamiętany.

## Model kosztu trasy

Wzór ryzyka pochodzi z opracowania promotora i nie został zmieniony. Dla zagrożenia o natężeniu `x` w klasie `i`:

```
a_i = Σ_j M_ij · u_j        z = α · x · a_i        g = z / (α · x + ε)
f   = z · (1 + κ / (1 + exp(−η (g − τ))))          F = f / f_ref
```

Parametry: α = 1/9, η = 8, κ = 8, τ = 0,725, ε = 0,05, R_min = 0, u_j ∈ {0, 1}; `F = 1` to przeszkoda graniczna (klasa A przy samym U1). Krawędź zapisano jako sumę składowych, w metrach:

```
C = L_xy · (1 + Λ_h · Σ_i F(h_i)) + Σ_k q_k · (d_k + Λ_b · Σ_i F(b_ik))
```

`L_xy` to dystans poziomy, `q_k` ilość składowej punktowej (kondygnacje |Δz|/3,5, drzwi, oczekiwanie na windę), `d_k` czas jednostki wspólny dla wszystkich, `h`, `b` natężenia zagrożeń liniowych i przeszkód (klasy A–I), `M` macierz powiązań zagrożeń z ograniczeniami, `u_j` profil użytkownika; Λ_b = 300 m, Λ_h = 5,28. Implementacja: `WirtualnaMapa/src/libs/riskModel.js`, trasy: Dijkstra w `WirtualnaMapa/src/api/path/path.service.js` (koszty krawędzi liczone raz na profil i zapamiętywane).

## Struktura

- `WirtualnaMapa/` aplikacja: `src/` serwer (Express: `/api/graph`, `/api/path`, `/api/config`; `src/libs/` model kosztu i miary sieci), `public/` frontend bez budowania (widok sferyczny, mapa, wyszukiwarka, autospacer), `test/` testy, `scripts/` statystyki tras i analiza najgorszych tras (`GRAPH_JSON=data/graph_export.json node scripts/route_stats.js`), `data/graph_export.json` graf dla trybu plikowego
- `tools/` dane i narzędzia procesu: `location.csv` (punkty), `edges.json` i `risk_presets.json` (krawędzie i typy odcinków), `build_export.py` (eksport grafu), `migrate_to_neo4j.py`, edytory (`map_editor.html`, `edge_editor.html`, `server.py`), skrypty zdjęć i IPFS, `photo_cids.json`
- `tools/kalibracja/` prototyp modelu w Pythonie i testy zachowania (`runda_testow.py`, wymaga numpy)

## Ograniczenia (WIP)

- Natężenia h, b i czasy d są oszacowaniami autora, nie pomiarami; kalibracja ankietą preferencji jest zaplanowana, ale niewykonana.
- Profil użytkownika jest dwustanowy (ograniczenie zaznaczone albo nie), choć model dopuszcza wartości ciągłe.
- Zdjęcia nie są częścią repozytorium: aplikacja pobiera je wyłącznie z IPFS po identyfikatorach CID z grafu (`tools/photo_cids.json`); pliki źródłowe zdjęć są archiwum poza repozytorium, a aplikacja ich nie używa.

## Plan prac (TODO)

- **Opisy punktów:** dziś opis ma 1 z 72 punktów; opisy (numery sal, funkcje miejsc, synonimy) zasilają wyszukiwarkę i trzeba je uzupełnić.
- **Wersja mobilna:** układ responsywny, sterowanie dotykiem w widoku sferycznym, oszczędzanie transferu, opcjonalnie żyroskop i PWA.
- Kalibracja parametrów modelu ankietą preferencji; profil użytkownika o wartościach ciągłych.

## Licencja

Wszelkie prawa zastrzeżone (patrz `LICENSE`). Kod jest publikowany do wglądu.
