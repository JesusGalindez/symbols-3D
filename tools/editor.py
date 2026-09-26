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
import math
import re
import sys
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import polygonize, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simbolo as s  # noqa: E402

NOMBRE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AJUSTES = {"fondo": s.FONDO, "bisel": s.BISEL, "color": s.COLOR}
# Rejilla a la que se ajusta cada capa antes de combinar. Las piezas de un corte comparten
# borde, pero el navegador las guarda en coordenadas locales y al volver al mundo sus
# vértices difieren ~1e-17: la unión dejaba una grieta de ancho cero y el redondeo en
# planta se comía la franja junto a ella (shou-cruz cortado: 5e-3 de área perdida).
PRECISION = 1e-9
COPIAS = 20          # copias por documento en editor/.historial
CADA_COPIA = 30      # segundos mínimos entre copias: el navegador guarda 1,5 s tras cada cambio
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


def forma_capa(anillos):
    """Los anillos de una capa, en el mundo, combinados como el relleno evenodd del lienzo."""
    forma = Polygon()
    for a in anillos:
        if len(a) >= 3:
            forma = forma.symmetric_difference(anillo_valido(a))
    return forma


def geometria(capas, bisel):
    """Capas en coordenadas del mundo, de abajo arriba: unir suma, restar quita lo de debajo."""
    geo = Polygon()
    for c in capas:
        forma = shapely.set_precision(forma_capa(c["anillos"]), PRECISION)
        geo = geo.union(forma) if c["op"] == "unir" else geo.difference(forma)
    geo = unary_union([p for p in s.lista(geo.buffer(0)) if p.area > 1e-7])
    # mismo acabado en planta que redibujar.py; sobre una forma ya redondeada no cambia nada
    return s.redondear_planta(geo, bisel * s.DIAMETRO * 1.3, bisel * s.DIAMETRO * 0.6)


def cortar(capas, linea):
    """Cuchilla. Cada capa se parte por la línea nueva más sus costuras (cortes anteriores
    que no la separaron: en símbolos como shou-cruz un trazo está unido por varios lados y
    un corte solo no lo suelta). Las caras salen de polygonize() sobre el contorno y las
    líneas: vecinas con el mismo borde, vértice a vértice, y sin rendija al volver a unirlas.
    Devuelve las capas separadas con sus piezas, y las que la línea atraviesa sin separar
    (el navegador guarda esa línea como costura)."""
    cortes, atraviesa = [], []
    for c in capas:
        forma = forma_capa(c["anillos"])
        if forma.is_empty:
            continue
        nueva = alargar(linea, forma)
        if nueva.intersection(forma).length < 1e-4:
            continue  # la línea nueva no pasa por esta capa
        lineas = [nueva, *(alargar(k, forma) for k in c.get("costuras", []))]
        caras = [f for f in polygonize(unary_union([forma.boundary, *lineas]))
                 if f.area > 1e-7 and forma.contains(f.representative_point())]
        if len(caras) > len(s.lista(forma)):
            cortes.append({"id": c["id"], "piezas": a_listas(MultiPolygon(caras))})
        else:
            atraviesa.append(c["id"])
    return {"cortes": cortes, "atraviesa": atraviesa}


def alargar(linea, forma, hasta=0.15):
    """Un extremo de la cuchilla que acaba dentro de un trazo (fácil al arrastrar a mano)
    no cortaría nada: se prolonga en su dirección hasta salir de ese trazo, y no más allá
    de `hasta`, para no llegar a cortar trazos que no se tocaron."""
    pts = [tuple(q) for q in linea]
    for extremo, resto in ((0, pts[1:]), (-1, pts[-2::-1])):
        x, y = pts[extremo]
        if not forma.contains(Point(x, y)):
            continue
        # dirección con un punto a ≥ 0,01: a mano alzada los primeros puntos van muy juntos
        lejos = next((q for q in resto if math.dist(q, (x, y)) >= 0.01), resto[-1] if resto else None)
        if lejos is None or math.dist(lejos, (x, y)) == 0:
            continue
        ux, uy = (x - lejos[0]) / math.dist(lejos, (x, y)), (y - lejos[1]) / math.dist(lejos, (x, y))
        salida = LineString([(x, y), (x + ux * hasta, y + uy * hasta)]).intersection(forma.boundary)
        if salida.is_empty:
            continue
        q = min(getattr(salida, "geoms", [salida]), key=lambda g: g.distance(Point(x, y))).coords[0]
        nuevo = (q[0] + ux * 1e-4, q[1] + uy * 1e-4)  # justo fuera: la línea tiene que cruzar el borde
        if extremo == 0:
            pts.insert(0, nuevo)
        else:
            pts.append(nuevo)
    return LineString(pts)


def a_listas(geo):
    """Multipolígono de shapely -> [[exterior, hueco...], ...] (anillos cerrados, como GeoJSON)."""
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
    copias = sorted(historial.glob("*.json"))
    if not copias or time.time() - copias[-1].stat().st_mtime >= CADA_COPIA:
        (historial / f"{datetime.now():%Y%m%d-%H%M%S-%f}.json").write_text(texto)
        for vieja in sorted(historial.glob("*.json"))[:-COPIAS]:
            vieja.unlink()


def completar_parche(nombre, doc):
    """Al cerrar la pestaña, sendBeacon solo admite 64 KB y shou-circular ocupa 105: el
    navegador manda con anillos "=" las capas cuyos nodos no cambiaron desde el último
    guardado, y aquí se toman del documento guardado."""
    ruta = docs() / f"{nombre}.json"
    guardadas = {c["id"]: c["anillos"] for c in json.loads(ruta.read_text())["capas"]} if ruta.exists() else {}
    for c in doc["capas"]:
        if c["anillos"] == "=":
            if c["id"] not in guardadas:
                raise ValueError(f"parche sin base: la capa {c['id']} no está en editor/{nombre}.json")
            c["anillos"] = guardadas[c["id"]]
    return doc


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
        if self.path == "/api/cortar":
            try:
                return self.responder(cortar(datos["capas"], datos["linea"]))
            except Exception as e:
                return self.responder({"error": f"{type(e).__name__}: {e}"}, 422)
        nombre = datos.get("nombre", "")
        if not NOMBRE.match(nombre):
            return self.responder({"error": "nombre: minúsculas, números y guiones"}, 400)
        try:
            if self.path == "/api/guardar":
                guardar(nombre, completar_parche(nombre, datos["doc"]) if datos.get("parche") else datos["doc"])
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
