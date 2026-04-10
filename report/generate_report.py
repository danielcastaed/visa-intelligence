"""
generate_report.py — Visa Market Intelligence
Genera reporte mensual con snapshot de Crédito, Débito y Total.
El adjunto es el dashboard HTML completo (generado por el notebook).
"""

import requests, sys, os
import pandas as pd
from io import StringIO
from datetime import datetime
from collections import defaultdict

SFC_URL = (
    "https://www.datos.gov.co/api/v3/views/h2jg-r3zg/export.csv"
    "?accessType=DOWNLOAD&app_token=bHWsGtRFRP9x8Hl8lYivqM1hQ"
)
FRANQS_CRED = ["VISA", "MASTERCARD", "AMERICAN EXPRESS", "DINERS"]
FRANQS_DEB  = ["VISA", "MASTERCARD"]
VISA_COLOR  = "#1A1F71"
MC_COLOR    = "#CC2200"

EXCLUIR_REDES = [
    "REDEBAN S.A.",
    "MASTERCARD COLOMBIA ADMINISTRADORA S.A.",
    "CREDIBANCO S.A. PUDIENDO SIN PERDER SU NATURALEZA UTILIZAR LA SIGLA CREDIBANCO",
    "VISA COLOMBIA SUPPORT SERVICES SOCIEDAD ANONIMA",
    "VISIONAMOS SISTEMA DE PAGO COOPERATIVO",
]

TII_DESCRIPS = [
    "Ingresos por Tarifa Interbancaria de Intercambio - TII por Tarjeta Débito Visa",
    "Ingresos por Tarifa Interbancaria de Intercambio - TII por Tarjeta Débito Electrón",
    "Ingresos por Tarifa Interbancaria de Intercambio - TII por Tarjeta Débito Maestro",
    "Ingresos por Tarifa Interbancaria de Intercambio - TII por Tarjeta Master Débito",
]

# ── Descarga ──────────────────────────────────────────────────────────────────
def download_data():
    print("Descargando datos SFC...")
    r = requests.get(SFC_URL, timeout=180)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), low_memory=False)
    df["indicador"] = (
        df["TOTAL_TARJETAS"].astype(str)
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )
    df["MES_DT"] = pd.to_datetime(df["FECHACORTE"], format="%d/%m/%Y", dayfirst=True, errors="coerce")
    df = df.dropna(subset=["MES_DT"])
    df["MES"] = df["MES_DT"].dt.strftime("%Y-%m")
    df["NOMBRE_UCA"] = df["NOMBRE_UCA"].replace("CREDIBANCO-VISA", "VISA")
    print(f"  {len(df):,} registros · {df['MES'].min()} → {df['MES'].max()}")
    return df

# ── Construir master de CRÉDITO ───────────────────────────────────────────────
def build_credito(df):
    MAPA_TX = {
        "Monto de las transacciones por compras con tarjeta de crédito a nivel nacional": "MTO_NAL",
        "Monto de las transacciones por compras en el exterior con tarjeta de crédito":   "MTO_EXT",
        "Número de transacciones por compras a nivel nacional con tarjeta de crédito":    "NUM_NAL",
    }
    MAPA_VIG = {
        "Número total de tarjetas de crédito vigentes  a la fecha de corte": "VIGENTES",
    }
    def pivot(mapa, aggfunc):
        sub = df[df["DESCRIPCION"].isin(mapa)].copy()
        sub["DESCRIPCION"] = sub["DESCRIPCION"].map(mapa)
        p = sub.pivot_table(
            index=["MES","NOMBREENTIDAD","NOMBRE_UCA"],
            columns="DESCRIPCION", values="indicador", aggfunc=aggfunc
        ).reset_index()
        p.columns.name = None
        return p.rename(columns={"NOMBREENTIDAD":"ENTIDAD","NOMBRE_UCA":"FRANQUICIA"})

    tx  = pivot(MAPA_TX,  "sum")
    vig = pivot(MAPA_VIG, "max")
    m = tx.merge(vig, on=["MES","ENTIDAD","FRANQUICIA"], how="outer")
    for c in ["MTO_NAL","MTO_EXT","NUM_NAL","VIGENTES"]:
        if c not in m.columns: m[c] = 0
        m[c] = m[c].fillna(0)
    m["MTO_TOT"] = m["MTO_NAL"] + m["MTO_EXT"]
    m = m[m["FRANQUICIA"].isin(FRANQS_CRED)]
    return m

