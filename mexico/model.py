"""Modelo de share de facturación Visa vs Mastercard en México.

No existe una fuente pública con facturación por marca en México. Este modelo la
estima con datos públicos de Banxico:

1. Facturación total por producto (crédito / débito): SIE CF888 (2009-2022) y
   CF914 (dic-2022 en adelante), empalmadas con el traslape de dic-2022.
   -> data/banxico_montos.json (mensual, trimestral, anual)
2. Tarjetas vigentes por marca y emisor anonimizado (letras), trimestral: SIE CF256.
   -> data/banxico_cf256.json
3. Peso de cada banco en crédito: saldo de los Indicadores Básicos de Tarjetas de
   Crédito (inputs.json > rib), interpolado entre reportes.
4. Emparejamiento letra -> banco (inputs.json > rib.bancos[*].evidencia).

Share Visa crédito = sum_k peso_k * %Visa_k   (escenarios: saldo, cartera, plásticos)
Share Visa débito  = mezcla de plásticos (sin ponderar)
Share Visa total   = promedio ponderado por facturación de cada producto

Granularidad: CF256 solo es trimestral, así que el share por marca es anual
(corte 4T) o trimestral. La facturación total por producto también sale mensual.

Uso:  python mexico/model.py   ->  escribe mexico/output.json
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BRANDS = ("visa", "mc", "otras")
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
Q_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def qlabel(date):
    return f"{(int(date[5:7]) - 1) // 3 + 1}T{date[2:4]}"


def triple(series, date):
    return tuple(int(series.get(b, {}).get(date, 0) or 0) for b in BRANDS)


class Billing:
    """Facturación (miles de millones MXN) empalmando CF888 -> CF914 en dic-2022."""

    def __init__(self, montos):
        self.m = montos
        self.last = montos["ultima_fecha"]
        self.factor = {}
        for p in ("credito", "debito"):
            a = montos["cf888"][p]["mensual"].get("2022-12")
            b = montos["cf914"][p]["mensual"].get("2022-12")
            self.factor[p] = (b / a) if a and b else 1.0

    def get(self, prod, gran, key):
        if gran == "anual":
            old = int(key) <= 2022
        elif gran == "trimestral":
            old = key <= "2022-T4"
        else:
            old = key <= "2022-11"
        src = "cf888" if old else "cf914"
        v = self.m[src][prod][gran].get(key)
        if v is None:
            return None
        return v * self.factor[prod] if old else v

    def months(self):
        keys = set(self.m["cf888"]["credito"]["mensual"]) | set(self.m["cf914"]["credito"]["mensual"])
        return sorted(k for k in keys if self.get("credito", "mensual", k) is not None)


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
    out["R"] = max(100 - sum(out.values()), 0.0)
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


def share_row(label, year, cut, cre, deb, cf, rib, extra):
    banks = rib["bancos"]
    ctot, dtot = cf["credito"]["totales"], cf["debito"]["totales"]
    ct, dt = triple(ctot, cut), triple(dtot, cut)
    mix = {k: triple(v, cut) for k, v in cf["credito"]["letras"].items() if k in banks}
    mix["R"] = tuple(max(ct[j] - sum(m[j] for m in mix.values()), 0) for j in range(3))
    sv, sm, so, cs = weighted_share(bank_weights(rib, year, "saldo"), mix)
    cv, cm, _, _ = weighted_share(bank_weights(rib, year, "tarjetas"), mix)
    pv, pm = ct[0] / sum(ct), ct[1] / sum(ct)
    dv, dm = dt[0] / sum(dt), dt[1] / sum(dt)
    T = cre + deb
    r = {"periodo": label, "anio": year, "corte_tarjetas": qlabel(cut),
         "fact_credito": round(cre / 1000, 4), "fact_debito": round(deb / 1000, 4),
         "tarj_cr_visa": ct[0], "tarj_cr_mc": ct[1], "tarj_cr_otras": ct[2],
         "tarj_db_visa": dt[0], "tarj_db_mc": dt[1], "tarj_db_otras": dt[2]}
    r.update(extra)
    for esc, (v, m) in {"saldo": (sv, sm), "cartera": (cv, cm), "plast": (pv, pm)}.items():
        r[f"cr_visa_{esc}"] = round(v * 100, 2)
        r[f"cr_mc_{esc}"] = round(m * 100, 2)
        r[f"tot_visa_{esc}"] = round((cre * v + deb * dv) / T * 100, 2)
        r[f"tot_mc_{esc}"] = round((cre * m + deb * dm) / T * 100, 2)
    r["db_visa"] = round(dv * 100, 2)
    r["db_mc"] = round(dm * 100, 2)
    return r, cs


def main():
    inp = load("inputs.json")
    cf = load(os.path.join("data", "banxico_cf256.json"))
    bill = Billing(load(os.path.join("data", "banxico_montos.json")))
    rib = inp["rib"]
    banks = rib["bancos"]
    y0 = inp["anio_inicial"]
    fechas = [d for d in cf["fechas"] if d in cf["credito"]["totales"]["visa"]]
    last_bill = bill.last

    # ---------- Anual (corte 4T; año en curso: último trimestre + facturación acumulada)
    anual, contrib_by = [], {}
    for y in sorted({int(d[:4]) for d in fechas if int(d[:4]) >= y0}):
        cuts = [d for d in fechas if d.startswith(str(y))]
        q4 = f"{y}-10-01"
        cut = q4 if q4 in cuts else max(cuts)
        cre, deb = bill.get("credito", "anual", str(y)), bill.get("debito", "anual", str(y))
        if cre is None or deb is None:
            continue
        full = cut == q4 and (y < int(last_bill[:4]) or last_bill.endswith("12-31"))
        label = str(y) if full else f"{y}*"
        r, cs = share_row(label, y, cut, cre, deb, cf, rib, {"completo": full})
        anual.append(r)
        contrib_by[label] = cs

    # ---------- Trimestral (desde 1T del año inicial)
    trimestral = []
    for d in fechas:
        y, q = int(d[:4]), (int(d[5:7]) - 1) // 3 + 1
        if y < y0:
            continue
        key = f"{y}-T{q}"
        cre, deb = bill.get("credito", "trimestral", key), bill.get("debito", "trimestral", key)
        if cre is None or deb is None:
            continue
        full = last_bill >= f"{y}-{Q_END[q]}"
        r, _ = share_row(qlabel(d) + ("" if full else "*"), y, d, cre, deb, cf, rib, {"completo": full, "trimestre": key})
        trimestral.append(r)

    # ---------- Histórico de tarjetas (plásticos), trimestral desde 2006
    hist = []
    for d in fechas:
        ct, dt = triple(cf["credito"]["totales"], d), triple(cf["debito"]["totales"], d)
        if sum(ct) == 0:
            continue
        hist.append({"corte": qlabel(d), "fecha": d,
                     "cr_visa": ct[0], "cr_mc": ct[1], "cr_otras": ct[2],
                     "db_visa": dt[0], "db_mc": dt[1], "db_otras": dt[2]})

    # ---------- Facturación mensual por producto (oficial)
    mensual = [{"mes": m, "credito": round(bill.get("credito", "mensual", m), 2),
                "debito": round(bill.get("debito", "mensual", m) or 0, 2)} for m in bill.months() if m >= "2009-01"]

    completos = [r for r in anual if r["completo"]]
    ultimo = completos[-1]["periodo"]
    first = anual[0]["periodo"]

    # ---------- Contribución por banco al Δ share de crédito (escenario saldo)
    contrib = []
    for k in list(banks) + ["R"]:
        a, b = contrib_by[first].get(k, (0, 0)), contrib_by[ultimo].get(k, (0, 0))
        contrib.append({"letra": k, "banco": banks[k]["banco"] if k in banks else "Resto (no emparejados)",
                        "visa_pp": round((b[0] - a[0]) * 100, 2), "mc_pp": round((b[1] - a[1]) * 100, 2)})

    def nombre(k, producto):
        if k in banks and not (producto == "debito" and k in ("S", "P")):
            return banks[k]["banco"]
        return "¿Mifel?" if k == "B" else f"Emisor {k}"

    # ---------- Heatmap y concentración por emisor (tarjetas vigentes)
    def issuer_views(producto):
        letras = cf[producto]["letras"]
        cuts = {}
        for y in sorted({int(d[:4]) for d in fechas if int(d[:4]) >= y0}):
            yc = [d for d in fechas if d.startswith(str(y))]
            q4 = f"{y}-10-01"
            cuts[str(y) if q4 in yc else f"{y}*"] = q4 if q4 in yc else max(yc)
        heat = {}
        for marca_idx, marca in ((None, "total"), (0, "visa"), (1, "mc")):
            rows = {}
            for lbl, cut in cuts.items():
                vals = {k: triple(s, cut) for k, s in letras.items()}
                den = sum((sum(v) if marca_idx is None else v[marca_idx]) for v in vals.values())
                if den <= 0:
                    continue
                for k, v in vals.items():
                    num = sum(v) if marca_idx is None else v[marca_idx]
                    rows.setdefault(k, {})[lbl] = round(num / den * 100, 3)
            heat[marca] = rows
        last_cut = list(cuts.values())[-1]
        # año contra año: mismo trimestre del año anterior
        prev_cut = f"{int(last_cut[:4]) - 1}{last_cut[4:]}"
        conc = {}
        for idx, marca in ((0, "visa"), (1, "mc")):
            out = {}
            for tag, cut in (("actual", last_cut), ("anterior", prev_cut)):
                vals = {k: triple(s, cut)[idx] for k, s in letras.items()}
                den = sum(vals.values())
                if den <= 0:
                    continue
                shares = {k: v / den * 100 for k, v in vals.items() if v > 0}
                out[tag] = {"hhi": round(sum(s * s for s in shares.values())),
                            "shares": {k: round(s, 2) for k, s in shares.items()}}
            top = sorted(out.get("actual", {}).get("shares", {}).items(), key=lambda kv: -kv[1])[:10]
            conc[marca] = {
                "corte": qlabel(last_cut), "corte_anterior": qlabel(prev_cut),
                "hhi": out.get("actual", {}).get("hhi"), "hhi_anterior": out.get("anterior", {}).get("hhi"),
                "top": [{"letra": k, "banco": nombre(k, producto), "share": s,
                         "delta_pp": (round(s - out["anterior"]["shares"].get(k, 0), 2) if "anterior" in out else None)}
                        for k, s in top]}
        return {"periodos": list(cuts.keys()), "heat": heat, "concentracion": conc,
                "nombres": {k: nombre(k, producto) for k in letras}}

    emisores = {p: issuer_views(p) for p in ("credito", "debito")}

    # ---------- Tablas de emisores
    last_cut, first_cut = fechas[-1], f"{y0}-10-01"
    emis_cr = []
    for k, ser in cf["credito"]["letras"].items():
        a, b = triple(ser, last_cut), triple(ser, first_cut)
        tot = sum(a)
        if tot == 0 and (sum(b) == 0 or (k not in banks and sum(b) < 20000)):
            continue  # emisores que ya no existen y eran marginales
        info = banks.get(k)
        emis_cr.append({
            "letra": k, "banco": nombre(k, "credito"),
            "confianza": info["confianza"] if info else ("Baja" if k == "B" else "—"),
            "evidencia": info["evidencia"] if info else rib["sin_identificar"].get(k, ""),
            "visa": a[0], "mc": a[1], "otras": a[2], "total": tot, "total_inicial": sum(b),
            "pct_visa": round(a[0] / tot * 100, 1) if tot else None,
            "saldo_pct_ult": round(info["saldo"][2] / rib["totales_saldo_mdp"]["2025"] * 100, 1) if info else None})
    emis_cr.sort(key=lambda r: -(r["total"] or r["total_inicial"]))
    emis_db = []
    for k, ser in cf["debito"]["letras"].items():
        v, m, o = triple(ser, last_cut)
        t = v + m + o
        if t > 0:
            emis_db.append({"letra": k, "banco": nombre(k, "debito"), "visa": v, "mc": m, "otras": o,
                            "total": t, "pct_visa": round(v / t * 100, 1)})
    emis_db.sort(key=lambda r: -r["total"])

    out = {
        "meta": {"corte_tarjetas": qlabel(last_cut), "corte_tarjetas_inicial": qlabel(first_cut),
                 "corte_facturacion": f"{MESES[int(last_bill[5:7]) - 1]}-{last_bill[:4]}",
                 "ultimo_anio_completo": ultimo, "primer_anio": first,
                 "empalme": {p: round(f, 4) for p, f in bill.factor.items()},
                 "descargado": cf.get("descargado", "")},
        "anual": anual, "trimestral": trimestral, "tarjetas_hist": hist, "facturacion_mensual": mensual,
        "contribucion_credito": contrib, "emisores": emisores,
        "emisores_credito": emis_cr, "emisores_debito": emis_db,
    }
    with open(os.path.join(HERE, "output.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    for r in anual:
        print(r["periodo"], r["corte_tarjetas"], "cr V/M", r["cr_visa_saldo"], r["cr_mc_saldo"],
              "| db", r["db_visa"], r["db_mc"], "| tot", r["tot_visa_saldo"], r["tot_mc_saldo"])
    print(f"trimestral: {len(trimestral)} filas · histórico tarjetas: {len(hist)} · meses: {len(mensual)}")


if __name__ == "__main__":
    main()
