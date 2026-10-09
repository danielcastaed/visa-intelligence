#!/usr/bin/env python3
"""Genera docs/resumen.html: tres relatos animados (histórico, año a la fecha, mes)
a partir de los datos embebidos en el dashboard (RAW_TOTAL / RAW_CREDITO / RAW_DEBITO).

Todos los textos salen de plantillas con las cifras del período: sin IA, sin
llamadas externas, siempre la misma redacción para los mismos datos.

Uso:
    python report/generate_resumen.py [dashboard.html] [salida.html]
    (por defecto: docs/index.html -> docs/resumen.html)
"""
import calendar
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).resolve().parent / "resumen_template.html"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
NUMEROS = {4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 8: "ocho"}
MES3 = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

BANCOS = {
    "BANCOLOMBIA S.A.": "Bancolombia",
    "NEQUI (Bancolombia)": "Nequi",
    "BANCO DAVIVIENDA S.A.": "Davivienda",
    "BANCO DE BOGOTA S. A.": "Banco de Bogotá",
    "BANCO POPULAR S.A.": "Banco Popular",
    "BANCO BILBAO VIZCAYA ARGENTARIA COLOMBIA S.A. BBVA COLOMBIA": "BBVA",
    "SCOTIABANK COLPATRIA S.A.": "Scotiabank Colpatria",
    "BANCO DE OCCIDENTE S.A.": "Banco de Occidente",
    "BANCO COMERCIAL AV VILLAS S.A.": "AV Villas",
    "BANCO CAJA SOCIAL S.A.": "Banco Caja Social",
    "BANCO AGRARIO DE COLOMBIA S.A.": "Banco Agrario",
    "CITIBANK - COLOMBIA S.A.": "Citibank",
    "ITAU CORPBANCA COLOMBIA S.A.": "Itaú",
    "BANCO FALABELLA S.A.": "Banco Falabella",
    "BANCO GNB SUDAMERIS S.A.": "GNB Sudameris",
    "NU O NU FINANCIERA": "Nu",
    "TUYA S.A C.F": "Tuya",
}


def banco(ent):
    if ent in BANCOS:
        return BANCOS[ent]
    n = re.sub(r"\b(S\.? ?A\.?|C\.? ?F\.?|COMPAÑÍA DE FINANCIAMIENTO)\b", "", ent)
    return re.sub(r"\s+", " ", n).strip(" .\"'-").title()


# ── Formato ─────────────────────────────────────────────────────────────────
def num(x, d=1):
    return f"{x:.{d}f}"


def sgn(x, d=2):
    s = f"{abs(x):.{d}f}"
    if float(s) == 0:
        return s
    return ("+" if x > 0 else "−") + s


def mes_largo(m):
    return f"{MESES[int(m[5:7]) - 1]} {m[:4]}"


def mes_corto(m):
    return f"{MES3[int(m[5:7]) - 1]}-{m[2:4]}"