# ── Construir master de DÉBITO ────────────────────────────────────────────────
def build_debito(df):
    # Paso 1: monto compras por emisor
    monto = df[
        (df["DESCRIPCION"] == "Monto de transacciones por compras con tarjetas débito") &
        (~df["NOMBREENTIDAD"].isin(EXCLUIR_REDES))
    ].groupby(["MES","NOMBREENTIDAD"])["indicador"].sum().reset_index()
    monto.columns = ["MES","ENTIDAD","MONTO_TOTAL"]

    # Paso 2: TII por franquicia
    def franq_tii(desc):
        d = desc.upper()
        return "VISA" if ("ELECTR" in d or "DEBITO VISA" in d or "DÉBITO VISA" in d) else "MASTERCARD"

    tii = df[df["DESCRIPCION"].isin(TII_DESCRIPS)].copy()
    tii["FRANQUICIA"] = tii["DESCRIPCION"].apply(franq_tii)
    tii_grp = tii.groupby(["MES","NOMBREENTIDAD","FRANQUICIA"])["indicador"].sum().reset_index()
    tii_grp.columns = ["MES","ENTIDAD","FRANQUICIA","TII"]
    tii_tot = tii_grp.groupby(["MES","ENTIDAD"])["TII"].sum().reset_index().rename(columns={"TII":"TII_TOT"})
    tii_grp = tii_grp.merge(tii_tot, on=["MES","ENTIDAD"])
    tii_grp["PROP"] = tii_grp["TII"] / tii_grp["TII_TOT"].replace(0, 1)

    # Paso 3: regla de tres
    deb = tii_grp.merge(monto, on=["MES","ENTIDAD"], how="inner")
    deb["MTO_TOT"] = deb["PROP"] * deb["MONTO_TOTAL"]

    # Vigentes débito
    vig = df[
        df["DESCRIPCION"] == "Número total de tarjetas débito  vigentes  a la fecha de corte"
    ].groupby(["MES","NOMBREENTIDAD"])["indicador"].sum().reset_index()
    vig.columns = ["MES","ENTIDAD","VIGENTES_TOTAL"]
    deb = deb.merge(vig, on=["MES","ENTIDAD"], how="left")
    deb["VIGENTES"] = deb.get("VIGENTES_TOTAL", 0) * deb["PROP"]

    # Paso 4: Nequi separado
    banc = deb["ENTIDAD"].str.contains("BANCOLOMBIA", na=False)
    nequi = deb[banc & (deb["FRANQUICIA"]=="VISA")].copy()
    nequi["ENTIDAD"] = "NEQUI (Bancolombia)"
    banc_mc = deb[banc & (deb["FRANQUICIA"]=="MASTERCARD")].copy()
    otros = deb[~banc].copy()
    deb = pd.concat([nequi, banc_mc, otros], ignore_index=True)

    deb["MES"] = deb["MES"].astype(str).str[:7]
    deb["MTO_NAL"] = deb["MTO_TOT"]
    deb["MTO_EXT"] = 0
    deb["NUM_NAL"] = 0
    deb = deb[deb["FRANQUICIA"].isin(FRANQS_DEB)]
    return deb[["MES","ENTIDAD","FRANQUICIA","MTO_TOT","MTO_NAL","MTO_EXT","NUM_NAL","VIGENTES"]]

