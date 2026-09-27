"""SVG externo (un logotipo exportado de Figma, Illustrator…) -> capas del editor con curvas.

Uso:  .venv/bin/python tools/leer_svg.py logo.svg        (resumen: capas, nodos, marco)

Lee path (M L H V C S Q T A Z, absolutos y relativos), rect (con esquinas redondeadas),
circle, ellipse, polygon y polyline, con el transform de cada elemento y de sus grupos, y
los estilos de atributo, de style="…" y de clase (<style> con selectores .clase).
Las cuadráticas pasan a cúbicas de forma exacta; los arcos, a cúbicas de ≤ 90° (error
~2,7e-4 del radio). Lo que no rellena (fill="none", defs, clipPath, mask, display:none…)
no entra: un logotipo hecho solo de trazos (stroke) hay que pasarlo a contornos antes.

Cada elemento es una capa «unir» con relleno evenodd, como las del editor. Con
fill-rule="nonzero" (el de por defecto) casi siempre da lo mismo; si no, se quitan los
anillos que no cambian el relleno al cruzarlos (una subruta dentro de otra con el mismo
sentido, que nonzero rellena y evenodd vaciaría) y, si ni así, cada anillo va en su capa,
«unir» o «restar» según quede relleno por dentro.

El resultado se escala a diámetro 1 (el lado mayor de la caja de todo), centrado en el
origen y con y hacia arriba, como los símbolos.
"""
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import shapely
import shapely.affinity
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
import curvas  # noqa: E402

FUERA = {"defs", "clipPath", "mask", "symbol", "pattern", "marker", "linearGradient", "radialGradient",
         "filter", "style", "script", "title", "desc", "metadata", "foreignObject", "text", "image", "use"}
GRUPOS = {"svg", "g", "a", "switch"}
HEREDA = ("fill", "fill-rule", "visibility", "fill-opacity", "stroke", "stroke-width", "stroke-opacity",
          "stroke-linecap", "stroke-linejoin", "stroke-miterlimit")
EXTREMOS = {"butt": "plano", "round": "redondo", "square": "cuadrado"}
UNIONES = {"miter": "inglete", "miter-clip": "inglete", "arcs": "inglete", "round": "redonda", "bevel": "bisel"}
IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)  # afín [a b c d e f], como matrix() de SVG
K_ARCO = 4 / 3


# ---------- afines
def mul(A, B):
    return (A[0] * B[0] + A[2] * B[1], A[1] * B[0] + A[3] * B[1], A[0] * B[2] + A[2] * B[3],
            A[1] * B[2] + A[3] * B[3], A[0] * B[4] + A[2] * B[5] + A[4], A[1] * B[4] + A[3] * B[5] + A[5])


def aplicar(M, p):
    return (M[0] * p[0] + M[2] * p[1] + M[4], M[1] * p[0] + M[3] * p[1] + M[5])


