// riskModel.js
//
// Koszt krawędzi (model v6b: koszt krawędzi = suma kosztów jej składowych):
//
//   s_i  = 1 - prod_j (1 - M_ij * u_j)              wrażliwość użytkownika na klasę zagrożeń i, w [0,1]
//   phi(z) = (e^(gamma*z) - 1) / (e^gamma - 1)      wypukła, phi(0) = 0, phi(1) = 1
//   C = L*(1 + LambdaH*sum_i phi(s_i*h_i)) + q*(d + LambdaB*sum_i phi(s_i*b_i))
//
// L - dystans POZIOMY krawędzi [m] (wysokość niesie składowa punktowa, nie długość 3D);
// h_i - zagrożenia liniowe (na każdym metrze dystansu); q - ilość składowej punktowej
// (kondygnacje |dz|/3,5 dla schodów i jazdy windą - mogą być ułamkowe; liczba drzwi;
// 1 dla oczekiwania na windę); b_i - bariera jednej jednostki; d - czas jednostki wspólny dla
// wszystkich użytkowników [m ekwiwalentu]. Koszt jest w metrach: osoba bez ograniczeń (s = 0)
// płaci L + q*d. Jedna krawędź niesie jedną składową (dystans plus ewentualnie jeden typ q).
//
// Etapy, żeby w pętli po krawędziach zostało tylko to, co zależy od pary (krawędź, profil):
//   prepareUser(u_vec)  - raz na profil:   s_i
//   prepareEdge(props)  - raz na krawędź:  {L, q, d, h[], b[]}
//   costPrepared(e, s)  - na parę:         wzór powyżej
// Wynik jest matematycznie identyczny z wersją "wszystko w każdym wywołaniu".

const ENV_CLASSES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I'];

// Profil demonstratora: ograniczenie zaznaczone = 1, niezaznaczone = 0 (model dopuszcza wartości z [0,1]).
const U_ON = 1.0;
const U_OFF = 0.0;

class RiskModel {
    constructor() {
        // Macierz powiązań zagrożeń (wiersze A..I) z ograniczeniami (kolumny U1..U7):
        // macierz promotora z poprawkami własnymi (uzasadnienie każdego wiersza: tools/kalibracja/model_v3.py, M_V3).
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

        this.gamma = 3.0;               // rozpiętość między łagodnym a granicznym zagrożeniem (~e^gamma)
        this.LambdaB = 300.0;           // Λ_b: koszt bariery granicznej [m obejścia]
        this.LambdaH = this.LambdaB / 25; // Λ_h = Λ_b/ℓ0, ℓ0 = 25 m: koszt metra granicznego odcinka liniowego
        this.safetyScale = this.LambdaB; // tylko wyświetlanie: Safety = exp(-C / safetyScale)
    }

    phi(z) {
        return Math.expm1(this.gamma * z) / Math.expm1(this.gamma);
    }

    // zależy tylko od użytkownika: s_i = 1 - prod_j (1 - M_ij * u_j)
    prepareUser(u_vec) {
        const s = new Float64Array(this.M.length);
        for (let i = 0; i < this.M.length; i++) {
            let keep = 1;
            for (let j = 0; j < u_vec.length; j++) keep *= 1 - this.M[i][j] * u_vec[j];
            s[i] = 1 - keep;
        }
        return s;
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
    costPrepared(edge, s) {
        let linear = 0;
        let point = 0;
        for (let i = 0; i < s.length; i++) {
            if (edge.h[i] > 0) linear += this.phi(s[i] * edge.h[i]);
            if (edge.b[i] > 0) point += this.phi(s[i] * edge.b[i]);
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
