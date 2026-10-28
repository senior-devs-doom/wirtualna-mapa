# WirtualnaMapa

> **Status: WIP.** Demonstrator z pracy inżynierskiej (Akademia WSB). Działa end-to-end, ale parametry modelu są szacunkowe, a profil użytkownika jest dwustanowy. Interfejs i dane mogą się jeszcze zmieniać.

Wirtualna mapa wnętrza budynku uczelni: 72 zdjęcia sferyczne 360° połączone grafem, wyszukiwanie miejsc i trasa **dobrana do ograniczeń użytkownika** (siedem klas podatności, U1–U7).

## Abstract

**PL.** Aplikacja pozwala obejrzeć wnętrze budynku uczelni na 72 zdjęciach sferycznych 360° połączonych grafem i wyznaczyć trasę do wybranego miejsca z uwzględnieniem ograniczeń użytkownika. Punktem wyjścia jest model kosztu przejścia krawędzi z opracowania promotora, w którym zagrożenia środowiskowe są ważone podatnościami użytkownika. Model zmodyfikowano: wrażliwość na klasę zagrożeń liczy się jako sumę probabilistyczną, kara rośnie wykładniczo, koszt wyrażono w metrach obejścia, a krawędź rozłożono na składowe (dystans poziomy i przeszkody punktowe, np. kondygnacja schodów, jazda i oczekiwanie na windę). Na grafie 72 punktów i 194 krawędzi skierowanych trasa osoby z ograniczeniem lokomocyjnym zawiera schody w 10,9% par (osoby bez ograniczeń w 63,9%), a wyznaczenie trasy trwa średnio 20 µs. Zdjęcia są przechowywane w IPFS i dostarczane przez pamięć podręczną z pobieraniem w tle.

**EN.** The app lets the user view the interior of a university building on 72 spherical 360° photographs linked by a graph and find a route to a chosen place that accounts for the user's limitations. The starting point is the edge traversal cost model from the supervisor's study, in which environmental hazards are weighted by user vulnerabilities. The model was modified: sensitivity to a hazard class is a probabilistic sum, the penalty grows exponentially, the cost is expressed in metres of detour, and each edge is decomposed into components (horizontal distance and point obstacles such as a flight of stairs, a lift ride and waiting for a lift). On a graph of 72 points and 194 directed edges, the route of a person with a locomotor limitation contains stairs in 10.9% of node pairs (63.9% for a person without limitations), and a route is computed in 20 µs on average. Photos are stored on IPFS and served through a cache with background prefetching.

## Uruchomienie

Wymagany Node.js ≥ 20.

```bash
npm install
npm start          # http://localhost:3000
npm test           # 45 testów
```

Bez konfiguracji aplikacja czyta dołączony graf `data/graph_export.json` (tryb plikowy, bez bazy). Zdjęcia pobiera z bram IPFS po identyfikatorach z grafu, więc wymagają dostępu do internetu.

Tryb bazy (opcjonalnie): skopiuj `.env.example` do `.env`, ustaw `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, a graf wczytaj poleceniem `python data/migrate_to_neo4j.py` (domyślnie czyści docelową bazę; opcja `--no-clear`). Po zmianie danych trzeba zrestartować serwer, bo graf jest pamiętany.

## Model kosztu trasy

Koszt krawędzi to suma kosztów jej składowych, w metrach:

```
C = L_xy · (1 + Λ_h · Σ_i φ(s_i · h_i)) + Σ_k q_k · (d_k + Λ_b · Σ_i φ(s_i · b_ik))
s_i = 1 − Π_j (1 − M_ij · u_j)          φ(z) = (e^{γz} − 1) / (e^γ − 1)
```

`L_xy` to dystans poziomy, `q_k` ilość składowej punktowej (kondygnacje |Δz|/3,5, drzwi, oczekiwanie na windę), `d_k` czas jednostki wspólny dla wszystkich, `h`, `b` natężenia zagrożeń liniowych i przeszkód (klasy A–I), `M` macierz powiązań zagrożeń z ograniczeniami, `u_j` profil użytkownika. Stałe globalne: γ = 3, Λ_b = 300 m, Λ_h = Λ_b/25. Implementacja: `src/libs/riskModel.js`, trasy: Dijkstra w `src/api/path/path.service.js` (koszty krawędzi liczone raz na profil i zapamiętywane).

## Struktura

- `src/` serwer (Express): `/api/graph`, `/api/path`, `/api/config`; `src/libs/` model kosztu i miary sieci
- `public/` frontend bez budowania: widok sferyczny, mapa, wyszukiwarka, autospacer
- `data/` graf budynku (`graph_export.json`), typy odcinków (`risk_presets.json`), migracja do Neo4j
- `test/` testy modelu, wyszukiwania, pamięci zdjęć i miar sieci; `scripts/` statystyki tras i test obciążeniowy (`GRAPH_JSON=data/graph_export.json node scripts/route_stats.js`)

## Ograniczenia (WIP)

- Natężenia h, b i czasy d są oszacowaniami autora, nie pomiarami; kalibracja ankietą preferencji jest zaplanowana, ale niewykonana.
- Profil użytkownika jest dwustanowy (ograniczenie zaznaczone albo nie), choć model dopuszcza wartości ciągłe.
- Zdjęcia są hostowane w IPFS (publiczne identyfikatory CID); źródła zdjęć i narzędzia do ich przygotowania nie są częścią tego repozytorium.

## Plan prac (TODO)

- **Opisy punktów:** dziś opis ma 1 z 72 punktów; opisy (numery sal, funkcje miejsc, synonimy) zasilają wyszukiwarkę i trzeba je uzupełnić.
- **Wersja mobilna:** układ responsywny, sterowanie dotykiem w widoku sferycznym, oszczędzanie transferu, opcjonalnie żyroskop i PWA.
- Kalibracja parametrów modelu ankietą preferencji; profil użytkownika o wartościach ciągłych.

## Licencja

Wszelkie prawa zastrzeżone (patrz `LICENSE`). Kod jest publikowany do wglądu.
