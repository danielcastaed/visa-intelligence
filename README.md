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