# ── Agregación ────────────────────────────────────────────────────────────────
def aggregate(df, franqs):
    agg = defaultdict(lambda: defaultdict(lambda: {
        "mto_tot":0,"mto_nal":0,"mto_ext":0,"num_nal":0,"vigentes":0,
    }))
    for _, r in df.iterrows():
        key = str(r["MES"])[:7]
        f   = r["FRANQUICIA"]
        if f not in franqs: continue
        d = agg[key][f]
        d["mto_tot"]  += r.get("MTO_TOT",  0) or 0
        d["mto_nal"]  += r.get("MTO_NAL",  0) or 0
        d["mto_ext"]  += r.get("MTO_EXT",  0) or 0
        d["num_nal"]  += r.get("NUM_NAL",  0) or 0
        d["vigentes"] += r.get("VIGENTES", 0) or 0
    periods = sorted(agg.keys())
    for p in periods:
        total = sum(agg[p][f]["mto_tot"] for f in franqs if f in agg[p])
        for f in agg[p]:
            agg[p][f]["ms"] = agg[p][f]["mto_tot"] / total if total > 0 else 0
    return dict(agg), periods

def find_prior(period, periods):
    if len(period) == 7:
        y, m = int(period[:4]), int(period[5:7])
        m -= 12
        if m <= 0: m += 12; y -= 1
        cand = f"{y}-{m:02d}"
    else:
        cand = str(int(period) - 1)
    return cand if cand in periods else periods[0]

# ── Formato ───────────────────────────────────────────────────────────────────
def fmt_cop(v):
    if v >= 1e12: return f"${v/1e12:.2f}B COP"
    if v >= 1e9:  return f"${v/1e9:.1f}MM COP"
    return f"${v/1e6:.0f}M COP"

def fmt_pct(v): return f"{'+'if v>0 else ''}{v:.1f}%"
def fmt_pp(v):  return f"{'+'if v>0 else ''}{v:.2f}pp"

def chip(val, fn):
    if val is None: return ""
    tc = "#15803D" if val>0 else ("#DC2626" if val<0 else "#94A3B8")
    bg = "#DCFCE7" if val>0 else ("#FEE2E2" if val<0 else "#F1F5F9")
    return (f'<span style="background:{bg};color:{tc};padding:2px 8px;'
            f'border-radius:20px;font-size:11px;font-weight:600">{fn(val)}</span>')

def _fmt_bank(raw):
    up = str(raw).upper()
    if "NEQUI"      in up: return "Nequi"
    if "BANCOLOMBIA" in up: return "Bancolombia"
    if "BOGOT"      in up: return "Banco de Bogotá"
    if "BBVA"       in up: return "BBVA Colombia"
    if "DAVIVIENDA" in up: return "Davivienda"
    if "CITIBANK"   in up: return "Citibank"
    if "GNB"        in up: return "GNB Sudameris"
    if "TUYA"       in up: return "Tuya"
    if "SCOTIABANK" in up or "COLPATRIA"  in up: return "Scotiabank Colpatria"
    if "FALABELLA"  in up: return "Falabella"
    if "OCCIDENTE"  in up: return "Occidente"
    if "AV VILLAS"  in up: return "Av Villas"
    if "ITAU"       in up: return "Itaú"
    if "JURISCOOP"  in up: return "Juriscoop"
    if "COOPCENTRAL" in up: return "Coopcentral"
    if "RAPPIPAY"   in up: return "RappiPay"
    if "BOLD"       in up: return "BOLD"
    if "LULO"       in up: return "Lulo Bank"
    if "POPULAR"    in up: return "Banco Popular"
    if "CAJA SOCIAL" in up: return "Caja Social"
    clean = str(raw).replace("BANCO ","").replace("S.A.","").replace("COLOMBIA","").strip()
    return clean.title()

# ── Componentes HTML ──────────────────────────────────────────────────────────
def section_header(title, subtitle=""):
    return (
        f'<div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;'
        f'text-transform:uppercase;margin:28px 0 10px">{title}</div>'
        + (f'<div style="font-size:11px;color:#CBD5E1;margin-bottom:10px">{subtitle}</div>' if subtitle else "")
    )

