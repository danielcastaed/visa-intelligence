# Visa Market Intelligence System

Reporte mensual automático de inteligencia competitiva para Visa Colombia.

## Configuración (5 minutos)

### 1. Crear repositorio en GitHub
- Ve a github.com → New repository → nombre: `visa-intelligence` → Private → Create

### 2. Subir archivos
Sube estos 3 archivos al repositorio:
- `visa_intelligence.py`
- `requirements.txt`
- `.github/workflows/visa_intelligence.yml`

### 3. Configurar credenciales (GitHub Secrets)
En tu repositorio: **Settings → Secrets and variables → Actions → New repository secret**

Crear 3 secrets:
| Nombre | Valor |
|--------|-------|
| `GMAIL_USER` | tu_correo@gmail.com |
| `GMAIL_PASSWORD` | tu App Password de 16 caracteres |
| `EMAIL_DESTINO` | dacastan@visa.com |

### 4. Correr manualmente la primera vez
- Ve a la pestaña **Actions** en tu repositorio
- Clic en **Visa Market Intelligence Report**
- Clic en **Run workflow** → **Run workflow**
- En ~10 minutos llega el email

### 5. Automatización mensual
El reporte corre automáticamente el **día 1 de cada mes a las 7am Colombia**.
No necesitas hacer nada más.

## Modificar el período de análisis
En `visa_intelligence.py`, línea ~20:
```python
SEMANA_ATRAS = HOY - timedelta(days=30)  # cambiar días aquí
```

## Costos
- GitHub Actions: **gratis** (2,000 minutos/mes incluidos, este script usa ~15 min)
- Todo lo demás: **gratis**
