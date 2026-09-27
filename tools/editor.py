"""Servidor del editor de símbolos (editor.html): abre, guarda, combina, corta, importa y
exporta SVG, y genera.

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
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import shapely
import trimesh
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import polygonize, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import curvas  # noqa: E402
import leer_svg  # noqa: E402
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


def importar(nombre, texto):
    """Un SVG externo -> documento nuevo (versión 2): una capa por elemento relleno, con sus
    curvas (tools/leer_svg.py), escalado a diámetro 1. El nombre sale del del archivo, sin
    pisar un documento ni un símbolo."""
    capas, marco = leer_svg.leer(texto)
    doc = {"version": 2, "origen": None, "capas": [], "ajustes": dict(AJUSTES)}
    r = lambda v: None if v is None else [round(v[0], 9), round(v[1], 9)]  # noqa: E731
    for c in capas:
        pts = [q for a in c["anillos"] for q in curvas.aplanar(a, cerrado=not c.get("abierto"))]
        cx = (min(q[0] for q in pts) + max(q[0] for q in pts)) / 2
        cy = (min(q[1] for q in pts) + max(q[1] for q in pts)) / 2
        anillos = [[{"p": r([n["p"][0] - cx, n["p"][1] - cy]), "ent": r(n["ent"]), "sal": r(n["sal"])} for n in a]
                   for a in c["anillos"]]
        for a in anillos:
            for n in a:
                n["tipo"] = tipo_nodo(n)
        doc["capas"].append({"id": len(doc["capas"]) + 1, "nombre": c["nombre"], "op": c["op"], "visible": True,
                             "anillos": anillos, "t": {"x": round(cx, 9), "y": round(cy, 9), "r": 0, "sx": 1, "sy": 1},
                             **({"trazo": c["trazo"]} if c.get("trazo") else {}), **({"abierto": True} if c.get("abierto") else {})})
    base = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", Path(nombre).stem.lower())).strip("-") or "importado"
    libre, k = base, 2
    while (docs() / f"{libre}.json").exists() or protegido(libre) or (s.RAIZ / "svg" / f"{libre}.svg").exists():
        libre, k = f"{base}-{k}", k + 1
    return {"nombre": libre, "doc": doc, "marco": marco}


def trazo_svg(anillos, K=1000, abierto=False):
    """Anillos de nodos en el mundo -> d="…" de SVG, en milésimas y con y hacia abajo.
    abierto: caminos sin el tramo de cierre ni Z."""
    f = lambda x, y: f"{round(x * K, 3):g} {round(-y * K, 3):g}"  # noqa: E731
    d = []
    for a in anillos:
        d.append("M" + f(*a[0]["p"]))
        for i, n in enumerate(a[:-1] if abierto else a):
            m = a[(i + 1) % len(a)]
            if n["sal"] is None and m["ent"] is None:
                d.append("L" + f(*m["p"]))
                continue
            c1 = [n["p"][0] + n["sal"][0], n["p"][1] + n["sal"][1]] if n["sal"] is not None else n["p"]
            c2 = [m["p"][0] + m["ent"][0], m["p"][1] + m["ent"][1]] if m["ent"] is not None else m["p"]
            d.append(f"C{f(*c1)} {f(*c2)} {f(*m['p'])}")
        if not abierto:
            d.append("Z")
    return "".join(d)


def exportar_svg(capas, simetria, color):
    """El diseño como SVG con curvas, sin el redondeo del acabado (ese es del GLB). Solo
    capas que unen y sin simetría: una ruta por capa con sus nodos tal cual (limpio para
    Figma o Illustrator, con el nombre de cada capa). Con restas o simetría, la forma
    combinada (planta) reajustada a rectas, arcos y cúbicas como al abrir un símbolo: una
    sola ruta evenodd que cualquier programa (y el importador) lee igual."""
    rgb = "#" + "".join(f"{round(255 * (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)):02x}"
                        for v in (min(max(float(c), 0), 1) for c in color[:3]))  # lineal (glTF) -> sRGB
    visibles = [c for c in capas if c.get("visible", True)]
    if not visibles:
        raise ValueError("no hay ninguna capa visible que exportar")
    centrado = lambda c: not c.get("trazo") or {**TRAZO, **c["trazo"]}["posicion"] == "centro"  # noqa: E731
    if simetria is None and all(c["op"] == "unir" and centrado(c) for c in visibles):
        # un trazo sale como trazo de SVG (editable en Figma); dentro/fuera no existen en SVG
        rutas = [(c.get("nombre", f"Capa {i + 1}"), [a for a in c["anillos"] if a and isinstance(a[0], dict)], c)
                 for i, c in enumerate(visibles)]
        pts = [q for c in visibles for p in s.lista(forma_de(c)) for q in p.exterior.coords]
    else:
        geo = planta(visibles, simetria)
        if geo.is_empty:
            raise ValueError("no queda ninguna forma que exportar")
        anillos = [curvas.ajustar_anillo(list(a.coords)[:-1], TOL_CURVAS)[0]
                   for p in s.lista(geo) for a in [p.exterior, *p.interiors]]
        rutas, pts = [("Diseño", anillos, {})], [q for p in s.lista(geo) for q in p.exterior.coords]
    x0, x1 = min(q[0] for q in pts) * 1000 - 20, max(q[0] for q in pts) * 1000 + 20
    y0, y1 = -max(q[1] for q in pts) * 1000 - 20, -min(q[1] for q in pts) * 1000 + 20
    marco = " ".join(f"{round(v, 3):g}" for v in (x0, y0, x1 - x0, y1 - y0))
    esc = lambda t: str(t).replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")  # noqa: E731
    def ruta(nombre, anillos, c):
        if not c.get("trazo"):
            return f'<path id="{esc(nombre)}" fill="{rgb}" fill-rule="evenodd" d="{trazo_svg(anillos)}"/>'
        tr = {**TRAZO, **c["trazo"]}
        return (f'<path id="{esc(nombre)}" fill="none" stroke="{rgb}" stroke-width="{round(float(tr["ancho"]) * 1000, 3):g}" '
                f'stroke-linecap="{ {"redondo": "round", "plano": "butt", "cuadrado": "square"}[tr["extremos"]]}" '
                f'stroke-linejoin="{ {"redonda": "round", "inglete": "miter", "bisel": "bevel"}[tr["uniones"]]}" '
                f'stroke-miterlimit="{float(tr["inglete"]):g}" d="{trazo_svg(anillos, abierto=bool(c.get("abierto")))}"/>')
    cuerpo = "\n".join(ruta(*r) for r in rutas if r[1])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{marco}" width="{round(x1 - x0, 3):g}" '
            f'height="{round(y1 - y0, 3):g}">\n{cuerpo}\n</svg>\n')


def anillo_valido(a):
    """Un anillo tal cual lo dejó el usuario. make_valid y no buffer(0): con un contorno
    que se cruza (pajarita), buffer(0) tira media forma; make_valid conserva las dos,
    como el relleno evenodd del lienzo."""
    g = shapely.make_valid(Polygon(a))
    return unary_union([x for x in getattr(g, "geoms", [g]) if x.geom_type in ("Polygon", "MultiPolygon")])


TRAZO = {"ancho": 0.03, "extremos": "redondo", "uniones": "redonda", "inglete": 4.0, "posicion": "centro"}
EXTREMOS = {"redondo": "round", "plano": "flat", "cuadrado": "square"}
UNIONES = {"redonda": "round", "inglete": "mitre", "bisel": "bevel"}


def forma_de(c):
    """La forma de una capa en el mundo: su relleno evenodd o, si tiene trazo, el trazo de
    su camino (abierto o cerrado) con su grosor. Un camino abierto sin trazo no rellena nada."""
    tr = c.get("trazo")
    if c.get("abierto") and not tr:
        raise ValueError("una capa abierta necesita un trazo")
    if not tr:
        return forma_capa(c["anillos"])
    return forma_trazo(c["anillos"], {**TRAZO, **tr}, bool(c.get("abierto")))


def forma_trazo(anillos, tr, abierto):
    """El trazo de un camino, como Figma: grosor, extremos (plano, redondo, cuadrado) y
    uniones (inglete con su límite, redonda, bisel). En un camino cerrado, centrado en el
    borde, por dentro o por fuera. El grosor va en unidades del mundo: escalar la capa no
    lo cambia (decisión 6 del plan)."""
    w = float(tr["ancho"])
    if w <= 0:
        return Polygon()
    kw = {"join_style": UNIONES[tr["uniones"]], "mitre_limit": float(tr["inglete"]), "quad_segs": 16}
    if abierto:
        partes = []
        for a in anillos:
            pts = curvas.aplanar(a, cerrado=False) if a and isinstance(a[0], dict) else a
            if len(pts) >= 2:
                partes.append(LineString(pts).buffer(w / 2, cap_style=EXTREMOS[tr["extremos"]], **kw))
        return shapely.make_valid(unary_union(partes)) if partes else Polygon()
    relleno = forma_capa(anillos)
    if tr["posicion"] == "dentro":
        g = relleno.difference(relleno.buffer(-w, **kw))
    elif tr["posicion"] == "fuera":
        g = relleno.buffer(w, **kw).difference(relleno)
    else:
        g = relleno.buffer(w / 2, **kw).difference(relleno.buffer(-w / 2, **kw))
    return shapely.make_valid(g)


TOL_CONTORNO = 0.00005  # al volver a curvas una forma calculada: en un trazo de 0,05, con
# 0,0002 (la de importar símbolos) el IoU caía a 0,996; con esta, 0,9993 y 19 nodos


def a_curvas(geo):
    """Una forma de shapely -> anillos de nodos (rectas, arcos y cúbicas), como al abrir un
    símbolo: exteriores y huecos juntos, que el relleno evenodd combina bien."""
    return [[{**n, "tipo": tipo_nodo(n)} for n in curvas.ajustar_anillo(list(a.coords)[:-1], TOL_CONTORNO)[0]]
            for p in s.lista(geo) for a in [p.exterior, *p.interiors] if len(a.coords) >= 4]


def contornear(capas):
    """Contornear trazo (⇧⌘O): cada capa, su forma exacta como relleno con curvas."""
    return [{"id": c.get("id"), "anillos": a_curvas(forma_de(c))} for c in capas]


def desplazar(capas, d):
    """Engrosar (d > 0) o adelgazar (d < 0) cada capa d por cada lado. Un trazo cambia su
    grosor (2d); un relleno, su contorno, en inglete (las esquinas siguen vivas: el
    redondeo es cosa del acabado) y reajustado a curvas."""
    out = []
    for c in capas:
        if c.get("trazo"):
            tr = {**TRAZO, **c["trazo"]}
            out.append({"id": c.get("id"), "trazo": {**c["trazo"], "ancho": max(1e-4, float(tr["ancho"]) + 2 * d)}})
        else:
            g = forma_de(c).buffer(d, join_style="mitre", mitre_limit=4.0)
            if g.is_empty:
                raise ValueError(f"adelgazar {-d:g} hace desaparecer «{c.get('nombre', c.get('id'))}»")
            out.append({"id": c.get("id"), "anillos": a_curvas(g)})
    return out


def engrosar_lo_necesario(capas, bisel, simetria=None, hasta=0.03):
    """«Generar» rechazó por trazo fino: el menor d (± 1e-4) que, aplicado a las capas que
    forman las piezas que pierden demasiado al redondear, deja todas por debajo de
    simbolo.PERDIDA_MAX. Devuelve d y las capas cambiadas (desplazar())."""
    perdida = lambda base: s.area_perdida(base, acabar(base, bisel))  # noqa: E731
    base = planta(capas, simetria)
    if perdida(base) <= s.PERDIDA_MAX:
        return {"d": 0.0, "capas": []}
    malas = [p for p in s.lista(base) if p.area > 0 and 1 - acabar(p, bisel).intersection(p).area / p.area > s.PERDIDA_MAX]
    culpables = [c for c in capas if c.get("op") == "unir" and c.get("visible", True)
                 and any(forma_de(c).intersection(p).area > 0 for p in malas)]
    ids = {id(c) for c in culpables}

    def con(d):  # las capas con las culpables engrosadas d (sin reajustar a curvas: más rápido)
        return [({**c, "trazo": {**c["trazo"], "ancho": float({**TRAZO, **c["trazo"]}["ancho"]) + 2 * d}} if c.get("trazo")
                 else {**c, "anillos": [list(a.coords)[:-1] for p in s.lista(forma_de(c).buffer(d, join_style="mitre", mitre_limit=4.0))
                                        for a in [p.exterior, *p.interiors]]}) if id(c) in ids else c for c in capas]
    if perdida(planta(con(hasta), simetria)) > s.PERDIDA_MAX:
        raise ValueError(f"ni engrosando {hasta:g} por lado aprueba")
    lo, hi = 0.0, hasta
    while hi - lo > 5e-5:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if perdida(planta(con(mid), simetria)) <= s.PERDIDA_MAX else (mid, hi)
    return {"d": hi, "capas": desplazar(culpables, hi)}


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


def planta(capas, simetria=None):
    """Capas en coordenadas del mundo, de abajo arriba: unir suma, restar quita lo de debajo.
    Sin el redondeo del acabado (con él, geometria())."""
    geo = Polygon()
    for c in capas:
        forma = shapely.set_precision(forma_de(c), PRECISION)
        geo = geo.union(forma) if c["op"] == "unir" else geo.difference(forma)
    geo = simetrizar(geo, simetria)
    return unary_union([p for p in s.lista(geo.buffer(0)) if p.area > 1e-7])


def acabar(geo, bisel, esquina=None):
    """Mismo acabado en planta que redibujar.py; sobre una forma ya redondeada no cambia nada.
    Sin piezas de área nula: con esquinas de 4 segmentos (la ligera), xi-doble simétrico
    dejaba una en el eje y el canto (simbolo.inset) no la aguantaba."""
    g = s.redondear_planta(geo, bisel * s.DIAMETRO * 1.3, bisel * s.DIAMETRO * 0.6, esquina)
    return unary_union([p for p in s.lista(g) if p.area > 1e-7])


def geometria(capas, bisel, simetria=None):
    return acabar(planta(capas, simetria), bisel)


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
    (el navegador guarda esa línea como costura). Una capa con curvas recibe sus piezas
    como nodos, con las curvas partidas por De Casteljau (curvas.recurvar)."""
    cortes, atraviesa, sin_esqueleto = [], [], []
    for c in capas:
        forma = forma_de(c)
        if forma.is_empty:
            continue
        if c.get("trazo"):  # un trazo se corta por su esqueleto, y sus trozos siguen siendo trazos
            piezas = cortar_trazo(c, alargar(linea, forma))
            if piezas is None:
                if LineString(linea).intersects(forma):
                    sin_esqueleto.append(c["id"])
            else:
                cortes.append({"id": c["id"], "piezas": [[a] for a, _ in piezas], "abiertos": [ab for _, ab in piezas]})
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
            piezas = a_listas(MultiPolygon(caras), None)
            if any(a and isinstance(a[0], dict) for a in c["anillos"]):  # con curvas: se rehacen
                ind = curvas.indice(c["anillos"])
                piezas = [[[{**n, "tipo": tipo_nodo(n)} for n in curvas.recurvar(a, ind)] for a in poli] for poli in piezas]
            cortes.append({"id": c["id"], "piezas": piezas})
        else:
            atraviesa.append(c["id"])
    return {"cortes": cortes, "atraviesa": atraviesa, **({"sin_esqueleto": sin_esqueleto} if sin_esqueleto else {})}