def snap_card(label, color, u, p, prior_label, show_ext=True):
    tku = u["mto_nal"]/u["num_nal"]/1000 if u.get("num_nal",0) > 0 else None
    tkp = p["mto_nal"]/p["num_nal"]/1000 if p.get("num_nal",0) > 0 else None
    rows = [
        ("Market Share",      f'{u["ms"]*100:.1f}%',
         chip((u["ms"]-p["ms"])*100 if p.get("ms") is not None else None, fmt_pp)),
        ("Facturación total", fmt_cop(u["mto_tot"]),
         chip((u["mto_tot"]/p["mto_tot"]-1)*100 if p.get("mto_tot") else None, fmt_pct)),
    ]
    if show_ext:
        rows += [
            ("Facturación nacional", fmt_cop(u["mto_nal"]),
             chip((u["mto_nal"]/p["mto_nal"]-1)*100 if p.get("mto_nal") else None, fmt_pct)),
            ("Facturación exterior", fmt_cop(u["mto_ext"]),
             chip((u["mto_ext"]/p["mto_ext"]-1)*100 if p.get("mto_ext") else None, fmt_pct)),
        ]
    else:
        rows.append(
            ("Facturación (nac+int)", fmt_cop(u["mto_nal"]),
             chip((u["mto_nal"]/p["mto_nal"]-1)*100 if p.get("mto_nal") else None, fmt_pct)),
        )
    rows += [
        ("Tarjetas vigentes", f'{int(u["vigentes"]):,}',
         chip((u["vigentes"]/p["vigentes"]-1)*100 if p.get("vigentes") else None, fmt_pct)),
    ]
    if show_ext and u.get("num_nal"):
        rows += [
            ("N° transacciones", f'{int(u["num_nal"]):,}',
             chip((u["num_nal"]/p["num_nal"]-1)*100 if p.get("num_nal") else None, fmt_pct)),
            ("Ticket promedio", f'${tku:.0f}K' if tku else "—",
             chip((tku/tkp-1)*100 if tku and tkp else None, fmt_pct)),
        ]
    trs = "".join(
        f'<tr><td style="padding:4px 0;color:#64748B;font-size:12px">{r}</td>'
        f'<td style="padding:4px 0;font-size:12px;font-weight:600;text-align:right">{v}</td>'
        f'<td style="padding:4px 0;text-align:right">{c}</td></tr>'
        for r,v,c in rows
    )
    return (
        f'<div style="border:1px solid #E2E8F0;border-top:4px solid {color};'
        f'border-radius:8px;padding:16px;flex:1;min-width:220px">'
        f'<div style="font-size:14px;font-weight:700;color:{color}">{label}</div>'
        f'<div style="font-size:10px;color:#94A3B8;margin-bottom:10px">vs {prior_label}</div>'
        f'<table style="width:100%;border-collapse:collapse">{trs}</table></div>'
    )

def contrib_banco_html(df, um, pm, franq, color, mto_col="MTO_TOT"):
    df_u = df[df["MES"].astype(str).str[:7] == um]
    df_p = df[df["MES"].astype(str).str[:7] == pm]
    mkt_u = df_u[mto_col].sum()
    mkt_p = df_p[mto_col].sum()

    def bank_ms(dfx, mkt):
        g = dfx[dfx["FRANQUICIA"]==franq].groupby("ENTIDAD")[mto_col].sum()
        return g/mkt*100 if mkt > 0 else g*0

    ms_u = bank_ms(df_u, mkt_u)
    ms_p = bank_ms(df_p, mkt_p)
    entries = []
    for b in ms_u.index.union(ms_p.index):
        u_v = ms_u.get(b, 0); p_v = ms_p.get(b, 0)
        if u_v < 0.05: continue
        entries.append({"bank": _fmt_bank(b), "ms": u_v, "diff": u_v - p_v})

    entries.sort(key=lambda x: -x["diff"])
    gainers = [e for e in entries if e["diff"] > 0][:5]
    losers  = sorted([e for e in entries if e["diff"] < 0], key=lambda x: x["diff"])[:5]
    top = gainers + losers
    if not top:
        return '<div style="color:#94A3B8;font-size:12px;padding:8px">Sin datos</div>'

    trs = ""
    for r in top:
        bw  = min(abs(r["diff"])*50, 100)
        bc  = color if r["diff"] >= 0 else "#DC2626"
        sgn = "+" if r["diff"] > 0 else ""
        trs += (
            f'<tr>'
            f'<td style="padding:4px 0;font-size:11px;max-width:130px;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap">{r["bank"]}</td>'
            f'<td style="padding:4px 0;font-size:11px;font-weight:600;text-align:right;width:42px">'
            f'{r["ms"]:.2f}%</td>'
            f'<td style="padding:4px 0"><div style="display:flex;align-items:center;gap:4px">'
            f'<div style="width:{max(bw,2):.0f}px;height:7px;background:{bc};border-radius:3px"></div>'
            f'<span style="font-size:11px;color:{bc};font-weight:600">{sgn}{r["diff"]:.2f}pp</span>'
            f'</div></td></tr>'
        )
    label = "VISA" if color == VISA_COLOR else "MASTERCARD"
    return (
        f'<div style="border:1px solid #E2E8F0;border-top:3px solid {color};'
        f'border-radius:8px;padding:14px;flex:1;min-width:220px">'
        f'<div style="font-size:12px;font-weight:700;color:{color};margin-bottom:2px">{label}</div>'
        f'<div style="font-size:10px;color:#94A3B8;margin-bottom:8px">Δ pp vs {pm}</div>'
        f'<table style="width:100%;border-collapse:collapse">{trs}</table></div>'
    )

