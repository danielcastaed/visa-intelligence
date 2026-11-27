"""Modelo de share de facturación Visa vs Mastercard en México.

No existe una fuente pública con facturación por marca en México. Este modelo la
estima con datos públicos de Banxico:

1. Facturación total por producto (crédito / débito): SIE CF888 + CF914.
2. Tarjetas vigentes por marca y emisor anonimizado (letras): SIE CF256.
3. Peso de cada banco en crédito: saldo de los Indicadores Básicos de Tarjetas
   de Crédito (jun-2019, dic-2024, jun-2025; 2020-2023 interpolados).
4. Emparejamiento letra -> banco por tamaño, mezcla de marcas, fechas de
   entrada/salida y crecimiento (ver inputs.json > rib.bancos[*].evidencia).

Share Visa crédito = sum_k peso_k * %Visa_k   (escenarios: saldo, cartera, plásticos)
Share Visa débito  = mezcla de plásticos (sin ponderar)
Share Visa total   = promedio ponderado por facturación de cada producto

Uso:  python mexico/model.py   ->  escribe mexico/output.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_inputs():
    with open(os.path.join(HERE, "inputs.json"), encoding="utf-8") as f:
        return json.load(f)


def parse_letters(raw):
    return {k: [tuple(int(x) for x in t.split("/")) for t in v.split()] for k, v in raw.items()}


def bank_weights(rib, i, n_hist, field):
    """Peso (% del total) de cada banco en el periodo i.

    i <= n_hist-1 (2019..2024): interpolación lineal entre jun-2019 y dic-2024.
    i >= n_hist (2025, 2026*): jun-2025.
    """
    tot_key = "totales_saldo_mdp" if field == "saldo" else "totales_tarjetas_miles"
    t19, t24, t25 = (rib[tot_key][y] for y in ("2019", "2024", "2025"))
    out = {}
    for k, b in rib["bancos"].items():
        v19, v24, v25 = b[field]
        a, z, c = v19 / t19, v24 / t24, v25 / t25
        if i < n_hist:
            w = a + (z - a) * (i / (n_hist - 1))
        else:
            w = c
        if k == "P":   # American Express: sale de la serie después de 2020
            w = a if i <= 1 else 0.0
        if k == "S":   # Banco Famsa: cierra en 2020
            w = a if i == 0 else 0.0
        out[k] = w * 100
    out["R"] = max(100 - sum(out.values()), 0.0)  # resto: emisores no emparejados
    return out


def mixes_for_period(letters, tot, banks, i):
    mix = {k: letters[k][i] for k in banks if k in letters}
    sv = sum(m[0] for m in mix.values())
    sm = sum(m[1] for m in mix.values())
    so = sum(m[2] for m in mix.values())
    mix["R"] = (max(tot["visa"][i] - sv, 0), max(tot["mc"][i] - sm, 0), max(tot["otras"][i] - so, 0))
    return mix


def weighted_share(weights, mix):
    V = M = O = 0.0
    contrib = {}
    for k, w in weights.items():
        t = mix.get(k, (0, 0, 0))
        s = sum(t)
        if s <= 0:
            contrib[k] = (0.0, 0.0)
            continue
        cv, cm, co = w / 100 * t[0] / s, w / 100 * t[1] / s, w / 100 * t[2] / s
        V += cv; M += cm; O += co
        contrib[k] = (cv, cm)
    n = V + M + O
    return V / n, M / n, O / n, {k: (a / n, b / n) for k, (a, b) in contrib.items()}


def main():
    inp = load_inputs()
    periods = inp["periodos"]
    letters = parse_letters(inp["credito_por_letra"])
    ct, dt = inp["credito_totales"], inp["debito_totales"]
    fx = inp["facturacion_mmdp"]
    rib = inp["rib"]
    banks = rib["bancos"]
    n_hist = 6  # 2019..2024 interpolados

    cre = [v * (fx["empalme"]["credito"] if i <= fx["empalme"]["hasta_indice"] else 1) for i, v in enumerate(fx["credito_raw"])]
    deb = [v * (fx["empalme"]["debito"] if i <= fx["empalme"]["hasta_indice"] else 1) for i, v in enumerate(fx["debito_raw"])]

    rows, contrib_by_period = [], []
    for i, y in enumerate(periods):
        mix = mixes_for_period(letters, ct, banks, i)
        sv, sm, so, cs = weighted_share(bank_weights(rib, i, n_hist, "saldo"), mix)
        cv, cm, _, _ = weighted_share(bank_weights(rib, i, n_hist, "tarjetas"), mix)
        ctot = ct["visa"][i] + ct["mc"][i] + ct["otras"][i]
        dtot = dt["visa"][i] + dt["mc"][i] + dt["otras"][i]
        pv, pm = ct["visa"][i] / ctot, ct["mc"][i] / ctot
        dv, dm = dt["visa"][i] / dtot, dt["mc"][i] / dtot
        T = cre[i] + deb[i]
        r = {
            "periodo": y, "corte_tarjetas": inp["cortes_cf256"][i],
            "fact_credito": round(cre[i] / 1000, 3), "fact_debito": round(deb[i] / 1000, 3),
            "tarj_cr_visa": ct["visa"][i], "tarj_cr_mc": ct["mc"][i], "tarj_cr_otras": ct["otras"][i],
            "tarj_db_visa": dt["visa"][i], "tarj_db_mc": dt["mc"][i], "tarj_db_otras": dt["otras"][i],
        }
        for esc, (v, m) in {"saldo": (sv, sm), "cartera": (cv, cm), "plast": (pv, pm)}.items():
            r[f"cr_visa_{esc}"] = round(v * 100, 2)
            r[f"cr_mc_{esc}"] = round(m * 100, 2)
            r[f"tot_visa_{esc}"] = round((cre[i] * v + deb[i] * dv) / T * 100, 2)
            r[f"tot_mc_{esc}"] = round((cre[i] * m + deb[i] * dm) / T * 100, 2)
        r["cr_otras_saldo"] = round(so * 100, 2)
        r["db_visa"] = round(dv * 100, 2)
        r["db_mc"] = round(dm * 100, 2)
        rows.append(r)
        contrib_by_period.append(cs)

    # Contribución de cada banco al cambio de share en crédito (escenario saldo), 2019 -> 2025
    i0, i1 = periods.index("2019"), periods.index("2025")
    contrib = []
    for k in list(banks) + ["R"]:
        a = contrib_by_period[i0].get(k, (0, 0))
        b = contrib_by_period[i1].get(k, (0, 0))
        contrib.append({
            "letra": k, "banco": banks[k]["banco"] if k in banks else "Resto (no emparejados)",
            "visa_pp": round((b[0] - a[0]) * 100, 2), "mc_pp": round((b[1] - a[1]) * 100, 2),
        })

    # Emisores de crédito (último corte)
    last = len(periods) - 1
    emis_cr = []
    for k, t in letters.items():
        a, b = t[last], t[0]
        tot = sum(a)
        if tot == 0 and sum(b) == 0:
            continue
        info = banks.get(k)
        nombre = info["banco"] if info else ("¿Mifel?" if k == "B" else "Sin identificar")
        emis_cr.append({
            "letra": k, "banco": nombre, "confianza": info["confianza"] if info else ("Baja" if k == "B" else "—"),
            "evidencia": info["evidencia"] if info else rib["sin_identificar"].get(k, ""),
            "visa": a[0], "mc": a[1], "otras": a[2], "total": tot, "total_4T19": sum(b),
            "pct_visa": round(a[0] / tot * 100, 1) if tot else None,
            "saldo_pct_jun25": round(info["saldo"][2] / rib["totales_saldo_mdp"]["2025"] * 100, 1) if info else None,
        })
    emis_cr.sort(key=lambda r: -(r["total"] or r["total_4T19"]))

    emis_db = []
    for k, (v, m, o) in inp["debito_por_letra_2T26"].items():
        t = v + m + o
        nombre = banks[k]["banco"] if k in banks and k not in ("S", "P") else ("¿Mifel?" if k == "B" else "Sin identificar")
        emis_db.append({"letra": k, "banco": nombre, "visa": v, "mc": m, "otras": o, "total": t,
                        "pct_visa": round(v / t * 100, 1)})
    emis_db.sort(key=lambda r: -r["total"])

    out = {
        "meta": {"corte_tarjetas": inp["cortes_cf256"][-1], "corte_facturacion": "oct-2026",
                 "ultimo_anio_completo": "2025", "fuentes": inp["_doc"]},
        "anual": rows, "contribucion_credito_2019_2025": contrib,
        "emisores_credito": emis_cr, "emisores_debito": emis_db,
    }
    with open(os.path.join(HERE, "output.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for r in rows:
        print(r["periodo"], "cr V/M", r["cr_visa_saldo"], r["cr_mc_saldo"], "| db", r["db_visa"], r["db_mc"],
              "| tot", r["tot_visa_saldo"], r["tot_mc_saldo"])


if __name__ == "__main__":
    main()
