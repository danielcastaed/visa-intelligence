"""
send_email.py
Envía el reporte mensual por email con link al dashboard en GitHub Pages.
El dashboard ya no se adjunta — se publica en GitHub Pages y el email incluye el link.
"""
import os, sys, smtplib, re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

PAGES_URL = "https://danielcastaed.github.io/visa-intelligence/"

def send_report(html_path: str):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASS"]
    to_addr    = os.environ.get("REPORT_TO", "dacastan@visa.com")

    with open(html_path, "r", encoding="utf-8") as f:
        html_body = f.read()

    # Inject dashboard link button before closing tag
    link_block = (
        '\n  <div style="text-align:center;padding:20px 0 12px">\n'
        '    <a href="' + PAGES_URL + '"\n'
        '       style="display:inline-block;padding:12px 32px;background:#1A1F71;color:#fff;\n'
        '              font-size:14px;font-weight:700;border-radius:8px;text-decoration:none;\n'
        '              letter-spacing:.3px">\n'
        '      Ver dashboard interactivo\n'
        '    </a>\n'
        '    <div style="font-size:10px;color:#94A3B8;margin-top:8px">' + PAGES_URL + '</div>\n'
        '  </div>\n'
    )
    html_body = re.sub(r"<body[^>]*>", lambda m: m.group(0) + link_block, html_body, count=1)

    periodo = datetime.now().strftime("%Y-%m")
    subject = f"Visa Market Intelligence — Tarjetas de Pago Colombia · {periodo}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"]    = f"Market Intelligence <{gmail_user}>"
    msg["To"]      = to_addr

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"  Dashboard publicado en: {PAGES_URL}")
    print(f"Enviando a {to_addr}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to_addr, msg.as_string())
    print("✅ Email enviado correctamente.")

if __name__ == "__main__":
    html_path = sys.argv[1] if len(sys.argv) > 1 else "report/output_report.html"
    send_report(html_path)
