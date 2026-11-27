"""Descarga la Base de Datos de Inclusión Financiera de la CNBV (trimestral, desde dic-2020) y extrae,
por institución nombrada, tarjetas de crédito y débito para Banca (BD Banca) y EACP/SOFIPO (BD EACP).
Salida: mexico/data/cnbv_tarjetas.json (cache incremental: solo baja periodos nuevos)."""
import io, json, os, re, ssl, socket, tempfile, datetime, requests, certifi, openpyxl
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtensionOID, AuthorityInformationAccessOID

UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
OUT=os.path.join(os.path.dirname(__file__),"data","cnbv_tarjetas.json")
def log(s): print(s, flush=True)

def bundle_with_intermediates(host):
    """Completa la cadena: baja los certificados intermedios que indica el campo AIA (verificación SSL intacta)."""
    ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
    with socket.create_connection((host,443),timeout=30) as s, ctx.wrap_socket(s,server_hostname=host) as ss:
        der = ss.getpeercert(binary_form=True)
    pems=[]; cert=x509.load_der_x509_certificate(der)
    for _ in range(4):
        try: aia=cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
        except x509.ExtensionNotFound: break
        urls=[d.access_location.value for d in aia if d.access_method==AuthorityInformationAccessOID.CA_ISSUERS]
        if not urls: break
        raw=requests.get(urls[0],timeout=30).content
        try: cert=x509.load_der_x509_certificate(raw)
        except Exception: cert=x509.load_pem_x509_certificate(raw)
        pems.append(cert.public_bytes(Encoding.PEM).decode())
        if cert.issuer==cert.subject: break
    f=tempfile.NamedTemporaryFile("w",suffix=".pem",delete=False)
    f.write(open(certifi.where()).read()+"\n"+"\n".join(pems)); f.close()
    log(f"intermediarios agregados: {len(pems)}")
    return f.name


def norm(s): return re.sub(r"\s+"," ",str(s or "")).strip().lower()

def parse_sheet(ws):
    rows=list(ws.iter_rows(values_only=True))
    h=next(i for i,r in enumerate(rows) if any(norm(v)=="nombre institución" for v in r))
    hdr=[norm(v) for v in rows[h]]
    def col(*pats):
        for j,v in enumerate(hdr):
            if all(p in v for p in pats) and "mujeres" not in v and "hombres" not in v: return j
        return None
    c=dict(sector=col("nombre sector"),clave=col("clave"),nombre=col("nombre institución"),
           td=col("tarjetas de débito"),tc=col("tarjetas de crédito"))
    out=[]
    for r in rows[h+1:]:
        if c["clave"] is None or r[c["clave"]] in (None,""): continue
        num=lambda j: (int(round(float(r[j]))) if j is not None and isinstance(r[j],(int,float)) else 0)
        out.append(dict(sector=str(r[c["sector"]]).strip(),clave=str(r[c["clave"]]).strip(),
                        nombre=str(r[c["nombre"]]).strip(),td=num(c["td"]),tc=num(c["tc"])))
    return out

def periods():
    t=datetime.date.today(); y=2020; m=12
    while (y,m)<=(t.year,t.month):
        yield f"{y}{m:02d}"; m+=3
        if m>12: m-=12; y+=1

def main():
    data=json.load(open(OUT)) if os.path.exists(OUT) else {"periodos":{}}
    CA=bundle_with_intermediates("www.cnbv.gob.mx")
    for per in periods():
        if per in data["periodos"]: continue
        got=None
        for ext in ("xlsx","xlsm"):
            url=f"https://www.cnbv.gob.mx/Inclusi%C3%B3n/BasesDeDatos/Base_de_Datos_de_Inclusion_Financiera_{per}.{ext}"
            try: r=requests.get(url,headers=UA,timeout=300,verify=CA)
            except Exception as e: log(f"{per} {ext} error {e}"); continue
            if r.status_code==200 and r.content[:2]==b"PK": got=r.content; break
        if not got: log(f"{per}: no disponible"); continue
        wb=openpyxl.load_workbook(io.BytesIO(got),read_only=True,data_only=True)
        rec={}
        for key,name in (("banca","BD Banca"),("eacp","BD EACP")):
            sh=[s for s in wb.sheetnames if norm(s)==norm(name)]
            if sh:
                try: rec[key]=parse_sheet(wb[sh[0]])
                except Exception as e: log(f"{per} {name} parse error {e}")
        log(f"{per}: banca={len(rec.get('banca',[]))} eacp={len(rec.get('eacp',[]))} "
            f"TC banca={sum(x['tc'] for x in rec.get('banca',[])):,}")
        if rec: data["periodos"][per]=rec
    data["actualizado"]=datetime.date.today().isoformat()
    data["fuente"]="CNBV, Base de Datos de Inclusión Financiera (hojas BD Banca y BD EACP)"
    os.makedirs(os.path.dirname(OUT),exist_ok=True)
    json.dump(data,open(OUT,"w"),ensure_ascii=False,indent=0,sort_keys=True)

if __name__=="__main__": main()
