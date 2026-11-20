// riskModel.js
//
// Model ryzyka promotora (bez zmian wzoru) i zapis kosztu krawędzi jako sumy składowych.
//
// Wzór promotora, liczony dla zagrożenia o natężeniu x w jednej klasie i:
//   a_i = sum_j M_ij * u_j                       powiązanie klasy i z ograniczeniami użytkownika (u_j = 0 lub 1)
//   z   = alpha * x * a_i                        ryzyko podstawowe (R_base)
//   g   = z / (alpha * x + eps)                  względne natężenie
//   f   = z * (1 + kappa * sigma(eta * (g - tau)))   ryzyko po wzmocnieniu (R * I)
//   F   = f / f_ref                              f_ref = f dla x = 1 w klasie A przy samym U1 = 1 (przeszkoda graniczna = 1)
//
// Koszt krawędzi (zapis w implementacji: suma składowych):
//   C = L*(1 + LambdaH*sum_i F(h_i)) + q*(d + LambdaB*sum_i F(b_i))
//
// L - dystans POZIOMY krawędzi [m]; h_i - zagrożenia liniowe (na każdym metrze dystansu); q - ilość składowej
// punktowej (kondygnacje |dz|/3,5 dla schodów i jazdy windą, mogą być ułamkowe; liczba drzwi; 1 dla oczekiwania na
// windę); b_i - bariera jednej jednostki; d - czas jednostki wspólny dla wszystkich użytkowników [m ekwiwalentu].
// Koszt jest w metrach: osoba bez ograniczeń (a = 0) płaci L + q*d. Jedna krawędź niesie jedną składową punktową.
//
// Etapy, żeby w pętli po krawędziach zostało tylko to, co zależy od pary (krawędź, profil):
//   prepareUser(u_vec)  - raz na profil:   a_i
//   prepareEdge(props)  - raz na krawędź:  {L, q, d, h[], b[]}
//   costPrepared(e, a)  - na parę:         wzór powyżej
// Wynik jest matematycznie identyczny z wersją "wszystko w każdym wywołaniu".

const ENV_CLASSES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I'];

// Profil demonstratora: ograniczenie zaznaczone = 1, niezaznaczone = 0 (R_min = 0).
const U_ON = 1.0;
const U_OFF = 0.0;

class RiskModel {
    constructor() {
        // Macierz powiązań zagrożeń (wiersze A..I) z ograniczeniami (kolumny U1..U7):
        // macierz promotora z kalibracją wpisów (uzasadnienie każdego wiersza: tools/kalibracja/model_v3.py, M_V3).
        this.M = [
            [1.0, 0.2, 0.3, 0.1, 0.0, 0.1, 0.6],
            [0.9, 0.2, 0.0, 0.0, 0.0, 0.1, 0.5],
            [0.8, 0.2, 0.3, 0.0, 0.1, 0.3, 0.1],
            [0.8, 0.1, 0.4, 0.3, 0.0, 0.1, 0.3],
            [0.0, 0.0, 1.0, 0.2, 0.3, 0.2, 0.1],
            [0.0, 0.0, 0.8, 0.4, 1.0, 0.4, 0.0],
            [0.6, 1.0, 0.3, 0.1, 0.1, 0.1, 0.3],
            [0.4, 0.2, 0.4, 0.2, 0.5, 1.0, 0.3],
            [0.6, 0.2, 0.5, 0.3, 0.5, 1.0, 0.4],
        ];

        this.alpha = 1 / 9;             // waga klasy zagrożeń (jednakowa)
        this.eta = 8.0;                 // stromość wzmocnienia (jak u promotora)
        this.kappa = 8.0;               // siła wzmocnienia
        this.tau = 0.725;               // próg wzmocnienia
        this.eps = 0.05;                // wygładzenie mianownika względnego natężenia
        this.LambdaB = 300.0;           // Λ_b: koszt bariery granicznej [m obejścia]
        this.LambdaH = 5.275202127557135; // Λ_h: koszt metra granicznego odcinka liniowego (środek przedziału z oczekiwań)
        this.safetyScale = this.LambdaB; // tylko wyświetlanie: Safety = exp(-C / safetyScale)
        this.fref = this._f(1, 1.0);    // klasa A, natężenie 1, a_A = M_A1 * 1 (samo U1)
    }

    // ryzyko po wzmocnieniu dla natężenia x w klasie o powiązaniu a
    _f(x, a) {
        const z = this.alpha * x * a;
        const g = z / (this.alpha * x + this.eps);
        return z * (1 + this.kappa / (1 + Math.exp(-this.eta * (g - this.tau))));
    }

    // zależy tylko od użytkownika: a_i = sum_j M_ij * u_j
    prepareUser(u_vec) {
        const a = new Float64Array(this.M.length);
        for (let i = 0; i < this.M.length; i++) {
            let sum = 0;
            for (let j = 0; j < u_vec.length; j++) sum += this.M[i][j] * u_vec[j];
            a[i] = sum;
        }
        return a;
    }

    // zależy tylko od krawędzi; props: {L, q, d, hA..hI, bA..bI} (brak pola = 0)
    prepareEdge(props) {
        return {
            L: props.L,
            q: props.q || 0,
            d: props.d || 0,
            h: ENV_CLASSES.map(c => props['h' + c] || 0),
            b: ENV_CLASSES.map(c => props['b' + c] || 0),
        };
    }

    // jedyne, co zostaje do policzenia dla pary (krawędź, użytkownik)
    costPrepared(edge, a) {
        let linear = 0;
        let point = 0;
        for (let i = 0; i < a.length; i++) {
            if (edge.h[i] > 0) linear += this._f(edge.h[i], a[i]) / this.fref;
            if (edge.b[i] > 0) point += this._f(edge.b[i], a[i]) / this.fref;
        }
        return edge.L * (1 + this.LambdaH * linear) + edge.q * (edge.d + this.LambdaB * point);
    }

    // pojedyncze wywołanie bez przygotowania (testy, skrypty)
    computeCost(props, user) {
        return this.costPrepared(this.prepareEdge(props), this.prepareUser(user.u_vec));
    }

    computeSafety(cost) {
        return Math.exp(-cost / this.safetyScale);
    }
}

// Długość pokonanej drogi (do wyświetlania i statystyk, nie do kosztu): przeciwprostokątna dystansu poziomego L
// i różnicy wysokości q kondygnacji schodów lub jazdy windą.
const METERS_PER_LEVEL = 3.5;
RiskModel.edgeLength = props => {
    const vertical = props.preset === 'stairs' || props.preset === 'elevator' ? (props.q || 0) * METERS_PER_LEVEL : 0;
    return Math.hypot(props.L, vertical);
};

module.exports = RiskModel;
module.exports.ENV_CLASSES = ENV_CLASSES;
module.exports.U_ON = U_ON;
module.exports.U_OFF = U_OFF;
