"""
generate_report.py
Descarga datos SFC, aplica el mismo pipeline del notebook de análisis,
calcula snapshot Visa vs MC y contribución al MS, y genera reporte HTML.
"""

import requests
import pandas as pd
from io import StringIO
from datetime import datetime
from collections import defaultdict
import sys

SFC_URL = (
    "https://www.datos.gov.co/api/v3/views/h2jg-r3zg/export.csv"
    "?accessType=DOWNLOAD&app_token=bHWsGtRFRP9x8Hl8lYivqM1hQ"
)
FRANQUICIAS = ["VISA", "MASTERCARD", "AMERICAN EXPRESS", "DINERS"]
VISA_COLOR  = "#1A1F71"
MC_COLOR    = "#CC2200"

MAPA_TX = {
    "Monto de las transacciones por compras con tarjeta de crédito a nivel nacional": "MTO_COMPRAS_NAL",
    "Monto de las transacciones por compras en el exterior con tarjeta de crédito":   "MTO_COMPRAS_EXT",
    "Número de transacciones por compras a nivel nacional con tarjeta de crédito":    "NUM_COMPRAS_NAL",
    "Número de transacciones por compras en el exterior con tarjeta de crédito":      "NUM_COMPRAS_EXT",
}
MAPA_TARJETAS = {
    "Tarjetas de crédito vigentes a la fecha de corte": "VIGENTES_FECHA_CORTE",
    "Tarjetas de crédito canceladas en el mes":         "CANCELADAS",
}

def download_data():
    print("Descargando datos SFC...")
    resp = requests.get(SFC_URL, timeout=180)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text), low_memory=False)
    print(f"  {len(df):,} registros")
    print(f"  Columnas: {list(df.columns)}")
    return df

