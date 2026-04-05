"""
generate_report.py
Descarga datos SFC, calcula snapshot Visa vs MC y contribución al MS,
y genera un reporte HTML listo para enviar por email.
"""

import requests
import pandas as pd
from datetime import datetime, date
from collections import defaultdict
import os
import sys

# ── Configuración ─────────────────────────────────────────────────────────────
SFC_URL = (
    "https://www.datos.gov.co/api/v3/views/h2jg-r3zg/export.csv"
    "?accessType=DOWNLOAD&app_token=bHWsGtRFRP9x8Hl8lYivqM1hQ"
)
FRANQUICIAS = ["VISA", "MASTERCARD", "AMERICAN EXPRESS", "DINERS"]
VISA_COLOR  = "#1A1F71"
MC_COLOR    = "#CC2200"


# ── Descarga de datos ─────────────────────────────────────────────────────────
def download_data():
    print("Descargando datos SFC...")
    resp = requests.get(SFC_URL, timeout=120)
    resp.raise_for_status()
    from io import StringIO
    df = pd.read_csv(StringIO(resp.text), low_memory=False)
    print(f"  {len(df):,} registros descargados.")
    return df


def clean_data(df):
    df.columns = [c.strip().upper().replace(" ", "_") for c in df.columns]

    # Mapear columnas clave con nombres posibles en el CSV
    col_map = {
        "MES":                  ["MES", "PERIODO", "FECHA"],
        "ENTIDAD":              ["ENTIDAD", "BANCO", "INSTITUCION"],
        "FRANQUICIA":           ["FRANQUICIA", "MARCA"],
        "MTO_COMPRAS_NAL":      ["MTO_COMPRAS_NAL", "COMPRAS_NAL", "MONTO_NAL"],
        "MTO_COMPRAS_EXT":      ["MTO_COMPRAS_EXT", "COMPRAS_EXT", "MONTO_EXT"],
        "MTO_COMPRAS_CREDITO":  ["MTO_COMPRAS_CREDITO", "COMPRAS_CREDITO", "MONTO_TOTAL"],
        "NUM_COMPRAS_NAL":      ["NUM_COMPRAS_NAL", "NUM_TRANSACCIONES_NAL"],
        "VIGENTES_FECHA_CORTE": ["VIGENTES_FECHA_CORTE", "TARJETAS_VIGENTES"],
        "CANCELADAS":           ["CANCELADAS"],
    }
    rename = {}
    for canonical, candidates in col_map.items():
        for c in candidates:
            if c in df.columns and canonical not in df.columns:
                rename[c] = canonical
    df = df.rename(columns=rename)

    # Solo crédito
    if "TIPO_TARJETA" in df.columns:
        df = df[df["TIPO_TARJETA"].str.upper().str.contains("CR", na=False)]

    numeric = ["MTO_COMPRAS_NAL", "MTO_COMPRAS_EXT", "MTO_COMPRAS_CREDITO",
               "NUM_COMPRAS_NAL", "VIGENTES_FECHA_CORTE", "CANCELADAS"]
    for c in numeric:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    df["FRANQUICIA"] = df["FRANQUICIA"].str.upper().str.strip()
    df["MES"]        = df["MES"].astype(str).str.strip().str[:7]   # YYYY-MM

    # Columna total si falta
    if "MTO_COMPRAS_CREDITO" not in df.columns:
        df["MTO_COMPRAS_CREDITO"] = df.get("MTO_COMPRAS_NAL", 0) + df.get("MTO_COMPRAS_EXT", 0)

    return df.sort_values("MES")


