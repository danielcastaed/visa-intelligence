"""
send_email.py
Envía el reporte HTML como email via Gmail SMTP.

Variables de entorno requeridas (GitHub Secrets):
  GMAIL_USER      → tu dirección Gmail (ej: tu.nombre@gmail.com)
  GMAIL_APP_PASS  → App Password de 16 caracteres (ver README)
  REPORT_TO       → destinatario (dacastan@visa.com)
"""

import os
import sys
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

def send_report(html_path: str):
    gmail_user  = os.environ["GMAIL_USER"]
    gmail_pass  = os.environ["GMAIL_APP_PASS"]
    to_addr     = os.environ.get("REPORT_TO", "dacastan@visa.com")

    # Leer HTML del reporte
    with open(html_path, "r", encoding="utf-8") as f:
        html_body = f.read()

    # Extraer período del nombre del archivo o del HTML
    periodo = datetime.now().strftime("%Y-%m")
    if "período:" in html_body:
        try:
            idx = html_body.index("período:") + 9
            periodo = html_body[idx:idx+7].strip()
        except Exception:
            pass

    subject = f"📊 Market Intelligence Report — Tarjetas de Crédito Colombia · {periodo}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Market Intelligence <{gmail_user}>"
    msg["To"]      = to_addr

    # Parte HTML
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Adjuntar también el HTML como archivo
    attachment = MIMEBase("text", "html")
    attachment.set_payload(html_body.encode("utf-8"))
    encoders.encode_base64(attachment)
    attachment.add_header(
        "Content-Disposition",
        f"attachment; filename=visa_market_report_{periodo}.html"
    )
    msg.attach(attachment)

    # Enviar
    print(f"Enviando reporte a {to_addr}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to_addr, msg.as_string())
    print("✅ Reporte enviado correctamente.")


if __name__ == "__main__":
    html_path = sys.argv[1] if len(sys.argv) > 1 else "report/output_report.html"
    send_report(html_path)