def clean_raw(df):
    df = df.rename(columns={
        "NOMBREENTIDAD": "ENTIDAD",
        "FECHACORTE":    "MES",
        "NOMBRE_UCA":    "FRANQUICIA",
        "TOTAL_TARJETAS":"indicador",
    })
    df["FRANQUICIA"] = df["FRANQUICIA"].replace("CREDIBANCO-VISA", "VISA")
    df = df[df["FRANQUICIA"] != "ADMINISTRADORAS DE SISTEMAS DE PAGO DE BAJO VALOR"]
    df["indicador"] = (
        df["indicador"].astype(str)
        .str.replace(",", "", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
    )
    df["MES"] = pd.to_datetime(df["MES"], format="%d/%m/%Y", dayfirst=True, errors="coerce")
    df = df.dropna(subset=["MES"])
    df["MES"] = df["MES"].dt.strftime("%Y-%m")
    print(f"  Período: {df['MES'].min()} -> {df['MES'].max()}")
    print(f"  Franquicias: {sorted(df['FRANQUICIA'].unique())}")
    return df

def build_table(df, mapa):
    df_f = df[df["DESCRIPCION"].isin(mapa.keys())].copy()
    df_f["DESCRIPCION"] = df_f["DESCRIPCION"].map(mapa)
    df_p = df_f.pivot_table(
        index=["MES", "ENTIDAD", "FRANQUICIA"],
        columns="DESCRIPCION",
        values="indicador",
        aggfunc="sum",
    ).reset_index()
    df_p.columns.name = None
    return df_p

def build_master(df):
    df_tx  = build_table(df, MAPA_TX)
    df_tgt = build_table(df, MAPA_TARJETAS)
    master = df_tx.merge(df_tgt, on=["MES","ENTIDAD","FRANQUICIA"], how="outer")
    master["MTO_COMPRAS_CREDITO"] = (
        master.get("MTO_COMPRAS_NAL", pd.Series(dtype=float)).fillna(0) +
        master.get("MTO_COMPRAS_EXT", pd.Series(dtype=float)).fillna(0)
    )
    for col in ["MTO_COMPRAS_NAL","MTO_COMPRAS_EXT","MTO_COMPRAS_CREDITO",
                "NUM_COMPRAS_NAL","NUM_COMPRAS_EXT","VIGENTES_FECHA_CORTE","CANCELADAS"]:
        if col not in master.columns:
            master[col] = 0.0
        master[col] = master[col].fillna(0)
    return master.sort_values("MES").reset_index(drop=True)

def aggregate(df, mode="mensual"):
    agg = defaultdict(lambda: defaultdict(lambda: {
        "mto_tot":0,"mto_nal":0,"mto_ext":0,
        "num_nal":0,"vigentes":0,"canceladas":0,
    }))
    for _, r in df.iterrows():
        key = r["MES"][:4] if mode == "anual" else r["MES"]
        d = agg[key][r["FRANQUICIA"]]
        d["mto_tot"]   += r["MTO_COMPRAS_CREDITO"]
        d["mto_nal"]   += r["MTO_COMPRAS_NAL"]
        d["mto_ext"]   += r["MTO_COMPRAS_EXT"]
        d["num_nal"]   += r["NUM_COMPRAS_NAL"]
        d["vigentes"]  += r["VIGENTES_FECHA_CORTE"]
        d["canceladas"]+= r["CANCELADAS"]
    periods = sorted(agg.keys())
    for p in periods:
        total = sum(agg[p][f]["mto_tot"] for f in FRANQUICIAS if f in agg[p])
        for f in agg[p]:
            agg[p][f]["ms"] = agg[p][f]["mto_tot"] / total if total > 0 else 0
    return dict(agg), periods

def find_prior(period, periods):
    if len(period) == 4:
        cand = str(int(period) - 1)
    else:
        try:
            y, m = int(period[:4]), int(period[5:7])
            m -= 12
            if m <= 0: m += 12; y -= 1
            cand = f"{y}-{m:02d}"
        except Exception:
            return periods[0]
    return cand if cand in periods else periods[0]

def fmt_cop(v):
    if v >= 1e12: return f"${v/1e12:.2f}B COP"
    if v >= 1e9:  return f"${v/1e9:.1f}MM COP"
    if v >= 1e6:  return f"${v/1e6:.0f}M COP"
    return f"${v:,.0f} COP"

def fmt_pct(v): return f"{'+'if v>0 else ''}{v:.1f}%"
def fmt_pp(v):  return f"{'+'if v>0 else ''}{v:.2f}pp"

def chip(val, fn):
    if val is None: return ""
    tc = "#15803D" if val>0 else ("#DC2626" if val<0 else "#94A3B8")
    bg = "#DCFCE7" if val>0 else ("#FEE2E2" if val<0 else "#F1F5F9")
    return f'<span style="background:{bg};color:{tc};padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600">{fn(val)}</span>'

def snap_card(label, color, u, p, prior_label):
    tku = u["mto_nal"]/u["num_nal"]/1000 if u["num_nal"]>0 else None
    tkp = p["mto_nal"]/p["num_nal"]/1000 if p["num_nal"]>0 else None
    rows = [
        ("Market Share",      f'{u["ms"]*100:.1f}%',
         chip((u["ms"]-p["ms"])*100 if p["ms"] else None, fmt_pp)),
        ("Facturación total", fmt_cop(u["mto_tot"]),
         chip((u["mto_tot"]/p["mto_tot"]-1)*100 if p["mto_tot"] else None, fmt_pct)),
        ("N° transacciones",  f'{int(u["num_nal"]):,}',
         chip((u["num_nal"]/p["num_nal"]-1)*100 if p["num_nal"] else None, fmt_pct)),
        ("Tarjetas vigentes", f'{int(u["vigentes"]):,}',
         chip((u["vigentes"]/p["vigentes"]-1)*100 if p["vigentes"] else None, fmt_pct)),
        ("Ticket promedio",   f'${tku:.0f}K' if tku else "—",
         chip((tku/tkp-1)*100 if tku and tkp else None, fmt_pct)),
    ]
    trs = "".join(
        f'<tr><td style="padding:6px 8px;color:#64748B;font-size:12px">{r}</td>'
        f'<td style="padding:6px 8px;font-size:12px;font-weight:600">{v}</td>'
        f'<td style="padding:6px 8px">{c}</td></tr>'
        for r,v,c in rows
    )
    return (f'<div style="border:1px solid #E2E8F0;border-top:4px solid {color};'
            f'border-radius:8px;padding:16px;flex:1;min-width:240px">'
            f'<div style="font-size:16px;font-weight:700;color:{color}">{label}</div>'
            f'<div style="font-size:11px;color:#94A3B8;margin-bottom:12px">vs {prior_label}</div>'
            f'<table style="width:100%;border-collapse:collapse">{trs}</table></div>')

def contrib_table(map_data, ult, pri):
    rows = []
    for f in FRANQUICIAS:
        u = map_data.get(ult,{}).get(f,{"ms":0})
        p = map_data.get(pri,{}).get(f,{"ms":0})
        diff = (u["ms"] - p["ms"]) * 100
        rows.append({"f":f, "ms":u["ms"]*100, "diff":diff})
    rows.sort(key=lambda x: -x["ms"])
    trs = ""
    for r in rows:
        bw = min(abs(r["diff"])*60, 100)
        bc = "#15803D" if r["diff"]>=0 else "#DC2626"
        sign = "+" if r["diff"]>0 else ""
        trs += (f'<tr><td style="padding:6px 8px;font-size:12px;width:140px">{r["f"].title()}</td>'
                f'<td style="padding:6px 8px;font-size:12px;font-weight:600">{r["ms"]:.1f}%</td>'
                f'<td style="padding:6px 8px"><div style="display:flex;align-items:center;gap:6px">'
                f'<div style="width:{bw}px;height:8px;background:{bc};border-radius:4px;min-width:2px"></div>'
                f'<span style="font-size:11px;color:{bc};font-weight:600">{sign}{r["diff"]:.2f}pp</span>'
                f'</div></td></tr>')
    return (f'<div style="border:1px solid #E2E8F0;border-radius:8px;padding:16px">'
            f'<div style="font-size:11px;color:#94A3B8;margin-bottom:10px">pp vs {pri}</div>'
            f'<table style="width:100%;border-collapse:collapse">{trs}</table></div>')

def build_report(master):
    map_m, periods_m = aggregate(master, "mensual")
    map_a, periods_a = aggregate(master, "anual")
    um, pm = periods_m[-1], find_prior(periods_m[-1], periods_m)
    ua, pa = periods_a[-1], find_prior(periods_a[-1], periods_a)
    now = datetime.now().strftime("%d %b %Y")

    def u(mp, k, f):
        return mp.get(k,{}).get(f,{"mto_tot":0,"mto_nal":0,"mto_ext":0,
                                    "num_nal":0,"vigentes":0,"canceladas":0,"ms":0})

    html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<title>Market Intelligence Report {um}</title></head>
<body style="margin:0;padding:0;background:#F8FAFC;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:680px;margin:0 auto;padding:24px 16px">

<div style="background:#0A1172;border-bottom:3px solid #F7A600;border-radius:8px;padding:20px 24px;margin-bottom:24px">
  <div style="font-size:10px;color:#A0AAC0;letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px">Market Intelligence Report &nbsp;·&nbsp; {um}</div>
  <div style="font-size:22px;font-weight:700;color:#FFF">Visa Colombia &nbsp;—&nbsp; Tarjetas de Crédito</div>
  <div style="font-size:11px;color:#A0AAC0;margin-top:4px">Elaborado por Daniel Castañeda &nbsp;·&nbsp; Business Development</div>
</div>

<div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;text-transform:uppercase;margin-bottom:10px">Snapshot mensual — {um} vs {pm}</div>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">
  {snap_card("VISA", VISA_COLOR, u(map_m,um,"VISA"), u(map_m,pm,"VISA"), pm)}
  {snap_card("MASTERCARD", MC_COLOR, u(map_m,um,"MASTERCARD"), u(map_m,pm,"MASTERCARD"), pm)}
</div>

<div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;text-transform:uppercase;margin-bottom:10px">Contribución al cambio en Market Share — {um} vs {pm}</div>
<div style="margin-bottom:28px">{contrib_table(map_m, um, pm)}</div>

<div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;text-transform:uppercase;margin-bottom:10px">Snapshot anual — {ua} vs {pa}</div>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">
  {snap_card("VISA", VISA_COLOR, u(map_a,ua,"VISA"), u(map_a,pa,"VISA"), pa)}
  {snap_card("MASTERCARD", MC_COLOR, u(map_a,ua,"MASTERCARD"), u(map_a,pa,"MASTERCARD"), pa)}
</div>

<div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;text-transform:uppercase;margin-bottom:10px">Contribución al cambio en Market Share — {ua} vs {pa}</div>
<div style="margin-bottom:28px">{contrib_table(map_a, ua, pa)}</div>

<div style="text-align:center;font-size:10px;color:#CBD5E1;padding-top:16px;border-top:1px solid #E2E8F0">
  Superintendencia Financiera de Colombia · datos.gov.co · Solo tarjetas de crédito · {now}
</div>
</div></body></html>"""

    return html, um

if __name__ == "__main__":
    output_path = sys.argv[1] if len(sys.argv) > 1 else "report/output_report.html"
    df_raw = download_data()
    df     = clean_raw(df_raw)
    master = build_master(df)
    print(f"  Dataset: {len(master):,} filas · {master['MES'].nunique()} períodos")
    html, ultimo = build_report(master)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Reporte generado: {output_path}  (período: {ultimo})")
