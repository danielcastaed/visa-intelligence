"""
send_email.py
Envía el reporte por email con el dashboard interactivo como adjunto.
"""
import os, sys, smtplib, glob
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime

def send_report(html_path: str):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASS"]
    to_addr    = os.environ.get("REPORT_TO", "dacastan@visa.com")

    with open(html_path, "r", encoding="utf-8") as f:
        html_body = f.read()

    periodo = datetime.now().strftime("%Y-%m")
    subject = f"Visa Market Intelligence — Tarjetas de Pago Colombia · {periodo}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"Market Intelligence <{gmail_user}>"
    msg["To"]      = to_addr

    # Cuerpo HTML
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Adjunto: el dashboard interactivo generado por el notebook
    dashboard_candidates = [
        "sfc_dashboard.html",            # generado por el notebook
        "sfc_dashboard_PREVIEW.html",    # fallback
    ]
    dashboard_path = next((c for c in dashboard_candidates if os.path.exists(c)), None)

    if dashboard_path:
        with open(dashboard_path, "rb") as f:
            payload = f.read()
        att = MIMEBase("text", "html")
        att.set_payload(payload)
        encoders.encode_base64(att)
        att.add_header("Content-Disposition",
                       f"attachment; filename=SFC_Dashboard_{periodo}.html")
        msg.attach(att)
        size_mb = len(payload) / 1024 / 1024
        print(f"  Dashboard adjunto: {dashboard_path} ({size_mb:.1f} MB)")
    else:
        print("  Aviso: no se encontró el dashboard HTML para adjuntar")

    print(f"Enviando a {to_addr}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to_addr, msg.as_string())
    print("✅ Email enviado correctamente.")

if __name__ == "__main__":
    html_path = sys.argv[1] if len(sys.argv) > 1 else "report/output_report.html"
    send_report(html_path)
