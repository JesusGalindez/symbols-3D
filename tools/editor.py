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
import tempfile
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import shapely
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import polygonize, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import curvas  # noqa: E402
import simbolo as s  # noqa: E402

NOMBRE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AJUSTES = {"fondo": s.FONDO, "bisel": s.BISEL, "color": s.COLOR}
# Rejilla a la que se ajusta cada capa antes de combinar. Las piezas de un corte comparten
# borde, pero el navegador las guarda en coordenadas locales y al volver al mundo sus
# vértices difieren ~1e-17: la unión dejaba una grieta de ancho cero y el redondeo en
# planta se comía la franja junto a ella (shou-cruz cortado: 5e-3 de área perdida).
PRECISION = 1e-9
TOL_CURVAS = 0.0002  # ajuste al importar: sondeo 4.0 de docs/PLAN-EDITOR.md
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


def tipo_nodo(n):
    """vivo: esquina; suave: tiradores alineados; espejo: además, del mismo largo."""
    e, o = n["ent"], n["sal"]
    if e is None or o is None:
        return "vivo"
    le, lo = math.hypot(*e), math.hypot(*o)
    if le < 1e-12 or lo < 1e-12 or (e[0] * o[0] + e[1] * o[1]) / (le * lo) > -math.cos(math.radians(2)):
        return "vivo"
    return "espejo" if abs(le - lo) <= 0.02 * max(le, lo) else "suave"


_curvas = {}  # nombre -> (fecha del svg, documento): ajustar shou-circular cuesta ~2 s


def piezas_curvas(nombre):
    """piezas_svg() con cada anillo denso ajustado a rectas, arcos y cúbicas (versión 2)."""
    fecha = (s.RAIZ / "svg" / f"{nombre}.svg").stat().st_mtime
    if _curvas.get(nombre, (None,))[0] != fecha:
        doc = piezas_svg(nombre)
        r = lambda v: None if v is None else [round(v[0], 9), round(v[1], 9)]  # noqa: E731
        for c in doc["capas"]:
            c["anillos"] = [[{"p": r(n["p"]), "ent": r(n["ent"]), "sal": r(n["sal"]), "tipo": tipo_nodo(n)}
                             for n in curvas.ajustar_anillo(a, TOL_CURVAS)[0]] for a in c["anillos"]]
        doc["version"] = 2
        _curvas[nombre] = (fecha, doc)
    return json.loads(json.dumps(_curvas[nombre][1]))  # copia: quien la recibe puede cambiarla


def anillo_valido(a):
    """Un anillo tal cual lo dejó el usuario. make_valid y no buffer(0): con un contorno
    que se cruza (pajarita), buffer(0) tira media forma; make_valid conserva las dos,
    como el relleno evenodd del lienzo."""
    g = shapely.make_valid(Polygon(a))
    return unary_union([x for x in getattr(g, "geoms", [g]) if x.geom_type in ("Polygon", "MultiPolygon")])


def forma_capa(anillos):
    """Los anillos de una capa, en el mundo, combinados como el relleno evenodd del lienzo.
    Un anillo es una lista de puntos o (versión 2) de nodos Bézier, que se aplanan aquí."""
    forma = Polygon()
    for a in anillos:
        if a and isinstance(a[0], dict):
            a = curvas.aplanar(a)
        if len(a) >= 3:
            forma = forma.symmetric_difference(anillo_valido(a))
    return forma


def geometria(capas, bisel, simetria=None):
    """Capas en coordenadas del mundo, de abajo arriba: unir suma, restar quita lo de debajo."""
    geo = Polygon()
    for c in capas:
        forma = shapely.set_precision(forma_capa(c["anillos"]), PRECISION)
        geo = geo.union(forma) if c["op"] == "unir" else geo.difference(forma)
    geo = simetrizar(geo, simetria)
    geo = unary_union([p for p in s.lista(geo.buffer(0)) if p.area > 1e-7])
    # mismo acabado en planta que redibujar.py; sobre una forma ya redondeada no cambia nada
    return s.redondear_planta(geo, bisel * s.DIAMETRO * 1.3, bisel * s.DIAMETRO * 0.6)


