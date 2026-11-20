// test.js

const RiskModel = require('./riskModel');
const { normalize } = RiskModel;

const ENV_CLASSES = ["A","B","C","D","E","F","G","H","I"];
const USER_CLASSES = ["U1","U2","U3","U4","U5","U6","U7"];

function main() {
    const model = new RiskModel();

    // ---- Edge ----
    const e_raw = {
        A: 0.85, B: 0.10, C: 0.20, D: 0.30,
        E: 0.45, F: 0.55, G: 0.15, H: 0.10, I: 0.10,
    };

    const e_vec = ENV_CLASSES.map(c => normalize(e_raw[c]));

    const edge = {
        edge_id: "edge_1",
        L: 20.0,
        e_vec: e_vec
    };

    // ---- Users ----
    const uA = USER_CLASSES.map(() => normalize(0.10));

    const uB_raw = [0.10, 0.10, 0.85, 0.20, 0.55, 0.20, 0.15];
    const uC_raw = [0.85, 0.45, 0.10, 0.20, 0.15, 0.15, 0.55];

    const users = [
        { user_id: "normalny", u_vec: uA },
        { user_id: "wzrokowa", u_vec: uB_raw.map(normalize) },
        { user_id: "ruchowa",  u_vec: uC_raw.map(normalize) },
    ];

    console.log("== COST ONLY (production view) ==");
    console.log(`Krawędź: ${edge.edge_id}, L=${edge.L}`);
    console.log();

    users.forEach(user => {
        const cost = model.computeCost(edge, user);
        const safety = model.computeSafety(cost);

        console.log(
            `${user.user_id.padEnd(10)} → cost=${cost.toFixed(4)} | safety=${safety.toFixed(4)}`
        );
    });
}

main();