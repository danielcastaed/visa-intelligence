import io, sys, requests, openpyxl, re
UA={"User-Agent":"Mozilla/5.0"}
out=[]
for per in ["202603","202012"]:
    url=f"https://www.cnbv.gob.mx/Inclusi%C3%B3n/BasesDeDatos/Base_de_Datos_de_Inclusion_Financiera_{per}." + ("xlsx" if per>="202212" else "xlsm")
    r=requests.get(url,headers=UA,timeout=300)
    out.append(f"== {per} {r.status_code} {len(r.content):,} bytes {r.headers.get('content-type')}")
    if r.status_code!=200: continue
    wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
    for ws in wb.worksheets:
        out.append(f"-- sheet '{ws.title}' dims={ws.max_row}x{ws.max_column}")
        for i,row in enumerate(ws.iter_rows(values_only=True)):
            if i<12: out.append("   "+" | ".join("" if v is None else str(v)[:40] for v in row[:30]))
            else: break
open("probe/cnbv_probe.txt","w").write("\n".join(out))
print("\n".join(out)[:3000])