def divider():
    return '<div style="border-top:1px solid #E2E8F0;margin:24px 0"></div>'

# ── Build report ──────────────────────────────────────────────────────────────
def build_report(df_cred, df_deb):
    now = datetime.now().strftime("%d %b %Y")

    # Crédito
    map_c, per_c = aggregate(df_cred, FRANQS_CRED)
    um_c = per_c[-1]; pm_c = find_prior(um_c, per_c)
    def uc(f): return map_c.get(um_c,{}).get(f,{"mto_tot":0,"mto_nal":0,"mto_ext":0,"num_nal":0,"vigentes":0,"ms":0})
    def pc(f): return map_c.get(pm_c,{}).get(f,{"mto_tot":0,"mto_nal":0,"mto_ext":0,"num_nal":0,"vigentes":0,"ms":0})

    # Débito
    map_d, per_d = aggregate(df_deb, FRANQS_DEB)
    um_d = per_d[-1]; pm_d = find_prior(um_d, per_d)
    def ud(f): return map_d.get(um_d,{}).get(f,{"mto_tot":0,"mto_nal":0,"mto_ext":0,"num_nal":0,"vigentes":0,"ms":0})
    def pd_(f): return map_d.get(pm_d,{}).get(f,{"mto_tot":0,"mto_nal":0,"mto_ext":0,"num_nal":0,"vigentes":0,"ms":0})

    # Total
    df_tot = pd.concat([
        df_cred[df_cred["FRANQUICIA"].isin(FRANQS_DEB)][["MES","ENTIDAD","FRANQUICIA","MTO_TOT","MTO_NAL","MTO_EXT","NUM_NAL","VIGENTES"]],
        df_deb[["MES","ENTIDAD","FRANQUICIA","MTO_TOT","MTO_NAL","MTO_EXT","NUM_NAL","VIGENTES"]],
    ], ignore_index=True)
    map_t, per_t = aggregate(df_tot, FRANQS_DEB)
    um_t = per_t[-1]; pm_t = find_prior(um_t, per_t)
    def ut(f): return map_t.get(um_t,{}).get(f,{"mto_tot":0,"mto_nal":0,"mto_ext":0,"num_nal":0,"vigentes":0,"ms":0})
    def pt(f): return map_t.get(pm_t,{}).get(f,{"mto_tot":0,"mto_nal":0,"mto_ext":0,"num_nal":0,"vigentes":0,"ms":0})

    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<title>Market Intelligence Report {um_c}</title></head>