# ── Agregación ────────────────────────────────────────────────────────────────
def aggregate_by_period(df, mode="mensual"):
    """Devuelve dict: period -> franquicia -> metrics"""
    agg = defaultdict(lambda: defaultdict(lambda: {
        "mto_tot": 0, "mto_nal": 0, "mto_ext": 0,
        "num_nal": 0, "vigentes": 0, "canceladas": 0,
    }))
    for _, r in df.iterrows():
        key = r["MES"][:4] if mode == "anual" else r["MES"]
        f   = r["FRANQUICIA"]
        d   = agg[key][f]
        d["mto_tot"]   += r.get("MTO_COMPRAS_CREDITO", 0)
        d["mto_nal"]   += r.get("MTO_COMPRAS_NAL", 0)
        d["mto_ext"]   += r.get("MTO_COMPRAS_EXT", 0)
        d["num_nal"]   += r.get("NUM_COMPRAS_NAL", 0)
        d["vigentes"]  += r.get("VIGENTES_FECHA_CORTE", 0)
        d["canceladas"]+= r.get("CANCELADAS", 0)

    periods = sorted(agg.keys())
    # Calcular market share
    for p in periods:
        total = sum(agg[p][f]["mto_tot"] for f in FRANQUICIAS if f in agg[p])
        for f in agg[p]:
            agg[p][f]["ms"] = agg[p][f]["mto_tot"] / total if total > 0 else 0

    return dict(agg), periods


def find_prior(period, all_periods):
    """Devuelve el período 12 meses (o 1 año) antes."""
    if len(period) == 4:
        return str(int(period) - 1)
    try:
        y, m = int(period[:4]), int(period[5:7])
        m -= 12
        if m <= 0:
            m += 12; y -= 1
        prior = f"{y}-{m:02d}"
        return prior if prior in all_periods else all_periods[0]
    except Exception:
        return all_periods[0]


# ── Formateo ──────────────────────────────────────────────────────────────────
def fmt_cop(val):
    """Formatea en billones/miles de millones COP."""
    if val >= 1e12:
        return f"${val/1e12:.2f}B COP"
    if val >= 1e9:
        return f"${val/1e9:.1f}MM COP"
    if val >= 1e6:
        return f"${val/1e6:.0f}M COP"
    return f"${val:,.0f} COP"

def fmt_pct(val, decimals=1):
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.{decimals}f}%"

def fmt_pp(val):
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}pp"

def chip_color(val, invert=False):
    positive = val > 0 if not invert else val < 0
    if abs(val) < 0.01:
        return "#94A3B8", "#F1F5F9"   # neutral
    return ("#15803D", "#DCFCE7") if positive else ("#DC2626", "#FEE2E2")

def chip_html(val, fmt_fn, invert=False):
    text_col, bg_col = chip_color(val, invert)
    return (
        f'<span style="background:{bg_col};color:{text_col};'
        f'padding:2px 7px;border-radius:20px;font-size:11px;font-weight:600">'
        f'{fmt_fn(val)}</span>'
    )


