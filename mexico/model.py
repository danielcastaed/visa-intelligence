"""Modelo de share de facturación Visa vs Mastercard en México.

No existe una fuente pública con facturación por marca en México. Este modelo la
estima con datos públicos de Banxico:

1. Facturación total por producto (crédito / débito): SIE CF888 (2019-2022, en
   inputs.json) + CF914 (2023+, descargado en data/banxico_montos.json).
2. Tarjetas vigentes por marca y emisor anonimizado (letras): SIE CF256
   (descargado en data/banxico_cf256.json).
3. Peso de cada banco en crédito: saldo de los Indicadores Básicos de Tarjetas
   de Crédito (inputs.json > rib).
4. Emparejamiento letra -> banco por tamaño, mezcla de marcas, fechas de
   entrada/salida y crecimiento (inputs.json > rib.bancos[*].evidencia).

Share Visa crédito = sum_k peso_k * %Visa_k   (escenarios: saldo, cartera, plásticos)
Share Visa débito  = mezcla de plásticos (sin ponderar)
Share Visa total   = promedio ponderado por facturación de cada producto

Periodos: un año por fila desde anio_inicial. Cada año usa el corte de tarjetas
del 4T; el año en curso usa el último trimestre publicado y la facturación
acumulada, y se marca con "*".

Uso:  python mexico/model.py   ->  escribe mexico/output.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BRANDS = ("visa", "mc", "otras")
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def qlabel(date):
    y, m = date[:4], int(date[5:7])
    return f"{(m - 1) // 3 + 1}T{y[2:]}"


def triple(series, date):
    return tuple(int(series.get(b, {}).get(date, 0) or 0) for b in BRANDS)


def build_periods(cf, montos, y0):
    """Lista de (etiqueta, año, corte_tarjetas, completo)."""
    fechas = cf["fechas"]
    tot = cf["credito"]["totales"]["visa"]
    last_bill = montos["ultima_fecha"]
    years = sorted({int(d[:4]) for d in fechas if int(d[:4]) >= y0})
    out = []
    for y in years:
        q4 = f"{y}-10-01"
        cuts = [d for d in fechas if d.startswith(str(y)) and d in tot]
        if not cuts:
            continue
        cut = q4 if q4 in tot else max(cuts)
        bill_full = y < int(last_bill[:4]) or last_bill.endswith("12-31")
        has_bill = str(y) in montos["credito"] or y <= 2022
        if not has_bill:
            continue
        full = cut == q4 and bill_full
        out.append((str(y) if full else f"{y}*", y, cut, full))
    return out


def bank_weights(rib, year, field):
    tot_key = "totales_saldo_mdp" if field == "saldo" else "totales_tarjetas_miles"
    t19, t24, t25 = (rib[tot_key][y] for y in ("2019", "2024", "2025"))
    out = {}
    for k, b in rib["bancos"].items():
        v19, v24, v25 = b[field]
        a, z, c = v19 / t19, v24 / t24, v25 / t25
        if year <= 2019:
            w = a
        elif year <= 2024:
            w = a + (z - a) * ((year - 2019) / 5)
        else:
            w = c
        if k == "P":   # American Express: sale de la serie después de 2020
            w = a if year <= 2020 else 0.0
        if k == "S":   # Banco Famsa: cierra en 2020
            w = a if year <= 2019 else 0.0
        out[k] = w * 100
    out["R"] = max(100 - sum(out.values()), 0.0)  # resto: emisores no emparejados
    return out


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
    n = (V + M + O) or 1
    return V / n, M / n, O / n, {k: (a / n, b / n) for k, (a, b) in contrib.items()}


def main():
    inp = load("inputs.json")
    cf = load(os.path.join("data", "banxico_cf256.json"))
    montos = load(os.path.join("data", "banxico_montos.json"))
    rib = inp["rib"]
    banks = rib["bancos"]
    hist = inp["facturacion_cf888_mmdp"]

    def bill(prod, y):
        if y <= 2022:
            return hist[prod][str(y)] * hist["empalme_a_cf914"][prod]
        return montos[prod][str(y)]

    periods = build_periods(cf, montos, inp["anio_inicial"])
    cl, dl = cf["credito"]["letras"], cf["debito"]["letras"]
    ctot, dtot = cf["credito"]["totales"], cf["debito"]["totales"]

    rows, contrib_by_year = [], {}
    for label, y, cut, full in periods:
        ct, dt = triple(ctot, cut), triple(dtot, cut)
        mix = {k: triple(v, cut) for k, v in cl.items() if k in banks}
        res = tuple(max(ct[j] - sum(m[j] for m in mix.values()), 0) for j in range(3))
        mix["R"] = res
        sv, sm, so, cs = weighted_share(bank_weights(rib, y, "saldo"), mix)
        cv, cm, _, _ = weighted_share(bank_weights(rib, y, "tarjetas"), mix)
        pv, pm = ct[0] / sum(ct), ct[1] / sum(ct)
        dv, dm = dt[0] / sum(dt), dt[1] / sum(dt)
        cre, deb = bill("credito", y), bill("debito", y)
        T = cre + deb
        r = {
            "periodo": label, "anio": y, "completo": full, "corte_tarjetas": qlabel(cut),
            "fact_credito": round(cre / 1000, 3), "fact_debito": round(deb / 1000, 3),
            "tarj_cr_visa": ct[0], "tarj_cr_mc": ct[1], "tarj_cr_otras": ct[2],
            "tarj_db_visa": dt[0], "tarj_db_mc": dt[1], "tarj_db_otras": dt[2],
        }
        for esc, (v, m) in {"saldo": (sv, sm), "cartera": (cv, cm), "plast": (pv, pm)}.items():
            r[f"cr_visa_{esc}"] = round(v * 100, 2)
            r[f"cr_mc_{esc}"] = round(m * 100, 2)
            r[f"tot_visa_{esc}"] = round((cre * v + deb * dv) / T * 100, 2)
            r[f"tot_mc_{esc}"] = round((cre * m + deb * dm) / T * 100, 2)
        r["cr_otras_saldo"] = round(so * 100, 2)
        r["db_visa"] = round(dv * 100, 2)
        r["db_mc"] = round(dm * 100, 2)
        rows.append(r)
        contrib_by_year[label] = cs

    completos = [r for r in rows if r["completo"]]
    ultimo_completo = completos[-1]["periodo"]
    first = rows[0]["periodo"]

    contrib = []
    for k in list(banks) + ["R"]:
        a = contrib_by_year[first].get(k, (0, 0))
        b = contrib_by_year[ultimo_completo].get(k, (0, 0))
        contrib.append({
            "letra": k, "banco": banks[k]["banco"] if k in banks else "Resto (no emparejados)",
            "visa_pp": round((b[0] - a[0]) * 100, 2), "mc_pp": round((b[1] - a[1]) * 100, 2),
        })

    last_cut = periods[-1][2]
    first_cut = periods[0][2]
    emis_cr = []
    for k, ser in cl.items():
        a, b = triple(ser, last_cut), triple(ser, first_cut)
        tot = sum(a)
        if tot == 0 and sum(b) == 0:
            continue
        info = banks.get(k)
        nombre = info["banco"] if info else ("¿Mifel?" if k == "B" else "Sin identificar")
        emis_cr.append({
            "letra": k, "banco": nombre,
            "confianza": info["confianza"] if info else ("Baja" if k == "B" else "—"),
            "evidencia": info["evidencia"] if info else rib["sin_identificar"].get(k, ""),
            "visa": a[0], "mc": a[1], "otras": a[2], "total": tot, "total_inicial": sum(b),
            "pct_visa": round(a[0] / tot * 100, 1) if tot else None,
            "saldo_pct_ult": round(info["saldo"][2] / rib["totales_saldo_mdp"]["2025"] * 100, 1) if info else None,
        })
    emis_cr.sort(key=lambda r: -(r["total"] or r["total_inicial"]))

    emis_db = []
    for k, ser in dl.items():
        v, m, o = triple(ser, last_cut)
        t = v + m + o
        if t <= 0:
            continue
        nombre = banks[k]["banco"] if k in banks and k not in ("S", "P") else ("¿Mifel?" if k == "B" else "Sin identificar")
        emis_db.append({"letra": k, "banco": nombre, "visa": v, "mc": m, "otras": o, "total": t,
                        "pct_visa": round(v / t * 100, 1)})
    emis_db.sort(key=lambda r: -r["total"])

    ub = montos["ultima_fecha"]
    out = {
        "meta": {
            "corte_tarjetas": qlabel(last_cut), "corte_tarjetas_inicial": qlabel(first_cut),
            "corte_facturacion": f"{MESES[int(ub[5:7]) - 1]}-{ub[:4]}",
            "ultimo_anio_completo": ultimo_completo, "primer_anio": first,
            "descargado": cf.get("descargado", ""),
        },
        "anual": rows, "contribucion_credito": contrib,
        "emisores_credito": emis_cr, "emisores_debito": emis_db,
    }
    with open(os.path.join(HERE, "output.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    for r in rows:
        print(r["periodo"], r["corte_tarjetas"], "cr V/M", r["cr_visa_saldo"], r["cr_mc_saldo"],
              "| db", r["db_visa"], r["db_mc"], "| tot", r["tot_visa_saldo"], r["tot_mc_saldo"])


if __name__ == "__main__":
    main()
