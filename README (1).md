# 📊 Visa Market Intelligence — Reporte Automático

Envío mensual automático del snapshot comparativo Visa vs Mastercard
y contribución al cambio en Market Share, con datos frescos de la SFC.

---

## Estructura

```
.github/
  workflows/
    monthly_report.yml   ← GitHub Action (corre día 15 de cada mes)
report/
  generate_report.py     ← Descarga SFC, calcula métricas, genera HTML
  send_email.py          ← Envía el HTML por Gmail SMTP
```

---

## Setup (una sola vez)

### 1. Crear un Gmail App Password

> Necesitas activar la verificación en 2 pasos en tu cuenta Gmail primero.

1. Entra a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Selecciona **"Correo"** como app y **"Otro"** como dispositivo → ponle nombre "visa-report"
3. Copia las **16 letras** que te genera (ej: `abcd efgh ijkl mnop`)

### 2. Agregar los 3 GitHub Secrets

En tu repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret          | Valor                                    |
|-----------------|------------------------------------------|
| `GMAIL_USER`    | Tu dirección Gmail (ej: `tu@gmail.com`)  |
| `GMAIL_APP_PASS`| El App Password de 16 caracteres         |
| `REPORT_TO`     | `dacastan@visa.com`                      |

### 3. Habilitar GitHub Actions

En tu repo → **Actions** → confirmar que está habilitado.

---

## Uso

### Automático
El workflow corre el **día 15 de cada mes a las 8am hora Colombia**.
La SFC publica los datos del mes anterior alrededor del día 10–12,
así que el día 15 ya hay datos frescos disponibles.

### Manual (cuando quieras)
1. Ve a **Actions → Monthly Market Intelligence Report**
2. Clic en **"Run workflow"**
3. Opcional: marca **dry_run = true** para generar el reporte sin enviarlo

### Ver el reporte generado
Cada ejecución sube el HTML como **artifact** (guardado 90 días):
Actions → selecciona el run → sección "Artifacts" → descarga `market-report-*`

---

## Qué incluye el reporte

**Por mes (último período disponible vs mismo mes año anterior):**
- Market Share Visa y Mastercard
- Facturación total (COP)
- N° transacciones
- Tarjetas vigentes
- Ticket promedio

**Contribución al cambio en MS (mensual y anual):**
- Δ pp por franquicia vs período anterior

---

## Personalización

Para cambiar el día de envío, edita el cron en `.github/workflows/monthly_report.yml`:
```yaml
- cron: "0 13 15 * *"   # día 15, 8am Colombia
```
Formato: `minuto hora día-del-mes mes día-semana` (todo en UTC).