def cortar_trazo(c, linea):
    """Los caminos de una capa de trazo partidos donde la línea cruza su esqueleto:
    [(nodos, abierto)], o None si no cruza ninguno. El parámetro t del cruce sale del
    aplanado (a < 1e-4 de la curva) y el punto de corte es el de la curva en ese t."""
    abierto, out, corta = bool(c.get("abierto")), [], False
    for a in c["anillos"]:
        pts = curvas.aplanar_t(a, cerrado=not abierto)
        segs = list(zip(pts, pts[1:] + (pts[:1] if not abierto else [])))
        cortes = []
        for p, q in segs:
            cruce = LineString([p[:2], q[:2]]).intersection(linea)
            for g in getattr(cruce, "geoms", [cruce]):
                if g.geom_type != "Point":
                    continue
                L = math.dist(p[:2], q[:2]) or 1
                lam = math.dist(p[:2], g.coords[0]) / L
                t1 = q[3] if q[2] == p[2] else 1.0
                cortes.append((p[2], p[3] + lam * (t1 - p[3])))
        if cortes:
            corta = True
            trozos = curvas.partir_camino(a, cortes, cerrado=not abierto)
            out += [([{**n, "tipo": tipo_nodo(n)} for n in t], True) for t in trozos]
        else:
            out.append((a, abierto))
    return out if corta else None


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
        if c.get("trazo"):
            continue  # las uniones en T son de contornos rellenos
        forma = forma_de(c)
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
    extremos = [[list(a[i]["p"]), list(a[i]["p"]), c.get("id")] for c in capas if c.get("abierto")
                for a in c["anillos"] for i in (0, -1)]  # los extremos de los caminos abiertos
    return [[list(a), list(b), c.get("id")] for c in capas for p in s.lista(forma_de(c))
            for anillo in [p.exterior, *p.interiors] for a, b in tramos_rectos(anillo, largo_min)] + extremos


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


