import io, re, ssl, socket, tempfile, traceback, requests, certifi
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtensionOID, AuthorityInformationAccessOID
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
out=[]
def log(s): out.append(str(s)); print(s)

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

try:
    CA=bundle_with_intermediates("www.cnbv.gob.mx")
except Exception:
    log(traceback.format_exc()); CA=True
for per in ["202603"]:
    try:
        url=f"https://www.cnbv.gob.mx/Inclusi%C3%B3n/BasesDeDatos/Base_de_Datos_de_Inclusion_Financiera_{per}.xlsx"
        r=requests.get(url,headers=UA,timeout=300,verify=CA)
        log(f"== {per} {r.status_code} {len(r.content):,} bytes")
        import openpyxl
        wb=openpyxl.load_workbook(io.BytesIO(r.content),read_only=True,data_only=True)
        for name in ["BD Banca","BD EACP","BD Datos históricos"]:
            ws=wb[name]
            log(f"-- sheet '{name}' dims={ws.max_row}x{ws.max_column}")
            hdr=None
            for i,row in enumerate(ws.iter_rows(values_only=True)):
                if i<14:
                    if any(v not in (None,"") for v in row):
                        log(f"  r{i}: "+" | ".join("" if v is None else str(v).replace(chr(10),' ')[:38] for v in row[:70]))
                    continue
                # muestra filas que contengan tarjeta o Nu/Plata
                s=" ".join("" if v is None else str(v) for v in row[:12])
                if re.search(r"Nu |Nu M|Plata|Stori|Klar|Finsus|Revolut|BBVA", s) and i<6000:
                    log(f"  r{i}: "+" | ".join("" if v is None else str(v)[:30] for v in row[:70]))
    except Exception:
        log(traceback.format_exc()[-1500:])
open("probe/cnbv_probe.txt","w").write("\n".join(out[:400]))
