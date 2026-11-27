# Visa Market Intelligence — Colombia

Inteligencia competitiva automatizada: participación de mercado, facturación y salud de cartera de Visa vs. Mastercard en Colombia, actualizada mensualmente con datos oficiales de la Superintendencia Financiera (SFC).

[![Ver dashboard en vivo](https://img.shields.io/badge/dashboard-en%20vivo-1A1F71?style=for-the-badge)](https://danielcastaed.github.io/visa-intelligence/)
[![Monthly Market Intelligence Report](https://github.com/danielcastaed/visa-intelligence/workflows/Monthly%20Market%20Intelligence%20Report/badge.svg)](https://github.com/danielcastaed/visa-intelligence/actions/workflows/monthly_report.yml)
[![Visa Market Intelligence Report](https://github.com/danielcastaed/visa-intelligence/workflows/Visa%20Market%20Intelligence%20Report/badge.svg)](https://github.com/danielcastaed/visa-intelligence/actions/workflows/visa_intelligence.yml)

## Qué es

Un sistema que corre solo, sin intervención manual: cada mes descarga datos públicos de la SFC, calcula participación de mercado y métricas de cartera para Visa y Mastercard, publica un dashboard interactivo, y envía un resumen ejecutivo por correo.

## Qué mide

- **Market share** — total, crédito y débito, con contribución por banco
- **Facturación** — nacional, exterior y total, por franquicia
- **Tarjetas vigentes** y ticket promedio
- **Salud de cartera** — utilización de cupo, ratio de mora, tasa de castigo, churn

## Cómo funciona

```
SFC (datos.gov.co) → SFC_Analytics.ipynb → dashboard (docs/, GitHub Pages)
                                          → report/generate_report.py → email
```

Dos pipelines corren en GitHub Actions:

| Workflow | Cadencia | Qué entrega |
|---|---|---|
| `monthly_report.yml` | Primer martes del mes | Dashboard actualizado + email con snapshot de market share |
| `visa_intelligence.yml` | Día 1 del mes | Email con tracking de noticias/lanzamientos Visa–Mastercard |
| `mexico_dashboard.yml` | Cada lunes | Dashboard México actualizado con datos de Banxico |

## Resumen animado

[`docs/resumen.html`](https://danielcastaed.github.io/visa-intelligence/resumen.html) cuenta el mercado en tres relatos cortos y animados, pensados para presentar:

- **Historia** — de 2015 al último mes: crecimiento del mercado, cuota de Visa vs. Mastercard, mezcla crédito/débito y tarjetas vigentes.
- **Año a la fecha** — acumulado del año contra el mismo período del año anterior, con aporte por banco.
- **Mes** — último mes contra el anterior y contra el mismo mes del año pasado.

Los filtros de la parte inferior permiten elegir el **producto** (total, crédito o débito), el **banco** y el **mes de corte** (últimos 12 meses; con un banco solo está el último mes). Los textos de cada combinación se precalculan al generar la página.

Se genera con `python report/generate_resumen.py` a partir de los datos embebidos en el dashboard (`docs/index.html`) y se regenera solo en el workflow mensual. Los textos salen de plantillas con las cifras del período (sin IA ni llamadas externas); la plantilla visual está en `report/resumen_template.html`.

## México (estimado con datos de Banxico)

[`docs/mexico/`](https://danielcastaed.github.io/visa-intelligence/mexico/) replica la estructura del dashboard de Colombia para México: snapshot, market share, share por producto, facturación, tarjetas vigentes (histórico desde 2006), crecimiento YoY, sensibilidad por escenario, contribución por banco, participación por emisor, mapa de calor, concentración (HHI) y una vista Deep Dive con facturación mensual. Filtros: período (anual / trimestral), producto (crédito / débito / total) y escenario. Las tarjetas por marca solo existen trimestrales en Banxico; la facturación total por producto se ve mensual.

A diferencia de la SFC, **ninguna fuente pública mexicana reporta facturación por marca**, así que el share es un estimado:

- **Facturación por producto**: Banxico SIE, cuadros CF888 y CF914 (monto operado con tarjetas de crédito y débito).
- **Tarjetas por marca y emisor**: Banxico SIE CF256, con emisores anonimizados por letra.
- **Peso de cada banco en crédito**: saldo de los Indicadores Básicos de Tarjetas de Crédito de Banxico.
- Las letras de CF256 se emparejan con bancos por tamaño, mezcla de marcas, fechas de entrada/salida y crecimiento. La tabla de identificación en el dashboard muestra la evidencia y la confianza de cada una.

```
Banxico SIE → mexico/fetch_banxico.py → mexico/data/ ┐
                 mexico/inputs.json (manual) ─────────┴→ mexico/model.py → report/generate_mexico.py → docs/mexico/index.html
```

El workflow `mexico_dashboard.yml` corre cada lunes (y cada vez que cambia el código del modelo o la plantilla): descarga CF256, CF888 y CF914, recalcula y publica solo si hay datos nuevos. Lo único manual son los pesos por banco de los Indicadores Básicos (PDF semestral de Banxico) en `mexico/inputs.json`. Opcional: un secret `BANXICO_TOKEN` (token gratuito del SIE) sirve de respaldo si el endpoint público falla.

Para correrlo local: `python mexico/fetch_banxico.py && python mexico/model.py && python report/generate_mexico.py`.

## Stack

Python (pandas) · Jupyter + Plotly · GitHub Actions · GitHub Pages · Gmail SMTP

## Fuente de datos

[Superintendencia Financiera de Colombia](https://www.datos.gov.co) — cifras públicas de tarjetas de crédito y débito por entidad.

---

## Para reproducirlo

<details>
<summary>Setup (5 minutos)</summary>

### 1. Configurar credenciales (GitHub Secrets)
En **Settings → Secrets and variables → Actions**, crear:

| Secret | Valor |
|---|---|
| `GMAIL_USER` | tu correo Gmail |
| `GMAIL_APP_PASS` | App Password de 16 caracteres |
| `REPORT_TO` | destinatario del reporte |

### 2. Correr manualmente
**Actions** → seleccionar el workflow → **Run workflow**.

### 3. Automatización
Ambos workflows ya están programados — no requieren nada más una vez configurados los secrets.

</details>