# ── Construcción del reporte ──────────────────────────────────────────────────
def build_report(df):
    map_m, periods = aggregate_by_period(df, "mensual")
    map_a, periods_a = aggregate_by_period(df, "anual")

    ultimo  = periods[-1]
    prior12 = find_prior(ultimo, periods)
    ultimo_a  = periods_a[-1]
    prior_a   = find_prior(ultimo_a, periods_a)

    now = datetime.now().strftime("%d %b %Y")

    # ── Snapshot por franquicia ───────────────────────────────────────────────
    def snap_rows(f, map_data, ult, pri):
        u = map_data.get(ult, {}).get(f, {})
        p = map_data.get(pri, {}).get(f, {})
        ms_u = (u.get("ms", 0)) * 100
        ms_p = (p.get("ms", 0)) * 100
        d_ms = ms_u - ms_p
        ticket_u = u["mto_nal"] / u["num_nal"] / 1000 if u.get("num_nal", 0) > 0 else None
        ticket_p = p["mto_nal"] / p["num_nal"] / 1000 if p.get("num_nal", 0) > 0 else None
        d_fact  = (u["mto_tot"] / p["mto_tot"] - 1) * 100 if p.get("mto_tot", 0) > 0 else None
        d_txn   = ((u["num_nal"]) / p["num_nal"] - 1) * 100 if p.get("num_nal", 0) > 0 else None
        d_vig   = (u["vigentes"] / p["vigentes"] - 1) * 100 if p.get("vigentes", 0) > 0 else None
        d_tk    = (ticket_u / ticket_p - 1) * 100 if ticket_u and ticket_p else None
        return {
            "ms": ms_u, "d_ms": d_ms,
            "mto_tot": u.get("mto_tot", 0), "d_fact": d_fact,
            "num_nal": u.get("num_nal", 0),  "d_txn": d_txn,
            "vigentes": u.get("vigentes", 0), "d_vig": d_vig,
            "ticket": ticket_u,               "d_tk": d_tk,
        }

    snap_v_m = snap_rows("VISA",       map_m, ultimo,   prior12)
    snap_mc_m= snap_rows("MASTERCARD", map_m, ultimo,   prior12)
    snap_v_a = snap_rows("VISA",       map_a, ultimo_a, prior_a)
    snap_mc_a= snap_rows("MASTERCARD", map_a, ultimo_a, prior_a)

    # ── Contribución al cambio de MS por franquicia ───────────────────────────
    def contrib_rows(map_data, ult, pri):
        rows = []
        for f in FRANQUICIAS:
            u = map_data.get(ult, {}).get(f, {})
            p = map_data.get(pri, {}).get(f, {})
            diff = (u.get("ms", 0) - p.get("ms", 0)) * 100
            rows.append({"f": f, "ms": u.get("ms", 0)*100, "diff": diff})
        return sorted(rows, key=lambda x: -x["ms"])

    contrib_m = contrib_rows(map_m, ultimo, prior12)
    contrib_a = contrib_rows(map_a, ultimo_a, prior_a)

    # ── HTML ──────────────────────────────────────────────────────────────────
    def snap_card_html(label, color, snap, prior_label):
        rows = [
            ("Market Share",       f'{snap["ms"]:.1f}%',
             chip_html(snap["d_ms"], fmt_pp) if snap["d_ms"] is not None else ""),
            ("Facturación total",  fmt_cop(snap["mto_tot"]),
             chip_html(snap["d_fact"], fmt_pct) if snap["d_fact"] is not None else ""),
            ("N° transacciones",   f'{int(snap["num_nal"]):,}',
             chip_html(snap["d_txn"], fmt_pct) if snap["d_txn"] is not None else ""),
            ("Tarjetas vigentes",  f'{int(snap["vigentes"]):,}',
             chip_html(snap["d_vig"], fmt_pct) if snap["d_vig"] is not None else ""),
            ("Ticket promedio",    f'${snap["ticket"]:.0f}K COP' if snap["ticket"] else "—",
             chip_html(snap["d_tk"], fmt_pct) if snap["d_tk"] is not None else ""),
        ]
        rows_html = "".join(
            f'<tr><td style="padding:6px 8px;color:#64748B;font-size:12px">{r}</td>'
            f'<td style="padding:6px 8px;font-size:12px;font-weight:600">{v}</td>'
            f'<td style="padding:6px 8px">{c}</td></tr>'
            for r, v, c in rows
        )
        return f"""
        <div style="border:1px solid #E2E8F0;border-top:4px solid {color};
                    border-radius:8px;padding:16px;flex:1;min-width:240px">
          <div style="font-size:16px;font-weight:700;color:{color};margin-bottom:4px">{label}</div>
          <div style="font-size:11px;color:#94A3B8;margin-bottom:12px">vs {prior_label}</div>
          <table style="width:100%;border-collapse:collapse">{rows_html}</table>
        </div>"""

    def contrib_table_html(rows, prior_label):
        trs = ""
        for r in rows:
            bar_w = min(abs(r["diff"]) * 60, 100)
            bar_c = "#15803D" if r["diff"] >= 0 else "#DC2626"
            sign  = "+" if r["diff"] > 0 else ""
            trs += f"""
            <tr>
              <td style="padding:6px 8px;font-size:12px;width:140px">{r["f"].title()}</td>
              <td style="padding:6px 8px;font-size:12px;font-weight:600">{r["ms"]:.1f}%</td>
              <td style="padding:6px 8px">
                <div style="display:flex;align-items:center;gap:6px">
                  <div style="width:{bar_w}px;height:8px;background:{bar_c};
                               border-radius:4px;min-width:2px"></div>
                  <span style="font-size:11px;color:{bar_c};font-weight:600">
                    {sign}{r["diff"]:.2f}pp
                  </span>
                </div>
              </td>
            </tr>"""
        return f"""
        <div style="border:1px solid #E2E8F0;border-radius:8px;padding:16px">
          <div style="font-size:11px;color:#94A3B8;margin-bottom:10px">Δ pp vs {prior_label}</div>
          <table style="width:100%;border-collapse:collapse">{trs}</table>
        </div>"""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Intelligence Report — {ultimo}</title>
