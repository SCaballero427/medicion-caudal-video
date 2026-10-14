"""Lector minimo de .xlsx (sin pandas ni openpyxl): devuelve las filas de la primera hoja."""
import zipfile, re, xml.etree.ElementTree as ET
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
def leer(ruta, hoja=1):
    z = zipfile.ZipFile(ruta)
    comp = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            comp.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    filas = []
    for r in ET.fromstring(z.read(f"xl/worksheets/sheet{hoja}.xml")).iter(f"{{{NS['m']}}}row"):
        fila = {}
        for c in r.findall("m:c", NS):
            col = re.match(r"[A-Z]+", c.get("r")).group()
            v = c.find("m:v", NS)
            if v is None: continue
            fila[col] = comp[int(v.text)] if c.get("t") == "s" else float(v.text)
        filas.append(fila)
    return filas