LIGERA = {"pasos": 3, "esquina": 4}  # como --ligera de redibujar.py y letras.py


def malla(nombre, doc, capas, carpeta, ligera=False, base=None):
    """Capas -> carpeta/glb/<nombre>.glb con el acabado de la galería. La usan «Generar» y
    la vista 3D del editor (/api/previa): lo que se ve es exactamente lo que se genera.
    base: la planta ya combinada, si se tiene (generar la reutiliza para la ligera)."""
    a = doc["ajustes"]
    base = planta(capas, doc.get("simetria")) if base is None else base
    geo = acabar(base, float(a["bisel"]), LIGERA["esquina"] if ligera else None)
    if geo.is_empty:
        raise ValueError("no queda ninguna forma que generar")
    for sub in ("glb", "svg"):
        (Path(carpeta) / sub).mkdir(parents=True, exist_ok=True)
    return s.exportar(geo, nombre, fondo=float(a["fondo"]), bisel=float(a["bisel"]),
                      color=[float(v) for v in a["color"]], pasos=LIGERA["pasos"] if ligera else None,
                      carpeta=carpeta)


def revisar(glb, base, bisel):
    """Lo que se exige a lo editado, sin imagen con que compararlo: la revisión de malla de
    verificar.py y el aviso de trazo fino de letras.py. [(qué, pasa, valor)]"""
    import verificar
    escena = trimesh.load(glb, process=False)
    geos = list(escena.geometry.values())
    r = verificar.revisar_malla(geos[0] if len(geos) == 1 else trimesh.util.concatenate(geos))
    perdida = s.area_perdida(base, acabar(base, bisel))
    return [("trazo fino", perdida <= s.PERDIDA_MAX, f"el redondeo se come el {perdida:.1%} de la pieza que más pierde (máx. {s.PERDIDA_MAX:.0%})"),
            ("malla cerrada", r["estanca"], str(r["estanca"])),
            ("canto en todas las piezas", r["piezas_sin_canto"] == 0, f"{r['piezas_sin_canto']} sin canto"),
            ("normal del frente exacta", r["normal_frente_ok"], str(r["normal_frente_ok"])),
            ("normal del dorso exacta", r["normal_dorso_ok"], str(r["normal_dorso_ok"])),
            ("material", r["material"] == "laca", str(r["material"]))]