</head>
<body style="margin:0;padding:0;background:#F8FAFC;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:680px;margin:0 auto;padding:24px 16px">

  <!-- HEADER -->
  <div style="background:#0A1172;border-bottom:3px solid #F7A600;
              border-radius:8px;padding:20px 24px;margin-bottom:24px">
    <div style="font-size:10px;color:#A0AAC0;letter-spacing:.08em;
                text-transform:uppercase;margin-bottom:4px">
      Market Intelligence Report &nbsp;·&nbsp; {ultimo}
    </div>
    <div style="font-size:22px;font-weight:700;color:#FFFFFF">
      Visa Colombia &nbsp;—&nbsp; Tarjetas de Crédito
    </div>
    <div style="font-size:11px;color:#A0AAC0;margin-top:4px">
      Elaborado por Daniel Castañeda &nbsp;·&nbsp; Business Development
    </div>
  </div>

  <!-- SNAPSHOT MENSUAL -->
  <div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;
              text-transform:uppercase;margin-bottom:10px">
    Snapshot comparativo — {ultimo} vs {prior12}
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">
    {snap_card_html("VISA", VISA_COLOR, snap_v_m, prior12)}
    {snap_card_html("MASTERCARD", MC_COLOR, snap_mc_m, prior12)}
  </div>

  <!-- CONTRIBUCIÓN MS MENSUAL -->
  <div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;
              text-transform:uppercase;margin-bottom:10px">
    Contribución al cambio en Market Share — {ultimo} vs {prior12}
  </div>
  <div style="margin-bottom:28px">
    {contrib_table_html(contrib_m, prior12)}
  </div>

  <!-- SNAPSHOT ANUAL -->
  <div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;
              text-transform:uppercase;margin-bottom:10px">
    Snapshot comparativo — {ultimo_a} vs {prior_a} (acumulado año)
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">
    {snap_card_html("VISA", VISA_COLOR, snap_v_a, prior_a)}
    {snap_card_html("MASTERCARD", MC_COLOR, snap_mc_a, prior_a)}
  </div>

  <!-- CONTRIBUCIÓN MS ANUAL -->
  <div style="font-size:10px;color:#94A3B8;letter-spacing:.09em;
              text-transform:uppercase;margin-bottom:10px">
    Contribución al cambio en Market Share — {ultimo_a} vs {prior_a} (acumulado año)
  </div>
  <div style="margin-bottom:28px">
    {contrib_table_html(contrib_a, prior_a)}
  </div>

  <!-- FOOTER -->
  <div style="text-align:center;font-size:10px;color:#CBD5E1;padding-top:16px;
              border-top:1px solid #E2E8F0">
    Superintendencia Financiera de Colombia · datos.gov.co ·
    Solo tarjetas de crédito · Generado el {now}
  </div>

</div>
</body>
</html>"""

    return html, ultimo


# ── Guardar ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    output_path = sys.argv[1] if len(sys.argv) > 1 else "report/output_report.html"

    df  = download_data()
    df  = clean_data(df)
    html, ultimo = build_report(df)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Reporte generado: {output_path}  (período: {ultimo})")