def simetrizar(geo, simetria):
    """Simetría en vivo: manda una mitad y la otra es su reflejo. simetria = {"lr": bool,
    "ab": bool, "x": -1 (manda la izquierda) | 1, "y": -1 (manda la de abajo) | 1}; los ejes
    son x = 0 e y = 0 (los símbolos salen centrados). Como espejo_lr/espejo_ab de
    redibujar.py: se recorta la mitad que manda y se une con su reflejo. Reflejar el
    resultado entero no vale: un hueco hecho en la mitad que manda quedaría tapado por la
    otra, maciza. El recorte deja el borde exactamente en el eje, y su reflejo también
    (0 y -0 son el mismo número): las dos mitades se funden sin rendija."""
    if not simetria:
        return geo
    G = 10.0  # más grande que cualquier símbolo
    if simetria.get("lr"):
        lado = simetria.get("x", -1)
        mitad = geo.intersection(box(min(0.0, lado * G), -G, max(0.0, lado * G), G))
        geo = unary_union([mitad, affinity.scale(mitad, -1, 1, origin=(0, 0))])
    if simetria.get("ab"):
        lado = simetria.get("y", 1)
        mitad = geo.intersection(box(-G, min(0.0, lado * G), G, max(0.0, lado * G)))
        geo = unary_union([mitad, affinity.scale(mitad, 1, -1, origin=(0, 0))])
    return shapely.set_precision(geo, PRECISION)


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
        caras = sin_astillas([f for f in polygonize(unary_union([forma.boundary, *lineas]))
                              if f.area > 1e-7 and forma.contains(f.representative_point())])
        if len(caras) > len(s.lista(forma)):
            # sin redondear: un corte que roza de forma tangente el redondeo de una esquina
            # deja un canal casi sin anchura, y redondear (a 6 o a 9 decimales) lo cruzaba
            # consigo mismo (pieza inválida). El documento guarda coordenadas completas igual
            cortes.append({"id": c["id"], "piezas": a_listas(MultiPolygon(caras), None)})
        else:
            atraviesa.append(c["id"])
    return {"cortes": cortes, "atraviesa": atraviesa}


def sin_astillas(caras, minima=1e-4):
    """Un trozo de menos de `minima` (1 % × 1 % del diámetro) no merece ser una capa: se
    funde con la vecina con la que comparte más borde. Sale al cortar una misma unión por
    sus dos lados, que se cruzan en el redondeo de la esquina (shou-cruz: 0,006 × 0,006).
    El borde común es exacto, así que la fusión no deja rendija."""
    caras = list(caras)
    while len(caras) > 1:
        chica = min(caras, key=lambda f: f.area)
        if chica.area >= minima:
            break
        otras = [f for f in caras if f is not chica]
        vecina = max(otras, key=lambda f: chica.boundary.intersection(f.boundary).length)
        if chica.boundary.intersection(vecina.boundary).length == 0:
            break  # suelta de verdad (no toca a nadie): se deja
        caras = [f for f in otras if f is not vecina] + [unary_union([vecina, chica])]
    return caras


def tramos_rectos(anillo, largo_min):
    """Bordes rectos de un anillo: segmentos seguidos con la misma dirección (< 1°)."""
    pts = list(anillo.coords)[:-1]
    n = len(pts)
    ang = lambda a, b: math.atan2(b[1] - a[1], b[0] - a[0])
    segs = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    tramos, i = [], 0
    while i < n:
        a, b = segs[i]
        j = i
        while j + 1 < n and abs((ang(*segs[j + 1]) - ang(a, b) + math.pi) % (2 * math.pi) - math.pi) < math.radians(1):
            j += 1
        if math.dist(a, segs[j][1]) >= largo_min:
            tramos.append((a, segs[j][1]))
        i = j + 1
    return tramos


def sugerencias(capas, largo_min=0.03, max_corte=0.12, paralelos=0.02):
    """Cortes propuestos para la cuchilla: una unión en T es justo donde el borde recto de
    un trazo, prolongado, atraviesa el otro. Se prolonga cada borde (≥ largo_min) desde sus
    extremos por dentro del material hasta que sale (≤ max_corte). Sondeo 2026-09-26: en
    shou-cruz los 40 caen en uniones reales. Dos casi paralelos a < `paralelos` (bordes de
    trazos distintos casi alineados) dejarían una astilla entre ellos: se funden en uno."""
    cortes = []
    for c in capas:
        forma = forma_capa(c["anillos"])
        propios = []
        for p in s.lista(forma):
            for anillo in [p.exterior, *p.interiors]:
                for a, b in tramos_rectos(anillo, largo_min):
                    L = math.dist(a, b)
                    d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
                    for o, u in ((b, d), (a, (-d[0], -d[1]))):
                        corte = prolongar(forma, o, u, max_corte)
                        if corte and not any(min(math.dist(o, k[0]) + math.dist(corte, k[1]),
                                                 math.dist(o, k[1]) + math.dist(corte, k[0])) < 0.008 for k in propios):
                            propios.append((o, corte))
        cortes += fundir_paralelos(propios, paralelos)
    # un poco más largos por los dos lados: el corte tiene que cruzar el borde con holgura
    largo = lambda a, b, e: (b[0] + (b[0] - a[0]) / math.dist(a, b) * e, b[1] + (b[1] - a[1]) / math.dist(a, b) * e)
    return [[list(largo(b, a, 2e-4)), list(largo(a, b, 2e-4))] for a, b in cortes]


def bordes_rectos(capas, largo_min=0.015):
    """Bordes rectos de cada capa, [a, b, id]: el imán engancha a sus extremos, a ellos
    mismos y a sus prolongaciones (por donde pasa un corte limpio de una unión). Con el id,
    al mover una capa se ignoran los suyos."""
    return [[list(a), list(b), c.get("id")] for c in capas for p in s.lista(forma_capa(c["anillos"]))
            for anillo in [p.exterior, *p.interiors] for a, b in tramos_rectos(anillo, largo_min)]


