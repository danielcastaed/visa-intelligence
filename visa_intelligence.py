#!/usr/bin/env python3
"""
Visa Market Intelligence System
Corre automáticamente — compatible con GitHub Actions y cualquier servidor Python.
Configurar variables de entorno: GMAIL_USER, GMAIL_PASSWORD, EMAIL_DESTINO
"""

import os
import feedparser
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import smtplib
import math
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import warnings
warnings.filterwarnings("ignore")

# ── Credenciales desde variables de entorno (GitHub Secrets) ──────────
GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")
EMAIL_DESTINO  = os.environ.get("EMAIL_DESTINO", "")

# ── Período: último mes completo ──────────────────────────────────────
HOY = datetime.now()
SEMANA_ATRAS = HOY - timedelta(days=30)

# ============================================================
# CELDA 3 — IMPORTS Y CONFIGURACIÓN
# ============================================================

HOY = datetime.now()
SEMANA_ATRAS = HOY - timedelta(days=90)  # 90 días para validar pipeline — cambia a 7 cuando confirmes que funciona
print(f"✅ Configuración lista | Período: {SEMANA_ATRAS.strftime('%d/%m/%Y')} → {HOY.strftime('%d/%m/%Y')}")

# ============================================================
# CELDA 4 — FUENTES DE DATOS
# ============================================================

# --- MÓDULO 1: Mastercard Intelligence Tracker ---
# Los newsrooms oficiales de Mastercard bloquean bots — usamos Google News
FUENTES_MASTERCARD = [
    {"nombre": "Google News - Mastercard global",
     "url": "https://news.google.com/rss/search?q=Mastercard+new+product+launch&hl=en-US&gl=US&ceid=US:en",
     "tipo": "rss"},
    {"nombre": "Google News - Mastercard LatAm",
     "url": "https://news.google.com/rss/search?q=Mastercard+Latin+America+Colombia+partnership&hl=en-US&gl=US&ceid=US:en",
     "tipo": "rss"},
    {"nombre": "Google News - Mastercard ES",
     "url": "https://news.google.com/rss/search?q=Mastercard+Colombia+lanzamiento+producto&hl=es-419&gl=CO&ceid=CO:es-419",
     "tipo": "rss"},
]

# Bancos colombianos clave (emisores Visa) — solo Google News, los sitios bancarios bloquean scrapers
FUENTES_BANCOS_CO = [
    {"nombre": "Google News - Mastercard Colombia banco",
     "url": "https://news.google.com/rss/search?q=Mastercard+Colombia+banco&hl=es-419&gl=CO&ceid=CO:es-419",
     "tipo": "rss"},
    {"nombre": "Google News - tarjeta lanzamiento CO",
     "url": "https://news.google.com/rss/search?q=tarjeta+credito+debito+Colombia+lanzamiento&hl=es-419&gl=CO&ceid=CO:es-419",
     "tipo": "rss"},
]

# --- MÓDULO 2: Fintech Pulse ---
FUENTES_FINTECH = [
    {"nombre": "Google News - Fintech Colombia",  "url": "https://news.google.com/rss/search?q=fintech+Colombia+2024&hl=es-419&gl=CO&ceid=CO:es-419", "tipo": "rss"},
    {"nombre": "Google News - Pagos digitales CO", "url": "https://news.google.com/rss/search?q=pagos+digitales+Colombia+regulacion&hl=es-419&gl=CO&ceid=CO:es-419", "tipo": "rss"},
    {"nombre": "Google News - SFC Colombia",       "url": "https://news.google.com/rss/search?q=Superfinanciera+Colombia+fintech&hl=es-419&gl=CO&ceid=CO:es-419", "tipo": "rss"},
    {"nombre": "Google News - Rappi Nequi Nubank", "url": "https://news.google.com/rss/search?q=Rappi+Nequi+Nubank+Colombia+tarjeta&hl=es-419&gl=CO&ceid=CO:es-419", "tipo": "rss"},
    {"nombre": "Google News - fintech LatAm inversión", "url": "https://news.google.com/rss/search?q=fintech+Latin+America+funding+2025&hl=en-US&gl=US&ceid=US:en", "tipo": "rss"},
    {"nombre": "Google News - open finance Colombia", "url": "https://news.google.com/rss/search?q=open+finance+finanzas+abiertas+Colombia&hl=es-419&gl=CO&ceid=CO:es-419", "tipo": "rss"},
]

# --- MÓDULO 3: SFC — Circulares y aprobación de nuevas compañías ---
# La SFC no publica RSS nativo, usamos scraping directo + Google News como proxy
SFC_CIRCULARES_URL    = "https://www.superfinanciera.gov.co/publicaciones/10115459/circulares-externas-2025/"
SFC_CIRCULARES_URL_24 = "https://www.superfinanciera.gov.co/publicaciones/10114895/circulares-externas-2024/"
SFC_RESOLUCIONES_URL  = "https://www.superfinanciera.gov.co/publicaciones/10114898/resoluciones-2024/"

# Palabras clave que indican aprobación de nuevas entidades de financiamiento
KEYWORDS_SFC = [
    "compañía de financiamiento", "compañía financiamiento",
    "autorización funcionamiento", "aprobación constitución",
    "nueva entidad vigilada", "certificado funcionamiento",
    "establecimiento bancario", "corporación financiera",
    "cooperativa financiera", "licencia bancaria",
    "fintech autorizada", "entidad vigilada nueva",
]

