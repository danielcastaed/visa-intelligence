"""Descarga de Banxico los insumos que cambian del modelo México.

- CF256: tarjetas vigentes por marca (Visa / Mastercard / otras) y emisor
  anonimizado (letras), crédito y débito, trimestral.
- CF888 / CF914: monto operado con tarjetas de crédito y débito (diario),
  sumado por mes, trimestre y año.

Escribe:
  mexico/data/banxico_cf256.json
  mexico/data/banxico_montos.json

Método principal: los endpoints públicos del SIE que usa la propia página del
cuadro (sin token). Si falla y existe la variable de entorno BANXICO_TOKEN, usa
la API oficial SIE REST (token gratuito en
https://www.banxico.org.mx/SieAPIRest/service/v1/token).

Uso:  python mexico/fetch_banxico.py
"""
import datetime
import html as htmlmod
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
BASE = "https://www.banxico.org.mx"
UA = {"User-Agent": "Mozilla/5.0 (visa-intelligence; +https://github.com/danielcastaed/visa-intelligence)"}
TOKEN = os.environ.get("BANXICO_TOKEN", "").strip()

# Montos operados (diarios, pesos): CF888 (2009 - dic 2022, discontinuado) y CF914 (dic 2022 en adelante)
MONTOS = {
    "cf888": {"debito": "SF335896,CF888,2", "credito": "SF335897,CF888,3"},
    "cf914": {"debito": "SF351085,CF914,2", "credito": "SF351086,CF914,3"},
}

# Estructura de nodos del cuadro CF256
# nodo_<producto>_0_<marca>[_<emisor>]; producto 0=crédito, 1=débito; marca 0=total,1=MC,2=Visa,3=otras
PRODUCTO = {"0": "credito", "1": "debito"}
MARCA = {"0": "total", "1": "mc", "2": "visa", "3": "otras"}

session = requests.Session()
session.headers.update(UA)


def get(url, **kw):
    for intento in range(4):
        try:
            r = session.get(url, timeout=60, **kw)
            if r.status_code == 200:
                return r
            print(f"  HTTP {r.status_code} en {url}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  error {e} en {url}", file=sys.stderr)
        time.sleep(2 * (intento + 1))
    raise RuntimeError(f"No se pudo descargar {url}")


def series_map():
    """Lee el cuadro CF256 y devuelve [(nodo, serie, param, etiqueta)]."""
    url = f"{BASE}/SieInternet/consultarDirectorioInternetAction.do?sector=21&accion=consultarCuadro&idCuadro=CF256&locale=es"
    try:
        r = get(url)
        txt = r.content.decode("iso-8859-1", errors="replace")
        pat = re.compile(
            r'id="graph_(nodo_[\d_]+)_(SF\d+)"[^>]*?data-url="[^"]*?s=([^&"]+)[^"]*"[^>]*>\s*<span class="sr-only">(.*?)</span>',
            re.S)
        out = []
        for nodo, sf, param, lbl in pat.findall(txt):
            if not re.match(r"nodo_[01]_0_[0-3]", nodo):
                continue
            lbl = re.sub(r"\s+", " ", htmlmod.unescape(lbl)).strip()
            lbl = re.sub(r"(?i)^mostrar gr.fica de\s+la serie\s+", "", lbl).strip()
            depth = len(nodo.split("_"))
            out.append({"nodo": nodo, "serie": sf, "param": param, "etiqueta": lbl if depth == 5 else "TOTAL"})
        if len(out) >= 100:
            print(f"Mapa CF256 leído del cuadro: {len(out)} series")
            with open(os.path.join(DATA, "cf256_series_map.json"), "w", encoding="utf-8") as f:
                json.dump({"_doc": f"Mapa de series del cuadro CF256 (extraído {datetime.date.today()}).", "series": out},
                          f, ensure_ascii=False, indent=0)
            return out
        print(f"Aviso: solo {len(out)} series en el cuadro; uso el respaldo", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"Aviso: no se pudo leer el cuadro CF256 ({e}); uso el respaldo", file=sys.stderr)
    with open(os.path.join(DATA, "cf256_series_map.json"), encoding="utf-8") as f:
        return json.load(f)["series"]


def fetch_public(param):
    r = get(f"{BASE}/SieInternet/consultaSerieGrafica.do", params={"s": param, "versionSerie": "LA-MAS-RECIENTE", "l": "es"})
    vals = r.json()["valores"]
    return [(d, v) for d, v in vals if v is not None and v != -989898]


def fetch_rest(serie):
    r = get(f"{BASE}/SieAPIRest/service/v1/series/{serie}/datos", headers={"Bmx-Token": TOKEN, "Accept": "application/json"})
    datos = r.json()["bmx"]["series"][0].get("datos", [])
    out = []
    for d in datos:
        if d["dato"] in ("N/E", ""):
            continue
        dd, mm, yy = d["fecha"].split("/")
        out.append((f"{yy}-{mm}-{dd}", float(d["dato"].replace(",", ""))))
    return out


def fetch(param):
    serie = param.split(",")[0]
    try:
        return fetch_public(param)
    except Exception as e:  # noqa: BLE001
        if not TOKEN:
            raise
        print(f"  público falló para {serie} ({e}); uso SIE REST", file=sys.stderr)
        return fetch_rest(serie)


def main():
    os.makedirs(DATA, exist_ok=True)
    smap = series_map()

    cf256 = {"credito": {"totales": {}, "letras": {}}, "debito": {"totales": {}, "letras": {}}}
    fechas = set()
    for i, s in enumerate(smap, 1):
        parts = s["nodo"].split("_")          # nodo, prod, 0, marca, [emisor]
        prod, marca = PRODUCTO[parts[1]], MARCA[parts[3]]
        vals = fetch(s["param"])
        serie = {d: int(round(v)) for d, v in vals if d >= "2006-01-01"}
        fechas.update(serie)
        if len(parts) == 4:
            cf256[prod]["totales"][marca] = serie
        else:
            cf256[prod]["letras"].setdefault(s["etiqueta"], {})[marca] = serie
        if i % 25 == 0:
            print(f"  {i}/{len(smap)} series")
        time.sleep(0.15)
    cf256["fechas"] = sorted(fechas)
    cf256["descargado"] = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    with open(os.path.join(DATA, "banxico_cf256.json"), "w", encoding="utf-8") as f:
        json.dump(cf256, f, ensure_ascii=False, separators=(",", ":"))
    print(f"CF256: {len(smap)} series, último corte {cf256['fechas'][-1]}")

    montos = {"unidad": "miles de millones de pesos"}
    ultima = ""
    for fuente, prods in MONTOS.items():
        montos[fuente] = {}
        for prod, param in prods.items():
            agg = {"anual": {}, "trimestral": {}, "mensual": {}}
            for d, v in fetch(param):
                y, m = d[:4], int(d[5:7])
                keys = {"anual": y, "trimestral": f"{y}-T{(m - 1) // 3 + 1}", "mensual": d[:7]}
                for g, k in keys.items():
                    agg[g][k] = agg[g].get(k, 0) + v / 1e9
                if fuente == "cf914":
                    ultima = max(ultima, d)
            montos[fuente][prod] = {g: {k: round(v, 3) for k, v in sorted(s.items())} for g, s in agg.items()}
    montos["ultima_fecha"] = ultima
    with open(os.path.join(DATA, "banxico_montos.json"), "w", encoding="utf-8") as f:
        json.dump(montos, f, ensure_ascii=False, indent=1)
    print(f"Montos: CF888 + CF914 hasta {ultima}")


if __name__ == "__main__":
    main()