def lista(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


# ── Datos ───────────────────────────────────────────────────────────────────
def cargar(path):
    h = Path(path).read_text(encoding="utf-8")
    out = {}
    for nombre in ("RAW_TOTAL", "RAW_CREDITO", "RAW_DEBITO"):
        m = re.search(r"const " + nombre + r"\s*=\s*(\[.*?\]);\n", h, re.S)
        if not m:
            sys.exit(f"No encontré {nombre} en {path}")
        out[nombre] = json.loads(m.group(1))
    return out


class Datos:
    """Agregados por (alcance, mes, franquicia). Alcance: T total, C crédito, D débito."""

    def __init__(self, raw):
        self.fac = collections.defaultdict(float)
        self.vig = collections.defaultdict(float)
        self.banco_visa = collections.defaultdict(float)   # (mes, entidad) -> facturación Visa
        for esc, clave in (("T", "RAW_TOTAL"), ("C", "RAW_CREDITO"), ("D", "RAW_DEBITO")):
            for r in raw[clave]:
                f = r["FRANQUICIA"] if r["FRANQUICIA"] in ("VISA", "MASTERCARD") else "OTRAS"
                v = (r.get("MTO_COMPRAS_NAL") or 0) + (r.get("MTO_COMPRAS_EXT") or 0)
                self.fac[(esc, r["MES"], f)] += v
                self.vig[(esc, r["MES"], f)] += r.get("VIGENTES_FECHA_CORTE") or 0
                if esc == "T" and f == "VISA":
                    self.banco_visa[(r["MES"], r["ENTIDAD"])] += v
        self.meses = sorted({k[1] for k in self.fac})
        self.entidades = sorted({k[1] for k in self.banco_visa})

    def monto(self, meses, esc="T", f=None):
        fs = (f,) if f else ("VISA", "MASTERCARD", "OTRAS")
        return sum(self.fac[(esc, m, x)] for m in meses for x in fs)

    def cuota(self, meses, esc="T"):
        t = self.monto(meses, esc)
        if not t:
            return {"VISA": 0.0, "MASTERCARD": 0.0, "OTRAS": 0.0}
        return {f: 100 * self.monto(meses, esc, f) / t for f in ("VISA", "MASTERCARD", "OTRAS")}

    def vigentes(self, mes, esc="T", f=None):
        fs = (f,) if f else ("VISA", "MASTERCARD", "OTRAS")
        return sum(self.vig[(esc, mes, x)] for x in fs)

    def aportes(self, meses_a, meses_b):
        """Aporte de cada banco al cambio de cuota de Visa (pp) entre dos períodos."""
        ta, tb = self.monto(meses_a), self.monto(meses_b)
        res = []
        for e in self.entidades:
            va = sum(self.banco_visa[(m, e)] for m in meses_a) / ta
            vb = sum(self.banco_visa[(m, e)] for m in meses_b) / tb
            res.append((banco(e), 100 * (vb - va)))
        agg = collections.defaultdict(float)
        for n, v in res:
            agg[n] += v
        return sorted(agg.items(), key=lambda x: x[1])


def tendencia(d, umbral=0.10):
    """-1, 0, 1 según cambio de cuota (pp) frente a un umbral de 'sin cambio'."""
    return 0 if abs(d) < umbral else (1 if d > 0 else -1)


def top_aportes(ap, n=3, minimo=0.01):
    bajan = [a for a in ap if a[1] <= -minimo][:n]
    suben = [a for a in reversed(ap) if a[1] >= minimo][:n]
    return suben, bajan


def escena_aportes(eyebrow, titulo, sub, suben, bajan):
    items = [{"name": n, "val": round(v, 4)} for n, v in suben]
    if suben and bajan:
        items.append(None)
    items += [{"name": n, "val": round(v, 4)} for n, v in sorted(bajan, key=lambda x: x[1], reverse=True)]
    mx = max([abs(i["val"]) for i in items if i] or [0.1])
    return {"type": "contrib", "eyebrow": eyebrow, "title": titulo, "sub": sub,
            "items": items, "max": round(mx * 1.15, 4), "dur": 7000}


def frase_aportes(suben, bajan, verbo_sube, verbo_baja):
    out = []
    if suben:
        out.append(f"{verbo_sube} <b>{lista(f'{n} ({sgn(v)} pp)' for n, v in suben)}</b>.")
    if bajan:
        out.append(f"{verbo_baja} <b>{lista(f'{n} ({sgn(v)} pp)' for n, v in bajan)}</b>.")
    return out


def barra(label, right, cuota):
    return {"label": label, "right": right,
            "segs": [{"k": "v", "val": round(cuota["VISA"], 2)},
                     {"k": "m", "val": round(cuota["MASTERCARD"], 2)},
                     {"k": "o", "val": round(cuota["OTRAS"], 2)}]}


def crecimiento(d, ma, mb, esc="T"):
    def g(f=None):
        a, b = d.monto(ma, esc, f), d.monto(mb, esc, f)
        return 100 * (b / a - 1) if a else 0.0
    return g("VISA"), g("MASTERCARD"), g()


def comparativo(visa, mc, mkt):
    if abs(visa - mc) < 0.3:
        return "en línea con Mastercard"
    return "menos que Mastercard" if visa < mc else "más que Mastercard"


# ═══ Relato 3: el mes ════════════════════════════════════════════════════════
def relato_mes(d):
    last, prev = d.meses[-1], d.meses[-2]
    yo = f"{int(last[:4]) - 1}{last[4:]}"
    cu, cp = d.cuota([last]), d.cuota([prev])
    dv = cu["VISA"] - cp["VISA"]
    t = tendencia(dv)
    gv, gm, gt = crecimiento(d, [prev], [last])
    ml, mp = mes_largo(last), mes_largo(prev)

    titulo = {0: "Visa casi no se movió: mantiene su cuota en el mercado",
              1: f"Visa ganó cuota en {MESES[int(last[5:7]) - 1]}",
              -1: f"Visa cedió cuota en {MESES[int(last[5:7]) - 1]}"}[t]
    suben, bajan = top_aportes(d.aportes([prev], [last]))
    serie = d.meses[-13:]
    sv = [round(d.cuota([m])["VISA"], 2) for m in serie]

    items = [
        f"La cuota de Visa {'quedó prácticamente igual' if t == 0 else 'subió' if t > 0 else 'bajó'} "
        f"(<b>{num(cu['VISA'], 2)}%</b>, {sgn(dv)} pp): su facturación creció <b>{sgn(gv)}%</b>, "
        f"{comparativo(gv, gm, gt)} ({sgn(gm)}%) y {'por debajo' if gv < gt - 0.15 else 'cerca' if abs(gv - gt) <= 0.15 else 'por encima'} "
        f"del mercado ({sgn(gt)}%)."]
    if yo in d.meses:
        cy = d.cuota([yo])
        items.append(f"Frente a {mes_largo(yo)}, la cuota de Visa {'subió' if cu['VISA'] > cy['VISA'] else 'bajó'} "
                     f"{num(abs(cu['VISA'] - cy['VISA']), 2)} pp ({num(cy['VISA'], 1)}% → {num(cu['VISA'], 1)}%).")
    items += frase_aportes(suben, bajan, "Sumaron cuota para Visa", "Restaron")
    cc, cd = d.cuota([last], "C")["VISA"], d.cuota([last], "D")["VISA"]
    items.append(f"Por producto: Visa tiene <b>{num(cc, 1)}%</b> en crédito (dato SFC) y "
                 f"<b>{num(cd, 1)}%</b> en débito (estimado).")
    lo, hi = min(sv), max(sv)
    pos = ("es el máximo del período" if sv[-1] == hi else "es el mínimo del período" if sv[-1] == lo
           else "está dentro del rango habitual")
    items.append(f"En los últimos {len(serie)} meses la cuota oscila entre {num(lo, 1)}% y {num(hi, 1)}%; "
                 f"el dato de {MESES[int(last[5:7]) - 1]} {pos}.")

    chip_cls = "flat" if t == 0 else "pos" if t > 0 else "neg"
    return {
        "id": "mes", "tab": "Mes", "label": ml,
        "scenes": [
            {"type": "hero", "eyebrow": f"Resumen del mes · {ml}", "title": titulo,
             "num": {"from": round(cp["VISA"], 2), "to": round(cu["VISA"], 2), "decimals": 2, "suffix": "%"},
             "chip": {"text": f"{sgn(dv)} pp vs {MESES[int(prev[5:7]) - 1]}", "cls": chip_cls},
             "sub": "Participación de Visa en la facturación total de tarjetas en Colombia (crédito + débito).",
             "dur": 5200},
            {"type": "stack", "eyebrow": "Así se reparte el mercado", "title": f"Visa vs. Mastercard, {MESES[int(prev[5:7]) - 1]} → {MESES[int(last[5:7]) - 1]}",
             "rows": [barra(mp, f"${num(d.monto([prev]) / 1e12, 1)} billones facturados", cp),
                      barra(ml, f"${num(d.monto([last]) / 1e12, 1)} billones facturados", cu)],
             "tiles": [{"value": sgn(gv) + "%", "label": f"Facturación Visa vs. {MESES[int(prev[5:7]) - 1]}"},
                       {"value": sgn(gm) + "%", "label": f"Facturación Mastercard vs. {MESES[int(prev[5:7]) - 1]}"},
                       {"value": sgn(gt) + "%", "label": f"Mercado total vs. {MESES[int(prev[5:7]) - 1]}"}],
             "dur": 6200},
            escena_aportes("Quién movió la aguja", "Aporte de cada banco al cambio de cuota de Visa",
                           "Puntos porcentuales (pp) de cuota de mercado. Los aportes de todos los bancos suman el cambio total.",
                           suben, bajan),
            {"type": "line", "eyebrow": "Contexto", "title": f"Cuota de Visa, últimos {len(serie)} meses",
             "labels": [mes_corto(m).replace("-", " ") for m in serie],
             "series": [{"name": "Visa", "color": "visa", "values": sv}], "fmt": "%", "dur": 5600},
            {"type": "read", "eyebrow": "Lectura del mes", "title": "Qué pasó y qué mirar", "items": items,
             "note": "Cifras reportadas por las entidades a la SFC. La franquicia en débito es estimada (la SFC no la reporta).",
             "dur": 9000},
        ]}


# ═══ Relato 2: año a la fecha ════════════════════════════════════════════════
def relato_ytd(d):
    last = d.meses[-1]
    y, m_last = int(last[:4]), int(last[5:7])
    cy = [f"{y}-{i:02d}" for i in range(1, m_last + 1)]
    py = [f"{y - 1}-{i:02d}" for i in range(1, m_last + 1)]
    py = [m for m in py if m in d.meses]
    rango = f"{MES3[0]}–{MES3[m_last - 1]}" if m_last > 1 else MES3[0]
    ec, ep = f"{rango} {y}", f"{rango} {y - 1}"
    qc, qp = d.cuota(cy), d.cuota(py)
    dv = qc["VISA"] - qp["VISA"]
    t = tendencia(dv)
    gv, gm, gt = crecimiento(d, py, cy)
    titulo = {0: f"En {y}, Visa sostiene su cuota frente a {y - 1}",
              1: f"En {y}, Visa gana cuota frente a {y - 1}",
              -1: f"En {y}, Visa cede cuota frente a {y - 1}"}[t]
    suben, bajan = top_aportes(d.aportes(py, cy))

    # Cuota Visa mensual, año en curso vs anterior
    etq = [MES3[i] for i in range(m_last)]
    s_cy = [round(d.cuota([m])["VISA"], 2) for m in cy]
    s_py = [round(d.cuota([m])["VISA"], 2) for m in py]
    mejor = max(range(m_last), key=lambda i: s_cy[i])

    # Por producto
    cc_c, cc_p = d.cuota(cy, "C"), d.cuota(py, "C")
    dd_c, dd_p = d.cuota(cy, "D"), d.cuota(py, "D")
    gc = crecimiento(d, py, cy, "C")[2]
    gd = crecimiento(d, py, cy, "D")[2]
    mix_c = 100 * d.monto(cy, "D") / d.monto(cy)
    mix_p = 100 * d.monto(py, "D") / d.monto(py)

    items = [
        f"La cuota de Visa en {ec} es <b>{num(qc['VISA'], 1)}%</b> ({sgn(dv)} pp vs. {ep}); "
        f"Mastercard está en {num(qc['MASTERCARD'], 1)}% ({sgn(qc['MASTERCARD'] - qp['MASTERCARD'])} pp).",
        f"El mercado facturó <b>${num(d.monto(cy) / 1e12, 1)} billones</b> ({sgn(gt, 1)}% vs. {ep}); "
        f"Visa creció {sgn(gv, 1)}%, {comparativo(gv, gm, gt)} ({sgn(gm, 1)}%).",
        f"En <b>crédito</b> (dato SFC) Visa pasa de {num(cc_p['VISA'], 1)}% a {num(cc_c['VISA'], 1)}% ({sgn(cc_c['VISA'] - cc_p['VISA'], 1)} pp); "
        f"en <b>débito</b> (estimado), de {num(dd_p['VISA'], 1)}% a {num(dd_c['VISA'], 1)}% ({sgn(dd_c['VISA'] - dd_p['VISA'], 1)} pp).",
    ] + frase_aportes(suben, bajan, "Más cuota para Visa vino de", "Restaron")
    items.append(f"El débito pesa {num(mix_c, 1)}% de la facturación ({'+' if mix_c >= mix_p else '−'}{num(abs(mix_c - mix_p), 1)} pp vs. {ep}); "
                 f"el mejor mes de Visa en {y} fue {MESES[mejor]} ({num(s_cy[mejor], 1)}%).")

    return {
        "id": "ytd", "tab": "Año a la fecha", "label": ec,
        "scenes": [
            {"type": "hero", "eyebrow": f"Año a la fecha · {ec}", "title": titulo,
             "num": {"from": round(qp["VISA"], 2), "to": round(qc["VISA"], 2), "decimals": 2, "suffix": "%"},
             "chip": {"text": f"{sgn(dv)} pp vs {ep}", "cls": "flat" if t == 0 else "pos" if t > 0 else "neg"},
             "sub": f"Participación de Visa en la facturación acumulada de tarjetas, {ec} frente a {ep}.",
             "dur": 5200},
            {"type": "stack", "eyebrow": "Así se reparte el mercado", "title": f"Visa vs. Mastercard, {ep} vs. {ec}",
             "rows": [barra(ep, f"${num(d.monto(py) / 1e12, 1)} billones facturados", qp),
                      barra(ec, f"${num(d.monto(cy) / 1e12, 1)} billones facturados", qc)],
             "tiles": [{"value": sgn(gv, 1) + "%", "label": f"Facturación Visa vs. {ep}"},
                       {"value": sgn(gm, 1) + "%", "label": f"Facturación Mastercard vs. {ep}"},
                       {"value": sgn(gt, 1) + "%", "label": f"Mercado total vs. {ep}"}],
             "dur": 6200},
            {"type": "line", "eyebrow": "Mes a mes", "title": f"Cuota de Visa por mes: {y} vs. {y - 1}",
             "labels": etq,
             "series": [{"name": str(y - 1), "color": "muted", "values": s_py, "dash": True},
                        {"name": str(y), "color": "visa", "values": s_cy}], "fmt": "%", "dur": 6200},
            {"type": "stack", "eyebrow": "Por producto", "title": f"Crédito vs. débito, {ec}",
             "rows": [barra(f"Crédito · {ec}", f"{sgn(gc, 1)}% facturación vs. {ep}", cc_c),
                      barra(f"Débito (estimado) · {ec}", f"{sgn(gd, 1)}% facturación vs. {ep}", dd_c)],
             "tiles": [{"value": num(cc_c["VISA"], 1) + "%", "label": f"Visa en crédito ({sgn(cc_c['VISA'] - cc_p['VISA'], 1)} pp)"},
                       {"value": num(dd_c["VISA"], 1) + "%", "label": f"Visa en débito ({sgn(dd_c['VISA'] - dd_p['VISA'], 1)} pp)"},
                       {"value": num(mix_c, 1) + "%", "label": f"Peso del débito ({sgn(mix_c - mix_p, 1)} pp)"}],
             "dur": 6200},
            escena_aportes("Quién movió la aguja", f"Aporte de cada banco al cambio de cuota de Visa, {ec} vs. {ep}",
                           "Puntos porcentuales (pp) de cuota de mercado. Los aportes de todos los bancos suman el cambio total.",
                           suben, bajan),
            {"type": "read", "eyebrow": "Lectura del año", "title": f"Qué ha pasado en {y}", "items": items,
             "note": "Cifras reportadas por las entidades a la SFC. La franquicia en débito es estimada (la SFC no la reporta).",
             "dur": 10000},
        ]}


# ═══ Relato 1: la historia ═══════════════════════════════════════════════════
def relato_historia(d):
    last = d.meses[-1]
    años = sorted({m[:4] for m in d.meses})
    completos = [a for a in años if all(f"{a}-{i:02d}" in d.meses for i in range(1, 13))]
    ltm = d.meses[-12:]
    incluir_ltm = ltm[-1][5:7] != "12"
    etq = completos + ([f"12M {mes_corto(last)}"] if incluir_ltm else [])
    per = [[f"{a}-{i:02d}" for i in range(1, 13)] for a in completos] + ([ltm] if incluir_ltm else [])

    tot = [d.monto(p) / 1e12 for p in per]
    veces = tot[-1] / tot[0]
    # Años transcurridos entre el primer año completo y el último punto (12M o año completo)
    n = (len(completos) - 1) + (int(last[5:7]) / 12 if incluir_ltm else 0)
    cagr = 100 * ((tot[-1] / tot[0]) ** (1 / n) - 1)
    caidas = [(etq[i], 100 * (tot[i] / tot[i - 1] - 1)) for i in range(1, len(tot)) if tot[i] < tot[i - 1]]

    cuotas = [d.cuota(p) for p in per]
    vv = [round(c["VISA"], 2) for c in cuotas]
    mm = [round(c["MASTERCARD"], 2) for c in cuotas]
    i_pico = max(range(len(vv)), key=lambda i: vv[i])
    i_valle = min(range(len(vv)), key=lambda i: vv[i])

    deb = [100 * d.monto(p, "D") / d.monto(p) for p in per]
    cred = [100 - x for x in deb]
    i_deb50 = next((i for i, x in enumerate(deb) if x > 50), None)

    vc = [round(d.cuota(p, "C")["VISA"], 2) for p in per]
    mc_c = [round(d.cuota(p, "C")["MASTERCARD"], 2) for p in per]
    vd = [round(d.cuota(p, "D")["VISA"], 2) for p in per]

    def fin(a):
        return f"{a}-12"
    cortes = [fin(a) for a in completos] + ([last] if incluir_ltm else [])
    vig_t = [d.vigentes(m) / 1e6 for m in cortes]
    vig_c = [d.vigentes(m, "C") / 1e6 for m in cortes]
    vig_d = [d.vigentes(m, "D") / 1e6 for m in cortes]
    vig_visa = 100 * d.vigentes(cortes[-1], "T", "VISA") / d.vigentes(cortes[-1])

    # Apertura por franquicia (facturación en billones y parque en millones)
    fac_v = [d.monto(p, "T", "VISA") / 1e12 for p in per]
    fac_m = [d.monto(p, "T", "MASTERCARD") / 1e12 for p in per]
    fac_o = [t - v - m for t, v, m in zip(tot, fac_v, fac_m)]
    vig_v = [d.vigentes(m, "T", "VISA") / 1e6 for m in cortes]
    vig_m = [d.vigentes(m, "T", "MASTERCARD") / 1e6 for m in cortes]
    vig_o = [t - v - m for t, v, m in zip(vig_t, vig_v, vig_m)]

    def ficha(nombre, serie, fmt, extra=""):
        a, b = serie[0], serie[-1]
        anual = 100 * ((b / a) ** (1 / n) - 1)
        return {"value": fmt.format(b),
                "label": f"{nombre} · ×{num(b / a, 1)} desde {etq[0]} ({num(anual, 1)}% anual){extra}"}

    primero, ultimo = etq[0], etq[-1]
    pesos = f"de ${num(tot[0], 0)} billones en {primero} a ${num(tot[-1], 0)} billones en {ultimo.replace('12M', 'los 12 meses a')}"

    # Titulares dinámicos
    dv_pico = vv[-1] - vv[i_pico]
    if i_pico == len(vv) - 1:
        t_ms = f"Visa está en su nivel más alto: {num(vv[-1], 1)}% del mercado"
    elif abs(dv_pico) < 0.3:
        t_ms = f"La cuota de Visa ({num(vv[-1], 1)}%) se mantiene en su nivel máximo histórico"
    else:
        t_ms = (f"Visa pasó de {num(vv[i_pico], 1)}% en {etq[i_pico]} a {num(vv[-1], 1)}%: "
                f"{'perdió' if dv_pico < 0 else 'ganó'} {num(abs(dv_pico), 1)} pp")
    estable = abs(vv[-1] - vv[-2]) < 0.6 and abs(vv[-2] - vv[-3]) < 1.0 if len(vv) >= 3 else False
    sub_ms = (f"Mastercard subió de {num(mm[0], 1)}% a {num(mm[-1], 1)}%"
              + ("; en los últimos años la cuota de Visa se estabiliza." if estable else "."))

    dc = vc[-1] - vc[0]
    lider_c = "Visa lidera el crédito" if vc[-1] > mc_c[-1] else "Mastercard lidera el crédito"
    t_prod = (f"{lider_c}: {num(vc[-1], 1)}% de la facturación en crédito; "
              f"en débito (estimado) Visa tiene {num(vd[-1], 1)}%")

    items = [
        f"El mercado se multiplicó por <b>{num(veces, 1)}</b> en pesos corrientes ({pesos}), "
        f"un crecimiento anual compuesto de {num(cagr, 1)}%."
        + (f" La única caída fue {caidas[0][0]} ({sgn(caidas[0][1], 0)}%)." if len(caidas) == 1 else ""),
        f"Visa facturó <b>×{num(fac_v[-1] / fac_v[0], 1)}</b> desde {primero} (${num(fac_v[0], 0)} → ${num(fac_v[-1], 0)} billones) y Mastercard "
        f"<b>×{num(fac_m[-1] / fac_m[0], 1)}</b> (${num(fac_m[0], 0)} → ${num(fac_m[-1], 0)} billones): "
        f"{'Mastercard creció más rápido' if fac_m[-1] / fac_m[0] > fac_v[-1] / fac_v[0] else 'Visa creció más rápido'}, de ahí el cambio de cuota.",
        f"Visa tuvo su mejor momento en <b>{etq[i_pico]}</b> ({num(vv[i_pico], 1)}%) y hoy está en <b>{num(vv[-1], 1)}%</b>; "
        f"Mastercard pasó de {num(mm[0], 1)}% a {num(mm[-1], 1)}%.",
        f"El <b>crédito</b>, con dato reportado por la SFC, es el terreno sólido de Visa: {num(vc[0], 1)}% en {primero} → {num(vc[-1], 1)}% hoy "
        f"({sgn(dc, 1)} pp), frente a {num(mc_c[-1], 1)}% de Mastercard.",
        f"El <b>débito</b> pasó de {num(deb[0], 1)}% a {num(deb[-1], 1)}% de la facturación"
        + (f" y superó al crédito en {etq[i_deb50]}" if i_deb50 is not None and i_deb50 > 0 else "")
        + f"; ahí la cuota estimada de Visa baja de {num(vd[0], 1)}% a {num(vd[-1], 1)}%, y explica buena parte de la caída de la cuota total.",
        f"Las tarjetas vigentes pasaron de <b>{num(vig_t[0], 1)}</b> a <b>{num(vig_t[-1], 1)} millones</b> "
        f"(crédito {num(vig_c[0], 1)} → {num(vig_c[-1], 1)} M; débito {num(vig_d[0], 1)} → {num(vig_d[-1], 1)} M); Visa tiene {num(vig_visa, 0)}% del parque ({num(vig_v[-1], 1)} M de tarjetas frente a {num(vig_m[-1], 1)} M de Mastercard).",
    ]

    anot = [{"i": etq.index(a), "text": "pandemia" if a == "2020" else "caída"} for a, _ in caidas]
    return {
        "id": "historia", "tab": "Historia", "label": f"{primero}–{mes_corto(last)}",
        "scenes": [
            {"type": "hero", "eyebrow": f"La historia · {primero}–{mes_corto(last)}",
             "title": f"Desde {primero}, la facturación con tarjetas en Colombia se multiplicó por {num(veces, 1)}",
             "num": {"from": 1.0, "to": round(veces, 1), "decimals": 1, "suffix": "×"},
             "chip": {"text": f"{num(cagr, 1)}% anual compuesto", "cls": "pos"},
             "sub": pesos[0].upper() + pesos[1:] + " (pesos corrientes, sin descontar inflación).", "dur": 6000},
            {"type": "stackcols", "mode": "abs", "eyebrow": "Crecimiento",
             "title": "Facturación anual con tarjetas (billones de pesos), por franquicia",
             "sub": "Crédito + débito, nacional y exterior. La barra final son los últimos 12 meses. En débito la franquicia es estimada.",
             "labels": etq, "fmt": "{:.0f}", "annot": anot,
             "series": [{"name": "Visa", "color": "visa", "values": [round(x, 1) for x in fac_v]},
                        {"name": "Mastercard", "color": "mc", "values": [round(x, 1) for x in fac_m]},
                        {"name": "Otras", "color": "otras", "values": [round(x, 1) for x in fac_o]}],
             "tiles": [ficha("Mercado total", tot, "${:.0f} bill."), ficha("Visa", fac_v, "${:.0f} bill."),
                       ficha("Mastercard", fac_m, "${:.0f} bill.")], "dur": 8000},
            {"type": "line", "eyebrow": "Cuota de mercado", "title": t_ms, "sub": sub_ms,
             "labels": etq, "series": [{"name": "Visa", "color": "visa", "values": vv},
                                       {"name": "Mastercard", "color": "mc", "values": mm}], "fmt": "%", "dur": 7000},
            {"type": "stackcols", "eyebrow": "Mezcla de productos", "title": f"El débito pasó de {num(deb[0], 0)}% a {num(deb[-1], 0)}% de la facturación",
             "sub": "Participación de cada producto en la facturación total.", "labels": etq,
             "series": [{"name": "Crédito", "color": "credito", "values": [round(x, 1) for x in cred]},
                        {"name": "Débito", "color": "debito", "values": [round(x, 1) for x in deb]}], "dur": 6500},
            {"type": "line", "eyebrow": "Cuota de Visa por producto", "title": t_prod,
             "sub": "El crédito es dato directo de la SFC. La franquicia del débito se infiere (la SFC no la reporta) y desde 2025 Nequi se calibra con cifras reales, lo que genera un quiebre: lectura indicativa.",
             "labels": etq, "series": [{"name": "Visa en crédito (SFC)", "color": "credito", "values": vc},
                                       {"name": "Visa en débito (estimado)", "color": "debito", "values": vd, "dash": True}],
             "fmt": "%", "dur": 7500},
            {"type": "stackcols", "mode": "abs", "eyebrow": "Parque de tarjetas",
             "title": "Tarjetas vigentes (millones), crédito + débito, por franquicia",
             "sub": "Stock al cierre de cada año; la barra final es el último mes disponible. En débito la franquicia es estimada.",
             "labels": etq, "fmt": "{:.0f}", "annot": [],
             "series": [{"name": "Visa", "color": "visa", "values": [round(x, 1) for x in vig_v]},
                        {"name": "Mastercard", "color": "mc", "values": [round(x, 1) for x in vig_m]},
                        {"name": "Otras", "color": "otras", "values": [round(x, 1) for x in vig_o]}],
             "tiles": [ficha("Parque total", vig_t, "{:.1f} M"), ficha("Visa", vig_v, "{:.1f} M"),
                       ficha("Mastercard", vig_m, "{:.1f} M")], "dur": 8000},
            {"type": "read", "eyebrow": "Mensajes clave", "title": f"La historia en {NUMEROS.get(len(items), len(items))} ideas", "items": items,
             "note": "Pesos corrientes. Crédito: dato SFC. Débito: franquicia estimada por proxy (la SFC no la reporta); lectura indicativa.",
             "dur": 12000},
        ]}


# ═══ Salida ═════════════════════════════════════════════════════════════════
def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "index.html"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "resumen.html"
    d = Datos(cargar(src))
    last = d.meses[-1]
    y, m = int(last[:4]), int(last[5:7])
    corte = f"{calendar.monthrange(y, m)[1]}-{MES3[m - 1]}-{y}"
    data = {"corte": corte, "reportes": [relato_historia(d), relato_ytd(d), relato_mes(d)]}
    html = TEMPLATE.read_text(encoding="utf-8")
    assert html.count("/*__DATA__*/null") == 1
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", payload)
    out.write_text(html, encoding="utf-8")
    print(f"✅ {out} ({len(html) // 1024} KB) · corte {corte}")


if __name__ == "__main__":
    main()
