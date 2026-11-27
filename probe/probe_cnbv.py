import io, traceback, requests
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
out=[]
def log(s): out.append(str(s)); print(s)
for per in ["202603","202012"]:
    try:
        ext = "xlsx" if per>="202212" else "xlsm"
        url=f"https://www.cnbv.gob.mx/Inclusi%C3%B3n/BasesDeDatos/Base_de_Datos_de_Inclusion_Financiera_{per}.{ext}"
        r=requests.get(url,headers=UA,timeout=300)
        log(f"== {per} {r.status_code} {len(r.content):,} bytes {r.headers.get('content-type')}")
        if r.status_code!=200:
            log(r.text[:500]); continue
        import openpyxl
        wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
        for ws in wb.worksheets:
            log(f"-- sheet '{ws.title}' dims={ws.max_row}x{ws.max_column}")
            for i,row in enumerate(ws.iter_rows(values_only=True)):
                if i>=10: break
                log("   "+" | ".join("" if v is None else str(v)[:40] for v in row[:40]))
    except Exception:
        log(traceback.format_exc())
open("probe/cnbv_probe.txt","w").write("\n".join(out))
