"""Servidor del editor de símbolos (editor.html): abre, guarda, combina y genera.

Uso:  .venv/bin/python tools/editor.py                 -> http://localhost:8792/editor.html
      .venv/bin/python tools/editor.py --puerto 8793 --salida /tmp/x   (pruebas: nada cae en glb/)

El navegador solo dibuja y previsualiza; la geometría que cuenta la calcula este
servidor con shapely (/api/combinar) y el GLB sale de simbolo.exportar(), el mismo
acabado que redibujar.py y letras.py. Los documentos viven en editor/<nombre>.json,
con copias en editor/.historial/<nombre>/. Un GLB que no salió del editor no se
sobrescribe nunca.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simbolo as s  # noqa: E402

NOMBRE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AJUSTES = {"fondo": s.FONDO, "bisel": s.BISEL, "color": s.COLOR}
COPIAS = 20          # copias por documento en editor/.historial
SALIDA = s.RAIZ      # --salida la cambia: glb/, svg/ y editor/ se escriben ahí


def docs():
    return SALIDA / "editor"


def protegido(nombre):
    """Un GLB que existe y no tiene documento del editor es un símbolo hecho a mano."""
    existe = any((raiz / "glb" / f"{nombre}.glb").exists() for raiz in {s.RAIZ, SALIDA})
    return existe and not (docs() / f"{nombre}.json").exists()


def piezas_svg(nombre):
    """svg/<nombre>.svg (evenodd) -> una capa por pieza, con sus huecos."""
    d = re.search(r' d="([^"]+)"', (s.RAIZ / "svg" / f"{nombre}.svg").read_text()).group(1)
    geo = Polygon()
    for trazo in re.findall(r"M([^MZ]+)Z", d):
        pts = [tuple(map(float, p.split(","))) for p in trazo.split(" L")]
        geo = geo.symmetric_difference(Polygon([(x, -y) for x, y in pts]).buffer(0))
    capas = []
    for i, p in enumerate(sorted(s.lista(geo), key=lambda p: -p.area)):
        minx, miny, maxx, maxy = p.bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        anillos = [[[round(x - cx, 6), round(y - cy, 6)] for x, y in a.coords[:-1]]
                   for a in [p.exterior, *p.interiors]]
        capas.append({"nombre": f"Pieza {i + 1}", "op": "unir", "visible": True, "anillos": anillos,
                      "t": {"x": round(cx, 6), "y": round(cy, 6), "r": 0, "sx": 1, "sy": 1}})
    return {"version": 1, "origen": nombre, "capas": capas, "ajustes": AJUSTES}


def anillo_valido(a):
    """Un anillo tal cual lo dejó el usuario. make_valid y no buffer(0): con un contorno
    que se cruza (pajarita), buffer(0) tira media forma; make_valid conserva las dos,
    como el relleno evenodd del lienzo."""
    g = shapely.make_valid(Polygon(a))
    return unary_union([x for x in getattr(g, "geoms", [g]) if x.geom_type in ("Polygon", "MultiPolygon")])


def geometria(capas, bisel):
    """Capas en coordenadas del mundo, de abajo arriba: unir suma, restar quita lo de debajo."""
    geo = Polygon()
    for c in capas:
        forma = Polygon()
        for a in c["anillos"]:
            if len(a) >= 3:
                forma = forma.symmetric_difference(anillo_valido(a))
        geo = geo.union(forma) if c["op"] == "unir" else geo.difference(forma)
    geo = unary_union([p for p in s.lista(geo.buffer(0)) if p.area > 1e-7])
    # mismo acabado en planta que redibujar.py; sobre una forma ya redondeada no cambia nada
    return s.redondear_planta(geo, bisel * s.DIAMETRO * 1.3, bisel * s.DIAMETRO * 0.6)


def a_listas(geo):
    """Multipolígono de shapely -> [[exterior, hueco...], ...] como en polygon-clipping."""
    r = lambda a: [[round(x, 6), round(y, 6)] for x, y in a.coords]
    return [[r(p.exterior), *map(r, p.interiors)] for p in s.lista(geo) if not p.is_empty]


def generar(nombre, doc, capas):
    if protegido(nombre):
        raise ValueError(f"glb/{nombre}.glb no salió del editor: elige otro nombre")
    a = doc["ajustes"]
    geo = geometria(capas, float(a["bisel"]))
    if geo.is_empty:
        raise ValueError("no queda ninguna forma que generar")
    guardar(nombre, doc)
    for sub in ("glb", "svg"):
        (SALIDA / sub).mkdir(parents=True, exist_ok=True)
    return s.exportar(geo, nombre, fondo=float(a["fondo"]), bisel=float(a["bisel"]),
                      color=[float(v) for v in a["color"]], carpeta=SALIDA)


def guardar(nombre, doc):
    if protegido(nombre):
        raise ValueError(f"{nombre} es un símbolo que no salió del editor: elige otro nombre")
    texto = json.dumps(doc, ensure_ascii=False)
    ruta = docs() / f"{nombre}.json"
    if ruta.exists() and ruta.read_text() == texto:
        return
    historial = docs() / ".historial" / nombre
    historial.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto)
    (historial / f"{datetime.now():%Y%m%d-%H%M%S-%f}.json").write_text(texto)
    for vieja in sorted(historial.glob("*.json"))[:-COPIAS]:
        vieja.unlink()


class Manejador(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(s.RAIZ), **k)

    def translate_path(self, path):
        # lo generado vive en SALIDA; el resto (editor.html, vendor/, fuentes) en la raíz
        ruta = urlparse(path).path
        if ruta.startswith(("/glb/", "/svg/")) and (SALIDA / ruta.lstrip("/")).exists():
            return str(SALIDA / ruta.lstrip("/"))
        return super().translate_path(path)

    def responder(self, datos, codigo=200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/simbolos":
            editados = sorted(p.stem for p in docs().glob("*.json"))
            svgs = sorted(p.stem for p in (s.RAIZ / "svg").glob("*.svg")
                          if not p.stem.endswith("-ligera") and p.stem not in editados)
            return self.responder({"simbolos": svgs, "editados": editados, "ajustes": AJUSTES})
        if url.path == "/api/abrir":
            nombre = parse_qs(url.query).get("s", [""])[0]
            if not NOMBRE.match(nombre):
                return self.responder({"error": "nombre no válido"}, 400)
            doc = docs() / f"{nombre}.json"
            if doc.exists():
                return self.responder({"nombre": nombre, "doc": json.loads(doc.read_text())})
            if (s.RAIZ / "svg" / f"{nombre}.svg").exists():
                libre, n = f"{nombre}-editado", 2  # sin pisar una edición anterior del mismo símbolo
                while (docs() / f"{libre}.json").exists() or protegido(libre):
                    libre, n = f"{nombre}-editado-{n}", n + 1
                return self.responder({"nombre": libre, "doc": piezas_svg(nombre)})
            return self.responder({"error": f"no existe {nombre}"}, 404)
        return super().do_GET()

    def do_POST(self):
        datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/combinar":
            try:
                geo = geometria(datos["capas"], float(datos["bisel"]))
            except Exception as e:  # geometría imposible a mitad de edición: se dice, no se cae
                return self.responder({"error": f"{type(e).__name__}: {e}"}, 422)
            return self.responder({"resultado": a_listas(geo)})
        nombre = datos.get("nombre", "")
        if not NOMBRE.match(nombre):
            return self.responder({"error": "nombre: minúsculas, números y guiones"}, 400)
        try:
            if self.path == "/api/guardar":
                guardar(nombre, datos["doc"])
                return self.responder({"ok": True})
            if self.path == "/api/generar":
                return self.responder({"ok": True, **generar(nombre, datos["doc"], datos["capas"])})
        except ValueError as e:
            return self.responder({"error": str(e)}, 409)
        self.responder({"error": "ruta desconocida"}, 404)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):  # sin una línea por petición: /api/combinar llega a cada pausa
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8792)
    ap.add_argument("--salida", type=Path, default=s.RAIZ)
    args = ap.parse_args()
    SALIDA = args.salida.resolve()
    print(f"Editor en http://localhost:{args.puerto}/editor.html", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.puerto), Manejador).serve_forever()