def prolongar(forma, o, u, max_corte):
    """Desde o (extremo de un borde) en la dirección u: si entra en el material y vuelve a
    salir antes de max_corte, devuelve el punto de salida. El arco de redondeo de las
    esquinas que entran es tangente al borde: la prolongación roza el contorno al empezar,
    así que se mira el tramo de intersección que arranca en o, no un punto cercano."""
    rayo = LineString([o, (o[0] + u[0] * max_corte, o[1] + u[1] * max_corte)])
    inter = rayo.intersection(forma)
    for g in getattr(inter, "geoms", [inter]):
        if g.geom_type != "LineString" or g.length <= 0.005:
            continue
        ini, fin = g.coords[0], g.coords[-1]
        if math.dist(ini, o) < 1e-6 and g.length < max_corte - 1e-4:
            return fin
    return None


def fundir_paralelos(cortes, distancia):
    """Pares casi paralelos (< 5°), solapados y a < distancia: uno solo, por el medio."""
    cortes = list(cortes)
    i = 0
    while i < len(cortes):
        a, b = cortes[i]
        ua = ((b[0] - a[0]) / math.dist(a, b), (b[1] - a[1]) / math.dist(a, b))
        for j in range(i + 1, len(cortes)):
            c, d = cortes[j]
            if abs(ua[0] * (d[0] - c[0]) + ua[1] * (d[1] - c[1])) < math.dist(c, d) * math.cos(math.radians(5)):
                continue  # no son paralelos
            if (d[0] - c[0]) * ua[0] + (d[1] - c[1]) * ua[1] < 0:
                c, d = d, c  # misma orientación
            if LineString([a, b]).distance(LineString([c, d])) >= distancia:
                continue
            cortes[i] = (((a[0] + c[0]) / 2, (a[1] + c[1]) / 2), ((b[0] + d[0]) / 2, (b[1] + d[1]) / 2))
            del cortes[j]
            break
        else:
            i += 1
    return cortes


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


def a_listas(geo, decimales=6):
    """Multipolígono de shapely -> [[exterior, hueco...], ...] (anillos cerrados, como GeoJSON).
    decimales=None: sin redondear (piezas de un corte: ver cortar())."""
    r = lambda a: [[round(x, decimales), round(y, decimales)] if decimales else [x, y] for x, y in a.coords]
    return [[r(p.exterior), *map(r, p.interiors)] for p in s.lista(geo) if not p.is_empty]


def malla(nombre, doc, capas, carpeta):
    """Capas -> carpeta/glb/<nombre>.glb con el acabado de la galería. La usan «Generar» y
    la vista 3D del editor (/api/previa): lo que se ve es exactamente lo que se genera."""
    a = doc["ajustes"]
    geo = geometria(capas, float(a["bisel"]), doc.get("simetria"))
    if geo.is_empty:
        raise ValueError("no queda ninguna forma que generar")
    for sub in ("glb", "svg"):
        (Path(carpeta) / sub).mkdir(parents=True, exist_ok=True)
    return s.exportar(geo, nombre, fondo=float(a["fondo"]), bisel=float(a["bisel"]),
                      color=[float(v) for v in a["color"]], carpeta=carpeta)


def generar(nombre, doc, capas):
    if protegido(nombre):
        raise ValueError(f"glb/{nombre}.glb no salió del editor: elige otro nombre")
    guardar(nombre, doc)
    return malla(nombre, doc, capas, SALIDA)


def previa(doc, capas):
    """La malla real para la vista 3D, sin tocar glb/: se exporta a un temporal y se lee.
    Con el canto de three.js (ExtrudeGeometry) la vista mentía: en las esquinas que entran,
    redondeadas a 0,6 × canto, hundir el contorno un canto entero lo cruzaba consigo mismo
    y salían caras torcidas en los huecos que el GLB no tiene."""
    with tempfile.TemporaryDirectory() as d:
        malla("previa", doc, capas, d)
        return (Path(d) / "glb" / "previa.glb").read_bytes()


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
                return self.responder({"nombre": libre, "doc": piezas_curvas(nombre)})
            return self.responder({"error": f"no existe {nombre}"}, 404)
        return super().do_GET()

    def do_POST(self):
        datos = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/combinar":
            try:
                geo = geometria(datos["capas"], float(datos["bisel"]), datos.get("simetria"))
                bordes = bordes_rectos(datos["capas"])
            except Exception as e:  # geometría imposible a mitad de edición: se dice, no se cae
                return self.responder({"error": f"{type(e).__name__}: {e}"}, 422)
            # los bordes rectos de cada capa van con la geometría exacta: el imán los usa al
            # mover capas y nodos y en la cuchilla, siempre al día
            return self.responder({"resultado": a_listas(geo), "bordes": bordes})
        if self.path == "/api/previa":
            try:
                cuerpo = previa(datos["doc"], datos["capas"])
            except Exception as e:
                return self.responder({"error": f"{type(e).__name__}: {e}"}, 422)
            self.send_response(200)
            self.send_header("Content-Type", "model/gltf-binary")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        if self.path == "/api/sugerencias":
            try:
                return self.responder({"sugerencias": sugerencias(datos["capas"])})
            except Exception as e:
                return self.responder({"error": f"{type(e).__name__}: {e}"}, 422)
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