<body style="margin:0;padding:0;background:#F8FAFC;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:700px;margin:0 auto;padding:24px 16px">

  <!-- Header -->
  <div style="background:#0A1172;border-bottom:3px solid #F7A600;
              border-radius:8px;padding:20px 24px;margin-bottom:24px">
    <div style="font-size:10px;color:#A0AAC0;letter-spacing:.08em;
                text-transform:uppercase;margin-bottom:4px">
      Market Intelligence Report &nbsp;·&nbsp; {um_c}</div>
    <div style="font-size:22px;font-weight:700;color:#FFF">
      Visa Colombia &nbsp;—&nbsp; Market Intelligence</div>
    <div style="font-size:11px;color:#A0AAC0;margin-top:4px">
      Elaborado por Daniel Castañeda &nbsp;·&nbsp; Business Development</div>
  </div>

  <!-- TOTAL -->
  {section_header(f"Mercado Total — {um_t} vs {pm_t} (YoY)",
                  "Crédito + Débito · Visa y Mastercard")}
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
    {snap_card("VISA",       VISA_COLOR, ut("VISA"),       pt("VISA"),       pm_t, show_ext=False)}
    {snap_card("MASTERCARD", MC_COLOR,   ut("MASTERCARD"), pt("MASTERCARD"), pm_t, show_ext=False)}
  </div>
  <div style="font-size:10px;color:#94A3B8;margin-bottom:8px">
    Contribución al Δ MS por banco</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
    {contrib_banco_html(df_tot, um_t, pm_t, "VISA",       VISA_COLOR)}
    {contrib_banco_html(df_tot, um_t, pm_t, "MASTERCARD", MC_COLOR)}
  </div>

  {divider()}

  <!-- CRÉDITO -->
  {section_header(f"Crédito — {um_c} vs {pm_c} (YoY)",
                  "Visa, Mastercard, Amex y Diners · compras nacionales + exterior")}
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
    {snap_card("VISA",       VISA_COLOR, uc("VISA"),       pc("VISA"),       pm_c, show_ext=True)}
    {snap_card("MASTERCARD", MC_COLOR,   uc("MASTERCARD"), pc("MASTERCARD"), pm_c, show_ext=True)}
  </div>
  <div style="font-size:10px;color:#94A3B8;margin-bottom:8px">
    Contribución al Δ MS por banco</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
    {contrib_banco_html(df_cred, um_c, pm_c, "VISA",       VISA_COLOR)}
    {contrib_banco_html(df_cred, um_c, pm_c, "MASTERCARD", MC_COLOR)}
  </div>

  {divider()}

  <!-- DÉBITO -->
  {section_header(f"Débito — {um_d} vs {pm_d} (YoY)",
                  "MS estimado via TII · Nequi separado · sin desglose nacional/exterior")}
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
    {snap_card("VISA",       VISA_COLOR, ud("VISA"),       pd_("VISA"),       pm_d, show_ext=False)}
    {snap_card("MASTERCARD", MC_COLOR,   ud("MASTERCARD"), pd_("MASTERCARD"), pm_d, show_ext=False)}
  </div>
  <div style="font-size:10px;color:#94A3B8;margin-bottom:8px">
    Contribución al Δ MS por banco</div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">
    {contrib_banco_html(df_deb, um_d, pm_d, "VISA",       VISA_COLOR)}
    {contrib_banco_html(df_deb, um_d, pm_d, "MASTERCARD", MC_COLOR)}
  </div>

  <!-- Footer -->
  <div style="text-align:center;font-size:10px;color:#CBD5E1;
              padding-top:16px;border-top:1px solid #E2E8F0;margin-top:8px">
    Superintendencia Financiera de Colombia · datos.gov.co · Generado el {now}
  </div>

</div></body></html>"""

    return html, um_c


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    output_path = sys.argv[1] if len(sys.argv) > 1 else "report/output_report.html"

    df_raw  = download_data()
    df_cred = build_credito(df_raw)
    df_deb  = build_debito(df_raw)
    print(f"  Crédito: {len(df_cred):,} filas · Débito: {len(df_deb):,} filas")

    html, ultimo = build_report(df_cred, df_deb)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Reporte generado: {output_path}  (período: {ultimo})")