def web(origen, destino):
    """La versión web (meshopt), con el mismo comando que el README. None si salió bien;
    si no, por qué (sin npx, o sin internet la primera vez)."""
    npx = shutil.which("npx")
    if not npx:
        return "no está npx (Node.js)"
    destino.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run([npx, "-y", "@gltf-transform/cli@4", "optimize", str(origen), str(destino),
                            "--compress", "meshopt", "--simplify", "false"], capture_output=True, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return "gltf-transform no terminó en 3 min"
    return None if r.returncode == 0 and destino.exists() else (r.stderr.strip().splitlines() or ["falló"])[-1]


def generar(nombre, doc, capas):
    """Las tres versiones de la galería: detallada, ligera y web. Si la detallada no pasa la
    revisión, solo queda ella (para poder mirarla) y ni ligera ni web: nada se entrega
    rechazado. Las de una generación anterior con ese nombre se borran, para que no
    quede una ligera vieja junto a una detallada nueva."""
    if protegido(nombre):
        raise ValueError(f"glb/{nombre}.glb no salió del editor: elige otro nombre")
    guardar(nombre, doc)
    base = planta(capas, doc.get("simetria"))
    info = malla(nombre, doc, capas, SALIDA, base=base)
    comprobaciones = revisar(SALIDA / "glb" / f"{nombre}.glb", base, float(doc["ajustes"]["bisel"]))
    aprobado = all(ok for _, ok, _ in comprobaciones)
    ligera = f"{nombre}-ligera"
    rutas = {"ligera": SALIDA / "glb" / f"{ligera}.glb", "web": SALIDA / "glb" / "web" / f"{ligera}.glb"}
    for ruta in [*rutas.values(), SALIDA / "svg" / f"{ligera}.svg"]:
        ruta.unlink(missing_ok=True)
    archivos, aviso_web = [f"glb/{nombre}.glb"], None
    if aprobado:
        malla(ligera, doc, capas, SALIDA, ligera=True, base=base)
        archivos.append(f"glb/{ligera}.glb")
        aviso_web = web(rutas["ligera"], rutas["web"])
        if aviso_web is None:
            archivos.append(f"glb/web/{ligera}.glb")
    return {**info, "aprobado": aprobado, "archivos": archivos, "aviso_web": aviso_web,
            "comprobaciones": [{"que": q, "pasa": bool(ok), "valor": v} for q, ok, v in comprobaciones]}


def previa(doc, capas):
    """La malla real para la vista 3D, sin tocar glb/: se exporta a un temporal y se lee.
    Con el canto de three.js (ExtrudeGeometry) la vista mentía: en las esquinas que entran,
    redondeadas a 0,6 × canto, hundir el contorno un canto entero lo cruzaba consigo mismo
    y salían caras torcidas en los huecos que el GLB no tiene."""
    with tempfile.TemporaryDirectory() as d:
        malla("previa", doc, capas, d)
        return (Path(d) / "glb" / "previa.glb").read_bytes()


# Campos que conoce este editor. Lo que no esté aquí se rechaza al guardar y al generar:
# un editor anterior que ignorase un campo nuevo (p. ej. un trazo) lo borraría en silencio
# al guardar.
CAMPOS = {
    "doc": {"version", "origen", "capas", "ajustes", "simetria"},
    "capa": {"id", "nombre", "op", "visible", "anillos", "t", "costuras", "bloqueada", "trazo", "abierto"},
    "nodo": {"p", "ent", "sal", "tipo"},
}


def validar(doc):
    """ValueError con los campos desconocidos del documento, si los hay."""
    raros = set(doc) - CAMPOS["doc"]
    for c in doc.get("capas", []):
        raros |= {f"capa.{k}" for k in set(c) - CAMPOS["capa"]}
        for a in c.get("anillos", []) if isinstance(c.get("anillos"), list) else []:
            for n in a:
                if isinstance(n, dict):
                    raros |= {f"nodo.{k}" for k in set(n) - CAMPOS["nodo"]}
    if raros:
        raise ValueError(f"campos que este editor no conoce: {', '.join(sorted(raros))}")


def guardar(nombre, doc):
    validar(doc)
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
        if self.path in ("/api/contornear", "/api/desplazar", "/api/engrosar"):
            try:
                if self.path == "/api/contornear":
                    return self.responder({"capas": contornear(datos["capas"])})
                if self.path == "/api/desplazar":
                    return self.responder({"capas": desplazar(datos["capas"], float(datos["d"]))})
                return self.responder(engrosar_lo_necesario(datos["capas"], float(datos["bisel"]), datos.get("simetria")))
            except Exception as e:
                return self.responder({"error": f"{type(e).__name__}: {e}"}, 422)
        if self.path == "/api/svg":
            try:
                texto = exportar_svg(datos["capas"], datos.get("simetria"), datos["color"])
            except Exception as e:
                return self.responder({"error": f"{type(e).__name__}: {e}"}, 422)
            return self.responder({"svg": texto})
        if self.path == "/api/importar":  # el nombre es el del archivo: importar() lo limpia
            try:
                return self.responder(importar(str(datos.get("nombre", "")), datos["svg"]))
            except (ValueError, ET.ParseError) as e:
                return self.responder({"error": f"no se pudo importar el SVG: {e}"}, 422)
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


class Servidor(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # el navegador cancela peticiones que ya no le sirven (una /api/combinar vieja al
        # seguir editando): el socket roto no es un error del servidor
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=8792)
    ap.add_argument("--salida", type=Path, default=s.RAIZ)
    args = ap.parse_args()
    SALIDA = args.salida.resolve()
    print(f"Editor en http://localhost:{args.puerto}/editor.html", flush=True)
    Servidor(("127.0.0.1", args.puerto), Manejador).serve_forever()