FUENTES_SFC_NEWS = [
    {"nombre": "Google News - SFC aprobaciones",
     "url": "https://news.google.com/rss/search?q=Superfinanciera+aprobacion+compania+financiamiento+Colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "tipo": "rss"},
    {"nombre": "Google News - SFC nueva entidad",
     "url": "https://news.google.com/rss/search?q=SFC+Colombia+nueva+entidad+vigilada+autorizacion+2025&hl=es-419&gl=CO&ceid=CO:es-419",
     "tipo": "rss"},
    {"nombre": "Google News - licencia bancaria CO",
     "url": "https://news.google.com/rss/search?q=licencia+bancaria+Colombia+fintech+aprobacion+Superfinanciera&hl=es-419&gl=CO&ceid=CO:es-419",
     "tipo": "rss"},
]

print(f"📡 Fuentes configuradas: {len(FUENTES_MASTERCARD + FUENTES_BANCOS_CO)} Mastercard/Bancos · {len(FUENTES_FINTECH)} Fintech · {len(FUENTES_SFC_NEWS)}+scraping SFC")

# ============================================================
# CELDA 5 — SCRAPER UNIVERSAL
# ============================================================

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; VisaIntelBot/1.0)"}

def scrape_rss(fuente, timeout=8):
    """Extrae artículos de un feed RSS de la última semana."""
    articulos = []
    try:
        resp = requests.get(fuente["url"], headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            # Fecha — intentamos parsear, si falla incluimos el artículo igual
            fecha = HOY  # default: incluir si no hay fecha
            for campo in ['published_parsed', 'updated_parsed']:
                val = getattr(entry, campo, None)
                if val:
                    try:
                        fecha = datetime(*val[:6])  # siempre naive, sin tz
                        break
                    except Exception:
                        pass

            # Comparación segura (ambos naive)
            limite = SEMANA_ATRAS.replace(tzinfo=None)
            if fecha.replace(tzinfo=None) >= limite:
                resumen = ""
                if hasattr(entry, 'summary'):
                    soup = BeautifulSoup(entry.summary, 'html.parser')
                    resumen = soup.get_text()[:400]

                articulos.append({
                    "fuente":  fuente["nombre"],
                    "titulo":  entry.get("title", "")[:200],
                    "resumen": resumen,
                    "link":    entry.get("link", ""),
                    "fecha":   fecha.strftime("%d/%m/%Y"),
                })
    except requests.exceptions.Timeout:
        print(f"  ⏱️  Timeout en {fuente['nombre']} — omitida")
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  Error en {fuente['nombre']}: {type(e).__name__}")
    except Exception as e:
        print(f"  ⚠️  Error inesperado en {fuente['nombre']}: {type(e).__name__}")
    return articulos


def recolectar_noticias(lista_fuentes, modulo):
    """Corre el scraper en todas las fuentes de un módulo."""
    todos = []
    print(f"\n🔄 Recolectando: {modulo}")
    for fuente in lista_fuentes:
        arts = scrape_rss(fuente)
        print(f"   {fuente['nombre']}: {len(arts)} artículos")
        todos.extend(arts)
    return pd.DataFrame(todos)


print("✅ Scraper listo")

# ============================================================
# CELDA 5B — SCRAPER DIRECTO SFC (sin RSS nativo)
# ============================================================
# La SFC publica sus circulares en HTML, no tiene RSS propio.
# Estrategia dual: scraping directo de la página de circulares
# + Google News como proxy para noticias sobre aprobaciones.

def scrape_sfc_circulares(url, anio=2025):
    """Extrae circulares de la SFC filtrando por keywords de financiamiento."""
    resultados = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        textos = soup.find_all(['a', 'li', 'p', 'td'], string=True)
        for elem in textos:
            texto = elem.get_text(strip=True)
            if len(texto) < 15:
                continue
            texto_lower = texto.lower()
            if any(kw in texto_lower for kw in KEYWORDS_SFC):
                link = ""
                if elem.name == 'a' and elem.get('href'):
                    href = elem['href']
                    link = href if href.startswith('http') else f'https://www.superfinanciera.gov.co{href}'
                resultados.append({
                    'fuente':    f'SFC Circulares {anio}',
                    'titulo':    texto[:300],
                    'resumen':   'Circular SFC relacionada con compañías de financiamiento o nuevas entidades vigiladas.',
                    'link':      link,
                    'fecha':     HOY.strftime('%d/%m/%Y'),
                    'categoria': 'circular SFC — compañía de financiamiento',
                    'score':     0.90,
                    'alerta':    'ALTA',
                })
    except Exception as e:
        print(f'  ⚠️  Error scraping SFC ({anio}): {e}')
    return resultados


def recolectar_sfc():
    """Combina scraping directo + Google News para máxima cobertura SFC."""
    print('\n🔄 Recolectando: SFC — Circulares y aprobaciones')

    # 1. Scraping directo de las páginas de circulares y resoluciones
    c2025 = scrape_sfc_circulares(SFC_CIRCULARES_URL, 2025)
    c2024 = scrape_sfc_circulares(SFC_CIRCULARES_URL_24, 2024)
    res   = scrape_sfc_circulares(SFC_RESOLUCIONES_URL, 2024)
    scraping = c2025 + c2024 + res
    print(f'   Scraping directo SFC: {len(scraping)} circulares con keywords relevantes')

    # 2. Google News como cobertura de medios sobre nuevas aprobaciones
    noticias = []
    for fuente in FUENTES_SFC_NEWS:
        arts = scrape_rss(fuente)
        filtradas = [a for a in arts
                     if any(kw in (a['titulo'] + a['resumen']).lower() for kw in KEYWORDS_SFC)]
        print(f'   {fuente["nombre"]}: {len(filtradas)} relevantes (de {len(arts)} totales)')
        noticias.extend(filtradas)

    # Marcar las de Google News con alerta apropiada
    for n in noticias:
        n.setdefault('categoria', 'circular SFC — compañía de financiamiento')
        n.setdefault('score', 0.85)
        n.setdefault('alerta', 'ALTA')

    df_sfc = pd.DataFrame(scraping + noticias)
    print(f'\n📊 SFC Total: {len(df_sfc)} registros relevantes detectados')
    return df_sfc


print('✅ Scraper SFC listo')

# ============================================================
# CELDA 6 — CLASIFICADOR NLP (gratuito, sin API key)
# ============================================================
from transformers import pipeline

print("⏳ Cargando modelo NLP (primera vez toma ~2 min)...")
clasificador = pipeline(
    "zero-shot-classification",
    model="cross-encoder/nli-MiniLM2-L6-H768",
    device=-1
)
print("✅ Modelo NLP listo")

LABELS_MC = [
    "lanzamiento nuevo producto Mastercard",
    "alianza banco con Mastercard",
    "expansión Mastercard Colombia",
    "noticia general sin relevancia competitiva",
]

LABELS_FT = [
    "nueva fintech o neobank en Colombia",
    "fintech aprobada o autorizada como compañía de financiamiento",
    "regulación SFC o norma financiera",
    "ronda de inversión fintech LatAm",
    "expansión fintech existente Colombia",
    "noticia general sin relevancia estratégica",
]

# Keywords que fuerzan ALTA en MC — deben mencionar banco/producto colombiano concreto
# y contener "Mastercard" en el mismo texto
KEYWORDS_MC_COLOMBIA = [
    "davivienda", "bancolombia", "banco de bogotá", "bbva colombia",
    "nequi", "daviplata", "rappi", "scotiabank colombia", "itaú colombia",
    "banco popular", "colpatria", "falabella colombia", "linio",
    "colombia mastercard", "mastercard colombia", "tarjeta mastercard colombia",
    "nueva tarjeta mastercard", "lanzamiento mastercard",
    "mastercard débito", "mastercard crédito", "mastercard prepago",
    "co-branded mastercard", "cobranded mastercard",
]

# Keywords que fuerzan BAJA en MC — fuente global sin contexto colombiano
# Si el título NO contiene ningún banco/fintech colombiana y proviene de global → BAJA
FUENTES_GLOBALES_MC = [
    "google news - mastercard global",
    "google news - mastercard latam",
]

# Keywords que fuerzan ALTA en Fintech
KEYWORDS_FT_ALTA = [
    "compañía de financiamiento", "autorizada por la sfc",
    "aprobada superfinanciera", "licencia financiera",
    "autorización funcionamiento", "entidad vigilada",
    "fintech regulada", "aprobación sfc",
]

def clasificar_articulo(titulo, resumen, labels):
    texto = f"{titulo}. {resumen[:300]}"
    try:
        resultado = clasificador(texto, labels, multi_label=False)
        return resultado["labels"][0], round(resultado["scores"][0], 2)
    except:
        return "sin clasificar", 0.0

def calcular_alerta(categoria, score, modulo, titulo="", resumen="", fuente=""):
    """
    Lógica de prioridad de alertas.
    Las reglas de keywords tienen SIEMPRE precedencia sobre el NLP.
    """
    texto = (titulo + " " + resumen).lower()
    fuente_lower = fuente.lower()
    irrelevantes = {
        "noticia general sin relevancia competitiva",
        "noticia general sin relevancia estratégica",
    }

    if modulo == "mc":
        # Regla 0: BAJA si la noticia menciona Visa como red de la tarjeta
        # Cubre casos como "Banco Popular lanza tarjetas Visa" donde no hay Mastercard
        KEYWORDS_VISA_RED = [
            "tarjeta visa", "tarjetas visa", "visa card", "visa cards",
            "visa credit", "visa debit", "visa débito", "visa crédito",
            "visa prepaid", "visa prepago", "visa infinite", "visa platinum",
            "visa gold", "visa signature", "visa classic", "visa electron",
            "launch visa", "lanzamiento visa", "nueva tarjeta visa",
            "visa launches", "visa launch", "lanza tarjeta visa",
            "lanza tarjetas visa", "lanzó tarjeta visa", "lanzó tarjetas visa",
            "débito visa", "crédito visa", "edición visa", "portafolio visa",
        ]
        # Solo aplicar BAJA si Visa aparece en el texto Y Mastercard NO aparece
        tiene_visa = any(kw in texto for kw in KEYWORDS_VISA_RED)
        tiene_mc   = "mastercard" in texto
        if tiene_visa and not tiene_mc:
            return "BAJA"

        # Regla 1: ALTA si menciona banco colombiano + Mastercard explícito
        tiene_banco_co = any(kw in texto for kw in KEYWORDS_MC_COLOMBIA)
        if tiene_banco_co and tiene_mc:
            return "ALTA"
        # Si menciona banco colombiano pero no Mastercard → no es noticia MC
        if tiene_banco_co and not tiene_mc:
            return "BAJA"

        # Regla 2: BAJA si NLP dice irrelevante — sin excepción, incluso si
        # contiene "Mastercard" genérico (ej: noticia de Medio Oriente, EE.UU.)
        if categoria in irrelevantes:
            return "BAJA"

        # Regla 3: BAJA si viene de fuente global y el score es bajo
        if fuente_lower in FUENTES_GLOBALES_MC and score < 0.60:
            return "BAJA"

    if modulo == "ft":
        # Forzar ALTA si fintech fue aprobada/autorizada
        if any(kw in texto for kw in KEYWORDS_FT_ALTA):
            return "ALTA"
        if categoria in irrelevantes:
            return "BAJA"

    # Regla general por score NLP
    if score >= 0.75: return "ALTA"
    if score >= 0.50: return "MEDIA"
    return "BAJA"

print("✅ Clasificador configurado")

# ============================================================
# CELDA 7 — EJECUTAR MÓDULO 1: Mastercard Intelligence Tracker
# ============================================================

fuentes_mc_total = FUENTES_MASTERCARD + FUENTES_BANCOS_CO
df_mc = recolectar_noticias(fuentes_mc_total, "Mastercard Intelligence Tracker")

# Filtro post-recolección: eliminar noticias que mencionan Visa como red
# sin mencionar Mastercard — evita falsos positivos de fuentes genéricas
KEYWORDS_EXCLUIR_VISA = [
    "tarjeta visa", "tarjetas visa", "visa débito", "visa crédito",
    "visa debit", "visa credit", "edición visa", "portafolio visa",
    "débito visa", "crédito visa", "visa infinite", "visa platinum",
    "visa gold", "visa signature", "visa classic", "visa electron",
    "lanza tarjeta visa", "lanza tarjetas visa", "lanzó tarjeta visa",
]
if not df_mc.empty:
    def es_noticia_visa_pura(row):
        texto = (row["titulo"] + " " + row.get("resumen", "")).lower()
        tiene_visa_kw = any(kw in texto for kw in KEYWORDS_EXCLUIR_VISA)
        tiene_mc      = "mastercard" in texto
        return tiene_visa_kw and not tiene_mc

    mask_visa = df_mc.apply(es_noticia_visa_pura, axis=1)
    n_excluidas = mask_visa.sum()
    if n_excluidas > 0:
        print(f"   🚫 {n_excluidas} noticias de productos Visa excluidas del módulo MC")
    df_mc = df_mc[~mask_visa].reset_index(drop=True)

if not df_mc.empty:
    print("\n🤖 Clasificando con NLP...")
    resultados_mc = df_mc.apply(
        lambda r: pd.Series(clasificar_articulo(r['titulo'], r['resumen'], LABELS_MC)),
        axis=1
    )
    df_mc[['categoria', 'score']] = resultados_mc
    df_mc['alerta'] = df_mc.apply(
        lambda r: calcular_alerta(r['categoria'], r['score'], 'mc', r['titulo'], r['resumen'], r.get('fuente','')), axis=1
    )
    df_mc = df_mc.sort_values(['alerta', 'score'], ascending=[True, False])
    alertas_altas_mc = df_mc[df_mc['alerta'] == 'ALTA']
    print(f"\n📊 Mastercard Tracker: {len(df_mc)} artículos · {len(alertas_altas_mc)} alertas ALTAS")
else:
    print("⚠️ Sin artículos esta semana en fuentes Mastercard")

# ============================================================
# CELDA 8 — EJECUTAR MÓDULO 2: Fintech Pulse
# ============================================================

df_ft = recolectar_noticias(FUENTES_FINTECH, "Fintech Pulse Colombia")

if not df_ft.empty:
    print("\n🤖 Clasificando con NLP...")
    resultados_ft = df_ft.apply(
        lambda r: pd.Series(clasificar_articulo(r['titulo'], r['resumen'], LABELS_FT)),
        axis=1
    )
    df_ft[['categoria', 'score']] = resultados_ft
    df_ft['alerta'] = df_ft.apply(
        lambda r: calcular_alerta(r['categoria'], r['score'], 'ft', r['titulo'], r['resumen'], r.get('fuente','')), axis=1
    )
    df_ft = df_ft.sort_values(['alerta', 'score'], ascending=[True, False])
    alertas_altas_ft = df_ft[df_ft['alerta'] == 'ALTA']
    print(f"\n📊 Fintech Pulse: {len(df_ft)} artículos · {len(alertas_altas_ft)} alertas ALTAS")
else:
    print("⚠️ Sin artículos esta semana en fuentes Fintech")

# ============================================================
# CELDA 8B — EJECUTAR MÓDULO 3: SFC — Circulares y Aprobaciones
# ============================================================

df_sfc = recolectar_sfc()

if not df_sfc.empty:
    print(f"\n📊 SFC: {len(df_sfc)} registros · todos marcados como ALTA prioridad")
else:
    print("ℹ️ Sin nuevas circulares SFC relevantes detectadas esta semana")

# ============================================================
# CELDA 9B — REPORTE FINAL
# ============================================================

def badge_alerta(nivel):
    colores = {"ALTA": ("#7B1C1C","#FEE2E2"), "MEDIA": ("#78350F","#FEF3C7"), "BAJA": ("#1F2937","#F3F4F6")}
    fg, bg = colores.get(nivel, ("#1F2937","#F3F4F6"))
    return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:99px;font-size:11px;font-weight:600">{nivel}</span>'

def filas_tabla(df, max_rows=10):
    if df.empty:
        return '<tr><td colspan="5" style="color:#6B7280;text-align:center;padding:20px">Sin novedades detectadas</td></tr>'
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    df2 = df.copy()
    df2["_ord"] = df2["alerta"].map(orden).fillna(3)
    if "score" not in df2.columns:
        df2["score"] = 0
    df2 = df2.sort_values(["_ord","score"], ascending=[True,False]).head(max_rows)
    filas = ""
    for _, r in df2.iterrows():
        lnk = r.get("link","")
        tit = f'<a href="{lnk}" style="color:#1A56DB;text-decoration:none">{r["titulo"]}</a>' if lnk else r["titulo"]
        filas += (f'<tr style="border-bottom:1px solid #F3F4F6">'
                  f'<td style="padding:10px 8px;font-size:12px;color:#6B7280;white-space:nowrap">{r["fecha"]}</td>'
                  f'<td style="padding:10px 8px;font-size:13px">{tit}</td>'
                  f'<td style="padding:10px 8px;font-size:12px;color:#374151">{r["fuente"]}</td>'
                  f'<td style="padding:10px 8px;font-size:12px;color:#6B7280">{r.get("categoria","—")}</td>'
                  f'<td style="padding:10px 8px;text-align:center">{badge_alerta(r.get("alerta","BAJA"))}</td></tr>')
    return filas

def resumen_ejecutivo_v2(df_mc, df_ft, df_sfc):
    """Resumen ejecutivo con frase descriptiva — sin listar titulares individuales."""
    items = []

    # Mastercard
    altas_mc = df_mc[df_mc["alerta"]=="ALTA"] if not df_mc.empty else pd.DataFrame()
    if not altas_mc.empty:
        n = len(altas_mc)
        cats = altas_mc["categoria"].value_counts().index.tolist()
        cat_desc = cats[0] if cats else "movimientos estratégicos"
        frase = (f"Se detectaron <b>{n} señal(es)</b> de alta relevancia este mes, principalmente relacionadas con "
                 f"<i>{cat_desc}</i>. Se recomienda revisar antes del próximo comité de liderazgo y evaluar "
                 f"impacto en la estrategia comercial de Visa Colombia.")
        items.append(
            f'<li style="margin-bottom:16px">'
            f'<b>🔴 Mastercard — {n} alerta(s) alta(s)</b><br>'
            f'<span style="font-size:12px;color:#4B5563;line-height:1.6">{frase}</span>'
            f'</li>'
        )
    else:
        items.append(
            '<li style="margin-bottom:16px">✅ <b>Mastercard:</b> '
            '<span style="font-size:12px;color:#4B5563">Sin movimientos de alta relevancia este mes en Colombia y LatAm. '
            'No se requieren acciones inmediatas en el frente competitivo.</span></li>'
        )

    # Fintech Pulse
    altas_ft = df_ft[df_ft["alerta"]=="ALTA"] if not df_ft.empty else pd.DataFrame()
    if not altas_ft.empty:
        n = len(altas_ft)
        tiene_aprobacion = altas_ft["categoria"].str.contains("financiamiento|aprobada|autorizada", na=False).any()
        tiene_ronda = altas_ft["categoria"].str.contains("ronda|inversión", na=False).any()
        if tiene_aprobacion:
            frase = (f"Se identificaron <b>{n} señal(es)</b> que incluyen posibles aprobaciones de nuevas entidades "
                     f"como compañías de financiamiento. Evaluar si representan nuevos competidores o aliados potenciales para Visa.")
        elif tiene_ronda:
            frase = (f"Se detectaron <b>{n} señal(es)</b> relacionadas con rondas de inversión o nuevos players "
                     f"que podrían escalar y convertirse en competidores relevantes para la red.")
        else:
            frase = (f"Se detectaron <b>{n} señal(es)</b> de alta relevancia en el ecosistema fintech "
                     f"colombiano y LatAm. Revisar para identificar oportunidades de partnership o riesgos competitivos.")
        items.append(
            f'<li style="margin-bottom:16px">'
            f'<b>🟠 Fintech Pulse — {n} alerta(s) alta(s)</b><br>'
            f'<span style="font-size:12px;color:#4B5563;line-height:1.6">{frase}</span>'
            f'</li>'
        )
    else:
        items.append(
            '<li style="margin-bottom:16px">✅ <b>Fintech Pulse:</b> '
            '<span style="font-size:12px;color:#4B5563">Sin nuevos players disruptivos ni aprobaciones regulatorias '
            'este mes. Ecosistema estable.</span></li>'
        )

    # SFC
    if not df_sfc.empty:
        n = len(df_sfc)
        frase = (f"La SFC publicó <b>{n} circular(es)</b> relacionadas con autorización o aprobación "
                 f"de nuevas compañías de financiamiento. Revisar para identificar nuevos emisores potenciales "
                 f"que podrían ingresar al mercado de tarjetas en Colombia.")
        items.append(
            f'<li style="margin-bottom:16px">'
            f'<b>🟣 SFC — {n} circular(es) detectada(s)</b><br>'
            f'<span style="font-size:12px;color:#4B5563;line-height:1.6">{frase}</span>'
            f'</li>'
        )
    else:
        items.append(
            '<li style="margin-bottom:16px">✅ <b>SFC:</b> '
            '<span style="font-size:12px;color:#4B5563">Sin nuevas aprobaciones de compañías de financiamiento '
            'detectadas este mes.</span></li>'
        )

    return "".join(items)


def generar_reporte_v2(df_mc, df_ft, df_sfc):
    mes_str = HOY.strftime("%B %Y").capitalize()
    n_mc  = len(df_mc)  if not df_mc.empty  else 0
    n_ft  = len(df_ft)  if not df_ft.empty  else 0
    n_sfc = len(df_sfc) if not df_sfc.empty else 0
    altas = ((len(df_mc[df_mc["alerta"]=="ALTA"]) if not df_mc.empty else 0) +
             (len(df_ft[df_ft["alerta"]=="ALTA"]) if not df_ft.empty else 0) + n_sfc)
    alerta_color = "#DC2626" if altas > 0 else "#16A34A"

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#F3F4F6;margin:0;padding:20px}}
.container{{max-width:760px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #E5E7EB}}
.header{{background:#1A56DB;color:#fff;padding:28px 32px}}
.header h1{{margin:0;font-size:21px;font-weight:700;letter-spacing:0.2px}}
.header p{{margin:7px 0 0;font-size:12px;color:#BFDBFE}}
.kpis{{display:flex;border-bottom:1px solid #E5E7EB}}
.kpi{{flex:1;padding:16px 20px;border-right:1px solid #E5E7EB;text-align:center}}
.kpi:last-child{{border-right:none}}
.kpi-n{{font-size:26px;font-weight:700;color:#1e3a8a}}
.kpi-l{{font-size:11px;color:#6B7280;margin-top:3px}}
.section{{padding:22px 32px;border-bottom:1px solid #F3F4F6}}
.stitle{{font-size:12px;font-weight:700;color:#111827;margin:0 0 3px;text-transform:uppercase;letter-spacing:0.05em}}
.sdesc{{font-size:12px;color:#6B7280;margin:0 0 14px;line-height:1.55}}
.exec-box{{background:#EFF6FF;border-left:4px solid #1A56DB;border-radius:0 8px 8px 0;padding:16px 20px}}
.exec-box ul{{margin:0;padding-left:0;list-style:none}}
table{{width:100%;border-collapse:collapse}}
th{{text-align:left;font-size:11px;color:#9CA3AF;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;padding:8px;border-bottom:2px solid #E5E7EB}}
.badge{{display:inline-block;padding:3px 10px;border-radius:99px;font-size:11px;font-weight:600;margin-bottom:8px}}
.footer{{padding:16px 32px;font-size:11px;color:#9CA3AF;text-align:center;background:#F9FAFB}}
</style></head><body>
<div class="container">
  <div class="header">
    <h1>Visa Market Intelligence Report</h1>
    <p>{mes_str} · Generado automáticamente · Business Development · Visa Colombia</p>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="kpi-n">{n_mc}</div><div class="kpi-l">señales Mastercard</div></div>
    <div class="kpi"><div class="kpi-n">{n_ft}</div><div class="kpi-l">señales fintech</div></div>
    <div class="kpi"><div class="kpi-n">{n_sfc}</div><div class="kpi-l">circulares SFC</div></div>
    <div class="kpi"><div class="kpi-n" style="color:{alerta_color}">{altas}</div><div class="kpi-l">alertas ALTAS</div></div>
  </div>
  <div class="section">
    <div class="stitle">Resumen ejecutivo</div>
    <div class="sdesc">Prioridades y análisis basados únicamente en alertas de nivel ALTO de los 3 módulos.</div>
    <div class="exec-box"><ul>{resumen_ejecutivo_v2(df_mc, df_ft, df_sfc)}</ul></div>
  </div>
  <div class="section">
    <span class="badge" style="background:#FEE2E2;color:#7B1C1C">MÓDULO 1 · Mastercard Intelligence Tracker</span>
    <div class="sdesc">Monitoreo de lanzamientos, alianzas y movimientos estratégicos de Mastercard en Colombia y LatAm. Lanzamientos con banco colombiano → ALTA automática. Noticias globales sin contexto colombiano → BAJA. Máx. 10 resultados priorizando alertas altas.</div>
    <table><thead><tr><th>Fecha</th><th>Titular</th><th>Fuente</th><th>Categoría</th><th>Alerta</th></tr></thead><tbody>{filas_tabla(df_mc)}</tbody></table>
  </div>
  <div class="section">
    <span class="badge" style="background:#D1FAE5;color:#065F46">MÓDULO 2 · Fintech Pulse Colombia</span>
    <div class="sdesc">Radar del ecosistema fintech colombiano y LatAm: nuevos players, rondas de inversión, expansiones y regulación. Fintechs aprobadas como compañía de financiamiento → ALTA automática. Máx. 10 resultados priorizando alertas altas.</div>
    <table><thead><tr><th>Fecha</th><th>Titular</th><th>Fuente</th><th>Categoría</th><th>Alerta</th></tr></thead><tbody>{filas_tabla(df_ft)}</tbody></table>
  </div>
  <div class="section">
    <span class="badge" style="background:#EDE9FE;color:#4C1D95">MÓDULO 3 · SFC — Circulares y Aprobaciones</span>
    <div class="sdesc">Seguimiento directo de la Superintendencia Financiera de Colombia. Detecta circulares y resoluciones sobre autorización de nuevas compañías de financiamiento. Todos los registros son ALTA por definición. Máx. 10 registros.</div>
    <table><thead><tr><th>Fecha</th><th>Circular / Noticia</th><th>Fuente</th><th>Categoría</th><th>Alerta</th></tr></thead><tbody>{filas_tabla(df_sfc)}</tbody></table>
  </div>
  <div class="footer">Visa Market Intelligence System · {HOY.strftime('%d/%m/%Y %H:%M')} · Business Development · Visa Colombia</div>
</div></body></html>"""

reporte_html = generar_reporte_v2(
    df_mc  if "df_mc"  in dir() else pd.DataFrame(),
    df_ft  if "df_ft"  in dir() else pd.DataFrame(),
    df_sfc if "df_sfc" in dir() else pd.DataFrame(),
)
print("✅ Reporte generado — corre la siguiente celda para preview o email")

# ============================================================
# CELDA 9C — COMPETITIVE PULSE
# ============================================================

def calcular_scorecard(df_mc, df_ft, df_sfc):
    def safe_len(df, mask=None):
        if df.empty: return 0
        return len(df[mask]) if mask is not None else len(df)

    mc_altas = safe_len(df_mc, df_mc["alerta"].eq("ALTA")) if not df_mc.empty else 0
    mc_lanz  = safe_len(df_mc,
        df_mc["categoria"].str.contains("lanzamiento|producto", case=False, na=False)
    ) if not df_mc.empty else 0

    BANCOS = ["davivienda","bancolombia","bbva","nequi","daviplata",
              "rappi","scotiabank","popular","colpatria","falabella"]
    altas_mc = df_mc[df_mc["alerta"]=="ALTA"] if not df_mc.empty else pd.DataFrame()
    bancos_vistos = set()
    if not altas_mc.empty:
        for _, r in altas_mc.iterrows():
            t = (r["titulo"] + " " + r.get("resumen","")).lower()
            for b in BANCOS:
                if b in t: bancos_vistos.add(b)

    reg_total = safe_len(df_sfc) + (safe_len(df_ft,
        df_ft["categoria"].str.contains("regulación|SFC|norma|financiamiento", case=False, na=False)
    ) if not df_ft.empty else 0)
    nuevos   = safe_len(df_ft,
        df_ft["categoria"].str.contains("nueva fintech|neobank|ronda|inversión|aprobada", case=False, na=False)
    ) if not df_ft.empty else 0
    ft_altas = safe_len(df_ft, df_ft["alerta"].eq("ALTA")) if not df_ft.empty else 0

    return {
        "mc": [
            {"label": "Alertas altas",      "val": mc_altas,           "max": 10, "unidad": "señales"},
            {"label": "Lanzamientos",        "val": mc_lanz,            "max": 8,  "unidad": "productos"},
            {"label": "Bancos mencionados",  "val": len(bancos_vistos), "max": 6,  "unidad": "bancos CO"},
        ],
        "eco": [
            {"label": "Nuevos players",      "val": nuevos,    "max": 8, "unidad": "fintechs"},
            {"label": "Mov. regulatorios",   "val": reg_total, "max": 6, "unidad": "circulares"},
            {"label": "Alertas fintech",     "val": ft_altas,  "max": 8, "unidad": "señales"},
        ],
    }


def barra_html(val, max_val):
    pct  = min(100, int((val / max(max_val, 1)) * 100))
    color = "#DC2626" if pct >= 70 else ("#F59E0B" if pct >= 40 else "#93C5FD")
    # tabla de 1 fila para compatibilidad email
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:6px">'
        '<tr>'
        '<td width="' + str(pct) + '%" height="5" bgcolor="' + color + '" style="border-radius:3px;font-size:0;line-height:0">&nbsp;</td>'
        + (('<td width="' + str(100-pct) + '%" height="5" bgcolor="#E5E7EB" style="font-size:0;line-height:0">&nbsp;</td>') if pct < 100 else '')
        + '</tr></table>'
    )


def filas_metricas(items):
    html = ""
    for d in items:
        html += (
            '<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:14px">'
            '<tr>'
            '<td style="font-size:12px;color:#6B7280;padding-bottom:2px">' + d["label"] + '</td>'
            '<td align="right" style="padding-bottom:2px;white-space:nowrap">'
            '<span style="font-size:20px;font-weight:700;color:#111827;line-height:1">' + str(d["val"]) + '</span>'
            '&nbsp;<span style="font-size:10px;color:#9CA3AF">' + d["unidad"] + '</span>'
            '</td>'
            '</tr>'
            '<tr><td colspan="2">' + barra_html(d["val"], d["max"]) + '</td></tr>'
            '</table>'
        )
    return html


def generar_scorecard_compacto(scores):
    mes_str = HOY.strftime("%B %Y").capitalize()
    total   = sum(d["val"] for d in scores["mc"] + scores["eco"])

    mc_rows  = filas_metricas(scores["mc"])
    eco_rows = filas_metricas(scores["eco"])

    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;background:#fff">'

        # ── Header ──────────────────────────────────────────────────────────
        '<tr>'
        '<td colspan="3" bgcolor="#F9FAFB" style="padding:11px 20px;border-bottom:1px solid #E5E7EB">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        '<td style="font-size:11px;font-weight:700;color:#111827;text-transform:uppercase;letter-spacing:0.06em">Competitive Pulse</td>'
        '<td align="right" style="font-size:11px;color:#9CA3AF">' + mes_str + ' &middot; ' + str(total) + ' señales analizadas</td>'
        '</tr></table>'
        '</td>'
        '</tr>'

        # ── Columnas ─────────────────────────────────────────────────────────
        '<tr>'

        # Columna Mastercard
        '<td width="46%" valign="top" style="padding:16px 16px 16px 20px;border-right:1px solid #E5E7EB">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0">'

        # Badge
        '<tr><td style="padding-bottom:10px">'
        '<span style="background:#FEE2E2;color:#991B1B;font-size:10px;font-weight:700;'
        'padding:3px 9px;border-radius:99px;text-transform:uppercase;letter-spacing:0.06em">Mastercard</span>'
        '</td></tr>'

        # Descripción
        '<tr><td style="font-size:11px;color:#9CA3AF;line-height:1.5;padding-bottom:14px">'
        'Señales de lanzamiento de productos y expansión con bancos emisores en Colombia.'
        '</td></tr>'

        # Métricas
        '<tr><td>' + mc_rows + '</td></tr>'
        '</table>'
        '</td>'

        # Separador
        '<td width="8" style="padding:0"></td>'

        # Columna Ecosistema
        '<td width="46%" valign="top" style="padding:16px 20px 16px 16px">'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0">'

        # Badge
        '<tr><td style="padding-bottom:10px">'
        '<span style="background:#D1FAE5;color:#065F46;font-size:10px;font-weight:700;'
        'padding:3px 9px;border-radius:99px;text-transform:uppercase;letter-spacing:0.06em">Ecosistema</span>'
        '</td></tr>'

        # Descripción
        '<tr><td style="font-size:11px;color:#9CA3AF;line-height:1.5;padding-bottom:14px">'
        'Presión de nuevos players fintech y movimientos regulatorios que impactan emisores Visa.'
        '</td></tr>'

        # Métricas
        '<tr><td>' + eco_rows + '</td></tr>'
        '</table>'
        '</td>'

        '</tr>'
        '</table>'
    )


# ── Calcular e insertar ──────────────────────────────────────────────────────
scores         = calcular_scorecard(
    df_mc  if "df_mc"  in dir() else pd.DataFrame(),
    df_ft  if "df_ft"  in dir() else pd.DataFrame(),
    df_sfc if "df_sfc" in dir() else pd.DataFrame(),
)
scorecard_html = generar_scorecard_compacto(scores)

seccion_sc = (
    '<div style="padding:0 32px 22px">'
    + scorecard_html
    + '</div>'
)

ANCLA = '</div>\n  </div>\n  <div class="section">\n    <span class="badge" style="background:#FEE2E2'
if ANCLA in reporte_html:
    reporte_html = reporte_html.replace(
        ANCLA,
        '</div>\n' + seccion_sc + '\n  </div>\n  <div class="section">\n    <span class="badge" style="background:#FEE2E2',
        1
    )
else:
    ANCLA2 = "MÓDULO 1 · Mastercard Intelligence Tracker"
    reporte_html = reporte_html.replace(ANCLA2, seccion_sc + ANCLA2, 1)

print("✅ Competitive Pulse generado")
print()
print("  MASTERCARD")
for d in scores["mc"]:
    bar = "█" * min(5, round(d["val"] / max(d["max"],1) * 5))
    bar += "░" * (5 - len(bar))
    print(f"    {d['label']:<24} {bar}  {d['val']} {d['unidad']}")
print()
print("  ECOSISTEMA")
for d in scores["eco"]:
    bar = "█" * min(5, round(d["val"] / max(d["max"],1) * 5))
    bar += "░" * (5 - len(bar))
    print(f"    {d['label']:<24} {bar}  {d['val']} {d['unidad']}")


# ── Punto de entrada ──────────────────────────────────────────────────
def enviar_reporte_email(html_content, gmail_user, gmail_password, email_destino):
    mes_str = HOY.strftime('%B %Y').capitalize()
    asunto = f"📊 Visa Market Intelligence Report — {mes_str}"
    msg = MIMEMultipart('alternative')
    msg['Subject'] = asunto
    msg['From']    = gmail_user
    msg['To']      = email_destino
    texto_plano = f"Visa Market Intelligence Report — {mes_str}"
    msg.attach(MIMEText(texto_plano, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, email_destino, msg.as_string())
        print(f"✅ Email enviado exitosamente a {email_destino}")
        print(f"   Asunto: {asunto}")
    except smtplib.SMTPAuthenticationError:
        print("❌ Error de autenticación Gmail.")
        print("   → Verifica GMAIL_USER y GMAIL_PASSWORD en GitHub Secrets")
    except Exception as e:
        print(f"❌ Error enviando email: {e}")
        raise


if __name__ == "__main__":
    print(f"\n🚀 Visa Market Intelligence — {HOY.strftime('%B %Y')}")
    print(f"   Período: {SEMANA_ATRAS.strftime('%d/%m/%Y')} → {HOY.strftime('%d/%m/%Y')}")
    if not GMAIL_USER:
        print("❌ Faltan credenciales. Configura GMAIL_USER, GMAIL_PASSWORD, EMAIL_DESTINO.")
    else:
        enviar_reporte_email(reporte_html, GMAIL_USER, GMAIL_PASSWORD, EMAIL_DESTINO)
