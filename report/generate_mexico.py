"""Genera docs/mexico/index.html a partir de mexico/output.json.

Uso:
    python mexico/model.py          # recalcula el modelo (mexico/output.json)
    python report/generate_mexico.py
"""
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(os.path.join(ROOT, "mexico", "output.json"), encoding="utf-8") as f:
        data = json.load(f)
    data["meta"]["generado"] = datetime.date.today().isoformat()
    with open(os.path.join(ROOT, "report", "mexico_template.html"), encoding="utf-8") as f:
        tpl = f.read()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = tpl.replace("__DATA__", payload)
    out_dir = os.path.join(ROOT, "docs", "mexico")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"OK -> {out} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
