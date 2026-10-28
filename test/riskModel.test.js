const test = require('node:test');
const assert = require('node:assert');
const RiskModel = require('../src/libs/riskModel');

const { U_ON, U_OFF } = RiskModel;
const profile = mask => Array.from({ length: 7 }, (_, j) => (mask >> j & 1 ? U_ON : U_OFF));
const m = new RiskModel();

// presety krawędzi jak w tools/risk_presets.json (pozostałe klasy 0)
const STAIRS = { L: 8, q: 1, d: 10, bA: 1.0, bE: 0.1 };
const LIFT_RIDE = { L: 0, q: 1, d: 3 };
// oczekiwanie i obsługa kabiny tylko na krawędzi wejścia (q = 1); wyjście z windy to sam dystans
const LIFT_ENTRY = { L: 5, q: 1, d: 25, bC: 0.1, bG: 0.15, bF: 0.1, bH: 0.05 };
const LIFT_EXIT = { L: 5 };
const CORRIDOR = { L: 20 };
const NARROW = { L: 20, hC: 0.3 };
const DARK = { L: 20, hE: 0.6, hF: 0.2 };
const ALL = [STAIRS, LIFT_RIDE, LIFT_ENTRY, LIFT_EXIT, CORRIDOR, NARROW, DARK, { L: 10, hB: 0.9 }, { L: 2, q: 1, d: 2, bG: 0.7, bC: 0.2 }];
const cost = (e, mask) => m.computeCost(e, { u_vec: profile(mask) });
const costU = (e, u) => m.computeCost(e, { u_vec: u });
const near = (a, b, eps = 1e-5) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

// wszystkie pary (profil, profil z jednym dodatkowym U)
const pairs = [];
for (let s = 0; s < 128; s++) for (let j = 0; j < 7; j++) if (!(s >> j & 1)) pairs.push([s, s | 1 << j]);

test('A1: dołożenie ograniczenia nigdy nie obniża kosztu żadnej krawędzi (128 profili)', () => {
  for (const e of ALL) for (const [s, t] of pairs) assert.ok(cost(e, t) >= cost(e, s) - 1e-9, `${s} -> ${t}`);
});

test('A2: dołożenie ograniczenia nie zmienia składników klas, na które nie działa (brak rozrzedzania)', () => {
  // U2 nie wpływa na klasę E (M[E][U2] = 0): dwie krawędzie różniące się tylko w klasie E mają tę samą różnicę kosztów z U2 i bez
  const a = { L: 10, q: 1, bE: 0.8 }, b = { L: 10, q: 1 };
  const u0 = profile(0b0000001), u1 = profile(0b0000011);
  const diff = u => costU(a, u) - costU(b, u);
  near(diff(u0), diff(u1), 1e-9);
  // wózek (U1) plus wzrok (U3): koszt schodów od U1 nie maleje
  assert.ok(cost(STAIRS, 0b101) >= cost(STAIRS, 0b001) - 1e-9);
});

test('osoba bez ograniczeń płaci długość i czas: C = L + q*d', () => {
  near(cost(STAIRS, 0), 18);
  near(cost(CORRIDOR, 0), 20);
  near(cost(LIFT_ENTRY, 0), 5 + 25);
});

test('zgodność z prototypem w Pythonie (tools/kalibracja/model_v6.py, gamma 3, LambdaB 300)', () => {
  const cr = { L: 20, hC: 0.3 };
  near(cost(STAIRS, 0b001), 318.0);       // U1
  near(cost(STAIRS, 0b100), 46.442405);   // U3
  near(cost(STAIRS, 127), 323.499329);    // wszystkie
  near(cost(cr, 0b001), 33.259463);
  near(cost(cr, 0b100), 23.897793);
  near(cost(cr, 127), 36.6363, 1e-4);
});

test('osoba na wózku: kondygnacja schodów kosztuje wielokrotnie więcej niż jazda windą, osoba sprawna odwrotnie', () => {
  const lift = e => cost(LIFT_ENTRY, e) + cost(LIFT_EXIT, e) + cost(LIFT_RIDE, e);
  assert.ok(cost(STAIRS, 0b001) > 4 * lift(0b001));
  assert.ok(cost(STAIRS, 0) < lift(0));
});

test('przykład 20 m schodami wobec 60 m z windą: wózek wybiera windę, osoba sprawna schody', () => {
  const stairsRoute = e => cost({ L: 12 }, e) + cost(STAIRS, e);
  const liftRoute = (e, extra) => cost({ L: 12 + extra }, e) + cost(LIFT_ENTRY, e) + cost(LIFT_EXIT, e) + cost(LIFT_RIDE, e);
  assert.ok(stairsRoute(0) < liftRoute(0, 40));
  assert.ok(stairsRoute(0b001) > liftRoute(0b001, 150));   // wózek: nawet 150 m obejścia się opłaca
  assert.ok(stairsRoute(0b001) < liftRoute(0b001, 330));   // ... ale koszt jest skończony: przy bardzo długim obejściu schody z pomocą
});

test('koszt kondygnacji nie zależy od podziału klatki schodowej w grafie (q na zewnątrz funkcji phi)', () => {
  const full = { L: 0, q: 2, d: 10, bA: 1.0, bE: 0.1 };
  const half = { L: 0, q: 1, d: 10, bA: 1.0, bE: 0.1 };
  for (const mask of [0, 1, 127]) near(cost(full, mask), 2 * cost(half, mask), 1e-9);
});

test('część liniowa kosztu jest proporcjonalna do długości', () => {
  const c = L => cost({ L, hC: 0.3 }, 0b001);
  near(c(10), 2 * c(5), 1e-9);
});

test('przeszkoda punktowa nie zależy od długości krawędzi', () => {
  const pt = L => cost({ L, q: 1, bA: 1.0 }, 0b001) - L;
  near(pt(3), pt(30), 1e-9);
});

test('koszt jest ograniczony: wszystkie ograniczenia nie przekraczają ceny przeszkody granicznej', () => {
  assert.ok(cost({ L: 1, q: 1, bA: 1.0 }, 127) <= 1 + m.LambdaB + 1e-9);
});

test('safety maleje z kosztem i mieści się w (0, 1]', () => {
  assert.ok(m.computeSafety(0) === 1);
  assert.ok(m.computeSafety(100) < m.computeSafety(10));
  assert.ok(m.computeSafety(5000) > 0);
});

test('v6b: podział kondygnacji na części (q ułamkowe) nie zmienia kosztu, także z podestem pośrednim', () => {
  const whole = { L: 6, q: 1, d: 10, bA: 1.0, bE: 0.1 };
  const part = frac => ({ L: 6 * frac, q: frac, d: 10, bA: 1.0, bE: 0.1 });
  for (const mask of [0, 1, 0b100, 127]) near(cost(whole, mask), cost(part(0.3), mask) + cost(part(0.7), mask), 1e-9);
});

test('v6b: oczekiwanie na windę kosztuje tyle samo dla wszystkich profili bez bariery', () => {
  const wait = { L: 0, q: 1, d: 25 };
  const base = cost(wait, 0);
  for (let s = 0; s < 128; s++) near(cost(wait, s), base, 1e-9);
  near(base, 25);
});

test('v6b: wysokość nie wchodzi do dystansu - koszt schodów jest funkcją q, nie długości 3D', () => {
  near(cost({ L: 5, q: 1, d: 10, bA: 1 }, 0), 15);
  near(cost({ L: 5, q: 2, d: 10, bA: 1 }, 0), 25);
});