def transform(texto):
    """transform="…" -> afín. matrix, translate, scale, rotate (con centro), skewX, skewY."""
    M = IDENT
    for f, args in re.findall(r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)", texto or ""):
        v = [float(x) for x in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", args)]
        if f == "matrix" and len(v) == 6:
            T = tuple(v)
        elif f == "translate":
            T = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif f == "scale":
            T = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif f == "rotate":
            a = math.radians(v[0])
            T = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
            if len(v) == 3:
                T = mul(mul((1, 0, 0, 1, v[1], v[2]), T), (1, 0, 0, 1, -v[1], -v[2]))
        elif f == "skewX":
            T = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
        elif f == "skewY":
            T = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
        else:
            continue
        M = mul(M, T)
    return M


# ---------- trayectos
class Lector:
    """Números de un d="…" o points="…" uno a uno. Las banderas de un arco son un solo
    carácter y pueden ir pegadas («a1 1 0 00 1 1»): se leen aparte."""
    NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
    SEP = re.compile(r"[\s,]*")

    def __init__(self, texto):
        self.t, self.i = texto, 0

    def saltar(self):
        self.i = self.SEP.match(self.t, self.i).end()

    def hay_numero(self):
        self.saltar()
        return bool(self.NUM.match(self.t, self.i))

    def num(self):
        self.saltar()
        m = self.NUM.match(self.t, self.i)
        if not m:
            raise ValueError(f"se esperaba un número en «{self.t[self.i:self.i + 20]}»")
        self.i = m.end()
        return float(m.group())

    def bandera(self):
        self.saltar()
        ch = self.t[self.i:self.i + 1]
        if ch not in ("0", "1"):
            raise ValueError(f"bandera de arco no válida en «{self.t[self.i:self.i + 20]}»")
        self.i += 1
        return ch == "1"

    def comando(self):
        self.saltar()
        ch = self.t[self.i:self.i + 1]
        if ch and ch in "MmLlHhVvCcSsQqTtAaZz":
            self.i += 1
            return ch
        return None


def arco(p0, rx, ry, phi, grande, barrido, p1):
    """Arco de SVG (forma por extremos) -> cúbicas de ≤ 90°. Apéndice F.6 de SVG 1.1."""
    if p0 == p1:
        return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0:
        return [("recta", p1)]
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = c * dx + s * dy, -s * dx + c * dy
    k = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if k > 1:  # radios demasiado pequeños: se agrandan lo justo
        rx, ry = rx * math.sqrt(k), ry * math.sqrt(k)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    f = math.sqrt(max(0.0, num / (rx * rx * y1 * y1 + ry * ry * x1 * x1)))
    if grande == barrido:
        f = -f
    cx1, cy1 = f * rx * y1 / ry, -f * ry * x1 / rx
    cx, cy = c * cx1 - s * cy1 + (p0[0] + p1[0]) / 2, s * cx1 + c * cy1 + (p0[1] + p1[1]) / 2
    ang = lambda ux, uy: math.atan2(uy, ux)  # noqa: E731
    t0 = ang((x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = ang((-x1 - cx1) / rx, (-y1 - cy1) / ry) - t0
    if barrido and dt < 0:
        dt += 2 * math.pi
    elif not barrido and dt > 0:
        dt -= 2 * math.pi
    n = max(1, math.ceil(abs(dt) / (math.pi / 2) - 1e-9))
    h = dt / n
    kk = K_ARCO * math.tan(h / 4)
    punto = lambda t: (cx + c * rx * math.cos(t) - s * ry * math.sin(t), cy + s * rx * math.cos(t) + c * ry * math.sin(t))  # noqa: E731
    deriv = lambda t: (-c * rx * math.sin(t) - s * ry * math.cos(t), -s * rx * math.sin(t) + c * ry * math.cos(t))  # noqa: E731
    tramos = []
    for j in range(n):
        a, b = t0 + j * h, t0 + (j + 1) * h
        pa, pb, da, db = punto(a), punto(b), deriv(a), deriv(b)
        fin = p1 if j == n - 1 else pb  # el último acaba justo en el extremo pedido
        tramos.append(((pa[0] + kk * da[0], pa[1] + kk * da[1]), (pb[0] - kk * db[0], pb[1] - kk * db[1]), fin))
    return tramos


def subrutas(d):
    """d="…" -> subrutas, cada una [inicio, [tramo…], cerrada] con tramo ("recta", p) o
    (c1, c2, p); cerrada si acaba en Z (para los trazos: el relleno cierra siempre)."""
    L = Lector(d)
    rutas, cmd, cerrada = [], None, False
    cur = ini = (0.0, 0.0)
    ultimo_c = ultimo_q = None  # el último punto de control, para S y T
    while True:
        nuevo = L.comando()
        if nuevo:
            cmd = nuevo
            if cmd in "Zz":
                if rutas:
                    cur, cerrada = ini, True
                    rutas[-1][2] = True
                ultimo_c = ultimo_q = None
                continue
        elif cmd is None or cmd in "Zz" or not L.hay_numero():
            L.saltar()
            if L.i >= len(L.t):
                break
            raise ValueError(f"trayecto no válido en «{L.t[L.i:L.i + 20]}»")
        rel = cmd.islower()
        C = cmd.upper()
        o = cur if rel else (0.0, 0.0)
        pt = lambda x, y: (o[0] + x, o[1] + y)  # noqa: E731
        c_prev, q_prev = ultimo_c, ultimo_q
        ultimo_c = ultimo_q = None
        if C == "M":
            cur = ini = pt(L.num(), L.num())
            rutas.append([cur, [], False])
            cerrada = False
            cmd = "l" if rel else "L"  # los pares que siguen a una M son rectas
            continue
        if not rutas or cerrada:  # dibujar tras Z sin M: otra subruta, desde el inicio de la anterior
            rutas.append([cur, [], False])
            ini, cerrada = cur, False
        tramos = rutas[-1][1]
        if C == "L":
            cur = pt(L.num(), L.num())
            tramos.append(("recta", cur))
        elif C == "H":
            cur = (L.num() + (cur[0] if rel else 0), cur[1])
            tramos.append(("recta", cur))
        elif C == "V":
            cur = (cur[0], L.num() + (cur[1] if rel else 0))
            tramos.append(("recta", cur))
        elif C == "C":
            c1, c2, p = pt(L.num(), L.num()), pt(L.num(), L.num()), pt(L.num(), L.num())
            tramos.append((c1, c2, p))
            cur, ultimo_c = p, c2
        elif C == "S":
            c1 = (2 * cur[0] - c_prev[0], 2 * cur[1] - c_prev[1]) if c_prev else cur
            c2, p = pt(L.num(), L.num()), pt(L.num(), L.num())
            tramos.append((c1, c2, p))
            cur, ultimo_c = p, c2
        elif C in "QT":
            if C == "Q":
                q = pt(L.num(), L.num())
            else:
                q = (2 * cur[0] - q_prev[0], 2 * cur[1] - q_prev[1]) if q_prev else cur
            p = pt(L.num(), L.num())
            # cuadrática -> cúbica, exacta: los controles a 2/3 del de la cuadrática
            tramos.append(((cur[0] + 2 / 3 * (q[0] - cur[0]), cur[1] + 2 / 3 * (q[1] - cur[1])),
                           (p[0] + 2 / 3 * (q[0] - p[0]), p[1] + 2 / 3 * (q[1] - p[1])), p))
            cur, ultimo_q = p, q
        elif C == "A":
            rx, ry, phi = L.num(), L.num(), L.num()
            grande, barrido = L.bandera(), L.bandera()
            p = pt(L.num(), L.num())
            tramos += arco(cur, rx, ry, phi, grande, barrido, p)
            cur = p
    return rutas


def puntos(texto):
    L, v = Lector(texto), []
    while L.hay_numero():
        v.append(L.num())
    return [(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]


def rect(x, y, w, h, rx, ry):
    if w <= 0 or h <= 0:
        return ""
    if rx is None and ry is None:
        rx = ry = 0.0
    rx = ry if rx is None else rx
    ry = rx if ry is None else ry
    rx, ry = min(abs(rx), w / 2), min(abs(ry), h / 2)
    if rx == 0 or ry == 0:
        return f"M{x},{y}H{x + w}V{y + h}H{x}Z"
    return (f"M{x + rx},{y}H{x + w - rx}A{rx},{ry} 0 0 1 {x + w},{y + ry}V{y + h - ry}"
            f"A{rx},{ry} 0 0 1 {x + w - rx},{y + h}H{x + rx}A{rx},{ry} 0 0 1 {x},{y + h - ry}"
            f"V{y + ry}A{rx},{ry} 0 0 1 {x + rx},{y}Z")


def elipse(cx, cy, rx, ry):
    if rx <= 0 or ry <= 0:
        return ""
    return (f"M{cx + rx},{cy}A{rx},{ry} 0 0 1 {cx},{cy + ry}A{rx},{ry} 0 0 1 {cx - rx},{cy}"
            f"A{rx},{ry} 0 0 1 {cx},{cy - ry}A{rx},{ry} 0 0 1 {cx + rx},{cy}Z")


def trayecto(el, attr, trazo=False):
    """El d="…" equivalente de una figura básica ("" si no rellena nada). trazo: el camino
    que se traza, en el que <line> existe y <polyline> no se cierra."""
    f = lambda k, v=0.0: longitud(el.get(k), v)  # noqa: E731
    t = el.tag
    if t == "path":
        return el.get("d", "")
    if t == "rect":
        return rect(f("x"), f("y"), f("width"), f("height"),
                    longitud(el.get("rx"), None), longitud(el.get("ry"), None))
    if t == "circle":
        return elipse(f("cx"), f("cy"), f("r"), f("r"))
    if t == "ellipse":
        return elipse(f("cx"), f("cy"), f("rx"), f("ry"))
    if t == "line" and trazo:
        return f"M{f('x1')},{f('y1')}L{f('x2')},{f('y2')}"
    if t in ("polygon", "polyline"):
        pts = puntos(el.get("points", ""))
        if trazo and len(pts) >= 2:
            return "M" + "L".join(f"{x},{y}" for x, y in pts) + ("Z" if t == "polygon" else "")
        return "M" + "L".join(f"{x},{y}" for x, y in pts) + "Z" if len(pts) >= 3 else ""
    return ""


def longitud(v, defecto):
    """«12», «12px», «1.5e2»; las unidades absolutas se toman como usuario (el SVG se escala
    entero a diámetro 1, así que solo importa que todo vaya en la misma)."""
    if v is None:
        return defecto
    m = re.match(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)", v)
    return float(m.group(1)) if m else defecto


# ---------- estilos
def reglas_css(raiz):
    """<style> con selectores de clase (.cls-1{fill:#e30613}), como exporta Illustrator."""
    reglas = {}
    for st in raiz.iter("style"):
        texto = re.sub(r"/\*.*?\*/", "", st.text or "", flags=re.S)
        for sel, cuerpo in re.findall(r"([^{}]+)\{([^}]*)\}", texto):
            decl = declaraciones(cuerpo)
            for s in sel.split(","):
                m = re.fullmatch(r"\s*\.([\w-]+)\s*", s)
                if m:
                    reglas.setdefault(m.group(1), {}).update(decl)
    return reglas


def declaraciones(texto):
    return {k.strip(): v.strip() for k, v in (d.split(":", 1) for d in (texto or "").split(";") if ":" in d)}


def estilo(el, padre, css):
    """Las propiedades que importan, con herencia: atributo < clase < style="…"."""
    propio = {k: el.get(k) for k in (*HEREDA, "display", "opacity") if el.get(k) is not None}
    for c in (el.get("class") or "").split():
        propio.update({k: v for k, v in css.get(c, {}).items()})
    propio.update(declaraciones(el.get("style")))
    return {**{k: padre[k] for k in HEREDA if k in padre}, **propio}


def rellena(e):
    fill = e.get("fill", "black").strip()
    if fill == "none" or fill.startswith("url(") and "none" in fill:
        return False
    if e.get("visibility", "visible") in ("hidden", "collapse"):
        return False
    try:
        return float(e.get("fill-opacity", 1)) > 0 and float(e.get("opacity", 1)) > 0
    except ValueError:
        return True


def traza(e):
    """El grosor del trazo (en unidades de su elemento) o 0 si no se traza."""
    st = e.get("stroke", "none").strip()
    if st == "none" or e.get("visibility", "visible") in ("hidden", "collapse"):
        return 0.0
    try:
        if float(e.get("stroke-opacity", 1)) <= 0 or float(e.get("opacity", 1)) <= 0:
            return 0.0
    except ValueError:
        pass
    return max(0.0, longitud(e.get("stroke-width"), 1.0))


def geo_trazo(pts, abierto, w, tr):
    """El trazo de una polilínea con shapely (como forma_trazo de tools/editor.py)."""
    kw = {"join_style": {"inglete": "mitre", "redonda": "round", "bisel": "bevel"}[tr["uniones"]],
          "mitre_limit": tr["inglete"], "quad_segs": 16}
    if abierto:
        return LineString(pts).buffer(w / 2, cap_style={"plano": "flat", "redondo": "round", "cuadrado": "square"}[tr["extremos"]], **kw)
    p = poligono(pts)
    return p.buffer(w / 2, **kw).difference(p.buffer(-w / 2, **kw))


# ---------- anillos
def a_nodos(ruta, M, cerrar=True):
    """Una subruta en coordenadas del SVG -> anillo de nodos (sin escalar) tras aplicar M.
    Una afín lleva una Bézier a otra: basta con transformar los controles. cerrar=False:
    un camino abierto (el último nodo no se funde con el primero)."""
    inicio, tramos = ruta[0], ruta[1]
    P = aplicar(M, inicio)
    segs = [(("recta", aplicar(M, t[1])) if t[0] == "recta" else (aplicar(M, t[0]), aplicar(M, t[1]), aplicar(M, t[2])))
            for t in tramos]
    nodos = [{"p": P, "ent": None, "sal": None}]
    for s in segs:
        q = s[-1] if s[0] != "recta" else s[1]
        prev = nodos[-1]
        if s[0] == "recta":
            if math.dist(prev["p"], q) < 1e-12:
                continue
            nodos.append({"p": q, "ent": None, "sal": None})
        else:
            c1, c2 = s[0], s[1]
            if math.dist(prev["p"], q) < 1e-12 and math.dist(c1, q) < 1e-12 and math.dist(c2, q) < 1e-12:
                continue
            prev["sal"] = rel(c1, prev["p"])
            nodos.append({"p": q, "ent": rel(c2, q), "sal": None})
    # cerrar: el último nodo sobre el primero se funde con él (su tirador de entrada pasa al primero)
    if cerrar and len(nodos) > 1 and math.dist(nodos[-1]["p"], nodos[0]["p"]) < 1e-9 * (1 + abs(P[0]) + abs(P[1])):
        nodos[0]["ent"] = nodos.pop()["ent"]
    return nodos


def rel(c, p):
    v = (c[0] - p[0], c[1] - p[1])
    return None if math.hypot(*v) < 1e-12 else v


def polilinea(anillo, tol):
    return curvas.aplanar(anillo, tol)


def poligono(pts):
    g = shapely.make_valid(Polygon(pts))
    return unary_union([x for x in getattr(g, "geoms", [g]) if x.geom_type in ("Polygon", "MultiPolygon")])


def evenodd(polis):
    forma = Polygon()
    for p in polis:
        forma = forma.symmetric_difference(p)
    return forma


def vueltas(pt, anillos):
    """Número de vueltas (winding number) de los anillos alrededor de pt."""
    x, y = pt
    w = 0
    for a in anillos:
        n = len(a)
        for i in range(n):
            (x0, y0), (x1, y1) = a[i], a[(i + 1) % n]
            if y0 <= y < y1 and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) > 0:
                w += 1
            elif y1 <= y < y0 and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) < 0:
                w -= 1
    return w


def relleno_nonzero(planos):
    """La forma que rellena nonzero: las caras que dejan los anillos, con vueltas ≠ 0."""
    lineas = unary_union([LineString([*a, a[0]]) for a in planos])
    return unary_union([f for f in polygonize(lineas) if vueltas(f.representative_point().coords[0], planos) != 0])


def lados(a, eps):
    """Dos puntos a un lado y otro del anillo, junto al punto medio de su tramo más largo."""
    n = len(a)
    i = max(range(n), key=lambda k: math.dist(a[k], a[(k + 1) % n]))
    (x0, y0), (x1, y1) = a[i], a[(i + 1) % n]
    L = math.dist(a[i], a[(i + 1) % n])
    mx, my, nx, ny = (x0 + x1) / 2, (y0 + y1) / 2, -(y1 - y0) / L, (x1 - x0) / L
    return (mx + nx * eps, my + ny * eps), (mx - nx * eps, my - ny * eps)


def repartir(anillos, regla, tam):
    """Los anillos de un elemento -> [(op, [anillo…])], capas que dan su relleno. tam: el
    del dibujo entero, en unidades del SVG (tolerancias)."""
    planos = [polilinea(a, 1e-5 * tam) for a in anillos]
    # el área, la del polígono ya válido: la de un contorno en ocho (dos lóbulos de sentido
    # contrario) con la fórmula del área con signo da 0
    validos = [(a, p, g) for a, p in zip(anillos, planos) if len(p) >= 3 for g in [poligono(p)] if g.area > 0]
    if not validos:
        return []
    anillos, planos, polis = [list(x) for x in zip(*validos)]
    todos = evenodd(polis)
    if regla == "evenodd":
        return [("unir", anillos)]
    verdad = relleno_nonzero(planos)
    igual = lambda g: g.symmetric_difference(verdad).area <= 1e-9 * tam * tam  # noqa: E731
    if igual(todos):
        return [("unir", anillos)]
    # quitar los anillos que no cambian el relleno al cruzarlos
    eps = 1e-7 * tam
    cambian = [k for k, p in enumerate(planos)
               if (vueltas(lados(p, eps)[0], planos) != 0) != (vueltas(lados(p, eps)[1], planos) != 0)]
    if cambian and igual(evenodd([polis[k] for k in cambian])):
        return [("unir", [anillos[k] for k in cambian])]
    # cada anillo en su capa, de fuera adentro: unir si por dentro queda relleno, si no restar
    orden = sorted(range(len(anillos)), key=lambda k: -polis[k].area)
    capas = []
    for k in orden:
        dentro = [q for q in lados(planos[k], eps) if polis[k].contains(Point(q))]
        lleno = bool(dentro) and vueltas(dentro[0], planos) != 0
        capas.append(("unir" if lleno else "restar", [anillos[k]]))
    return capas


# ---------- todo
def recorrer(el, M, padre, css):
    """(elemento, afín acumulada, estilo) de cada figura que rellena."""
    tag = el.tag
    e = estilo(el, padre, css)
    if tag in FUERA or e.get("display") == "none":
        return
    try:
        if float(e.get("opacity", 1)) <= 0:
            return
    except ValueError:
        pass
    M = mul(M, transform(el.get("transform")))
    if tag in GRUPOS:
        for h in el:
            yield from recorrer(h, M, e, css)
    elif rellena(e) or traza(e):
        yield el, M, e


def sin_espacios(raiz):
    for el in raiz.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
        for k in list(el.attrib):
            if "}" in k:
                el.attrib[k.split("}", 1)[1]] = el.attrib.pop(k)
    return raiz


def leer(texto):
    """Texto de un SVG -> (capas, marco). Cada capa {"nombre", "op", "anillos"} con anillos
    de nodos {"p", "ent", "sal"} ya en el mundo (diámetro 1, centro en el origen, y hacia
    arriba); marco {"s", "cx", "cy"}: mundo = ((x − cx)·s, −(y − cy)·s). Un elemento con
    trazo da además una capa de trazo encima de la de su relleno ({"trazo", "abierto"}),
    con el grosor escalado; con una escala no uniforme (el grosor variaría), su contorno
    exacto como relleno."""
    raiz = sin_espacios(ET.fromstring(texto))
    if raiz.tag != "svg":
        raise ValueError("no es un SVG")
    css = reglas_css(raiz)
    figuras = []  # ("relleno", nombre, rutas, regla) | ("trazo", nombre, rutas, abierto, w, tr) | ("contorno", nombre, geo)
    for n, (el, M, e) in enumerate(recorrer(raiz, IDENT, {}, css), 1):
        nombre = el.get("label") or el.get("id") or f"{ {'path': 'Trazado', 'rect': 'Rectángulo', 'circle': 'Círculo', 'ellipse': 'Elipse', 'line': 'Línea'}.get(el.tag, 'Polígono')} {n}"
        d = trayecto(el, e) if rellena(e) else ""
        rutas = [a for a in (a_nodos(r, M) for r in subrutas(d)) if len(a) >= 2] if d.strip() else []
        if rutas:
            figuras.append(("relleno", nombre, rutas, e.get("fill-rule", "nonzero").strip()))
        w = traza(e)
        d = trayecto(el, e, trazo=True) if w > 0 else ""
        if not d.strip():
            continue
        tr = {"extremos": EXTREMOS.get(e.get("stroke-linecap", "butt").strip(), "plano"),
              "uniones": UNIONES.get(e.get("stroke-linejoin", "miter").strip(), "inglete"),
              "inglete": max(1.0, longitud(e.get("stroke-miterlimit"), 4.0)), "posicion": "centro"}
        det = abs(M[0] * M[3] - M[1] * M[2])
        a2, b2 = M[0] ** 2 + M[1] ** 2, M[2] ** 2 + M[3] ** 2  # valores singulares de M: iguales si es semejanza
        uniforme = abs(a2 - b2) <= 1e-4 * max(a2, b2) and abs(M[0] * M[2] + M[1] * M[3]) <= 1e-4 * max(a2, b2)
        subs = subrutas(d)
        if uniforme:
            nombre_t = f"{nombre} · trazo" if rutas else nombre
            for abierto in (False, True):
                grupo = [a for a in (a_nodos(r, M, cerrar=not abierto) for r in subs if (not r[2]) == abierto) if len(a) >= 2]
                if grupo:
                    figuras.append(("trazo", nombre_t, grupo, abierto, w * math.sqrt(det), tr))
        else:  # el trazo se hace en las coordenadas del elemento y luego se transforma
            partes = []
            for r in subs:
                a = a_nodos(r, IDENT, cerrar=r[2])
                pts = curvas.aplanar(a, 1e-4 * w, cerrado=r[2])
                if len(pts) >= 2:
                    partes.append(geo_trazo(pts, not r[2], w, tr))
            if partes:
                geo = shapely.affinity.affine_transform(unary_union(partes), [M[0], M[2], M[1], M[3], M[4], M[5]])
                figuras.append(("contorno", f"{nombre} · trazo" if rutas else nombre, geo))
    if not figuras:
        raise ValueError("no hay ninguna figura con relleno ni con trazo")
    # tamaño: la caja de los controles abarca la curva y sirve para fijar la tolerancia con
    # la que se aplana para medir la de verdad; los trazos cuentan con su grosor
    caja = lambda pts: (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))  # noqa: E731
    x0, y0, x1, y1 = caja([n["p"] for f in figuras if f[0] != "contorno" for a in f[2] for n in a]
                          + [q for f in figuras if f[0] == "contorno" for q in shapely.get_coordinates(f[2]).tolist()])
    tol = 1e-6 * max(x1 - x0, y1 - y0, 1e-300)
    pts = []
    for f in figuras:
        if f[0] == "relleno":
            pts += [q for a in f[2] for q in polilinea(a, tol)]
        elif f[0] == "trazo":
            for a in f[2]:
                g = geo_trazo(curvas.aplanar(a, tol, cerrado=not f[3]), f[3], f[4], f[5])
                pts += shapely.get_coordinates(g).tolist()
        else:
            pts += shapely.get_coordinates(f[2]).tolist()
    x0, y0, x1, y1 = caja(pts)
    tam = max(x1 - x0, y1 - y0)
    if tam <= 0:
        raise ValueError("el dibujo no tiene tamaño")
    s, cx, cy = 1 / tam, (x0 + x1) / 2, (y0 + y1) / 2
    mundo_p = lambda p: [(p[0] - cx) * s, -(p[1] - cy) * s]  # noqa: E731
    mundo_v = lambda v: None if v is None else [v[0] * s, -v[1] * s]  # noqa: E731
    mundo = lambda anillos: [[{"p": mundo_p(n["p"]), "ent": mundo_v(n["ent"]), "sal": mundo_v(n["sal"])} for n in a] for a in anillos]  # noqa: E731
    capas = []
    for f in figuras:
        if f[0] == "relleno":
            _, nombre, rutas, regla = f
            partes = repartir(rutas, "evenodd" if regla == "evenodd" else "nonzero", tam)
            for j, (op, anillos) in enumerate(partes):
                capas.append({"nombre": nombre if len(partes) == 1 else f"{nombre} · {j + 1}", "op": op, "anillos": mundo(anillos)})
        elif f[0] == "trazo":
            _, nombre, rutas, abierto, w, tr = f
            capas.append({"nombre": nombre, "op": "unir", "anillos": mundo(rutas), "trazo": {**tr, "ancho": w * s},
                          **({"abierto": True} if abierto else {})})
        else:
            geo = shapely.affinity.affine_transform(f[2], [s, 0, 0, -s, -cx * s, cy * s])
            anillos = [curvas.ajustar_anillo(list(a.coords)[:-1], 0.0002)[0] for p in getattr(geo, "geoms", [geo])
                       if p.geom_type == "Polygon" for a in [p.exterior, *p.interiors]]
            capas.append({"nombre": f[1], "op": "unir", "anillos": anillos})
    return capas, {"s": s, "cx": cx, "cy": cy}


def main():
    texto = Path(sys.argv[1]).read_text()
    capas, marco = leer(texto)
    for c in capas:
        print(f"{c['op']:6} {c['nombre']:30} anillos {len(c['anillos'])}  nodos {sum(map(len, c['anillos']))}")
    print(marco)


if __name__ == "__main__":
    main()
