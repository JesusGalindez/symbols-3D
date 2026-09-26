"""Redibuja un símbolo de trazo geométrico con rectas y círculos exactos.

Idea: todo borde del diseño es una vertical, una horizontal o un círculo
concéntrico. Se detectan esas líneas en la imagen, parten el disco en caras,
y cada cara es entera roja o entera crema: se decide por mayoría.

Uso:  .venv/bin/python tools/redibujar.py fuentes/shou-circular.png shou-circular
      añade --ligera para la versión de galería (-> glb/<nombre>-ligera.glb)
      añade --sin-simetria si el símbolo no es simétrico, o --simetria-ab si solo lo es arriba-abajo
"""
import json
import sys
from pathlib import Path

import numpy as np
import shapely
import trimesh
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union

sys.path.insert(0, str(Path(__file__).parent))
import simbolo as s  # noqa: E402

SEGMENTOS = 360      # lados por círculo completo
MIN_RECTA = 0.02     # un borde recto cuenta si mide al menos esto (fracción del diámetro)
FUSION = 0.004       # bordes más cercanos que esto son el mismo
SIMETRIA = True      # --sin-simetria para caracteres no simétricos (p. ej. 福)
SIM_AB = False       # --simetria-ab: solo arriba-abajo (ganchos que giran igual a ambos lados)
SIM_LR = False       # --simetria-lr: solo izquierda-derecha (p. ej. shou-sello)
DISCO = False        # lo pone cuadrar(): el dibujo no llena el disco, normalizar con el círculo
ACHATADO = 1.0      # lo pone cuadrar(): alto/ancho del disco en la imagen (captura achatada)


def disco_incompleto(c):
    """Si el dibujo no llena el disco (囍: arriba y abajo quedan cortos), el recuadro no
    es el círculo. Se ajusta una elipse de ejes horizontal y vertical a los extremos de
    las filas anchas (las de las franjas llegan al borde; las de trazos sueltos, no),
    descartando las que no caen en ella. Elipse y no círculo: una captura puede venir
    achatada un 1 %, y con un círculo el borde se sale por arriba o por abajo.
    Devuelve centro (cx, cy) y semiejes (a horizontal, b vertical) en píxeles de c."""
    h, w = c.shape
    filas = [(y, x_) for y, x_ in ((y, np.nonzero(c[y])[0]) for y in range(h))
             if len(x_) and x_[-1] - x_[0] > 0.5 * w]
    pts = np.array([(x_[0], y) for y, x_ in filas] + [(x_[-1] + 1, y) for y, x_ in filas], float)
    sel = np.ones(len(pts), bool)
    for _ in range(8):
        X, Y = pts[sel, 0], pts[sel, 1]
        A, B, C, D = np.linalg.lstsq(np.stack([X ** 2, Y ** 2, X, Y], 1), np.ones_like(X), rcond=None)[0]
        cx, cy = -C / (2 * A), -D / (2 * B)
        F = 1 + A * cx ** 2 + B * cy ** 2
        a, b = np.sqrt(F / A), np.sqrt(F / B)
        resto = np.abs(np.hypot((pts[:, 0] - cx) / a, (pts[:, 1] - cy) / b) - 1) * a
        sel = resto < 0.004 * max(h, w)
    return cx, cy, a, b


def cuadrar(m):
    """Recorta al disco y fuerza la doble simetría medida (izq-der y arriba-abajo)."""
    global DISCO
    ys, xs = np.where(m)
    c = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(float)
    n = max(c.shape)
    if abs(c.shape[0] - c.shape[1]) > 0.01 * n:
        global ACHATADO
        cx, cy, a, b = disco_incompleto(c)
        ACHATADO = b / a  # se reconstruye redondo y al final se devuelve este achatado
        alto = int(round(c.shape[0] * a / b))
        from PIL import Image
        c = np.asarray(Image.fromarray((c * 255).astype(np.uint8)).resize((c.shape[1], alto), Image.BILINEAR)) / 255
        cy *= a / b
        arriba, izq, n = int(round(a - cy)), int(round(a - cx)), int(round(2 * a))
        c = np.pad(c, ((max(0, arriba), 0), (max(0, izq), 0)))[max(0, -arriba):, max(0, -izq):]
        DISCO = True
    c = np.pad(c, ((0, max(0, n - c.shape[0])), (0, max(0, n - c.shape[1]))))[:n, :n]
    if SIM_AB:
        return (c + c[::-1]) / 2 > 0.5
    if SIM_LR:
        return (c + c[:, ::-1]) / 2 > 0.5
    if not SIMETRIA:
        return c > 0.5
    return (c + c[:, ::-1] + c[::-1] + c[::-1, ::-1]) / 4 > 0.5


def picos(conteo, minimo, fusion):
    """Posiciones con suficientes transiciones, agrupadas."""
    idx = np.where(conteo >= minimo)[0]
    grupos, actual = [], []
    for i in idx:
        if actual and i - actual[-1] > fusion:
            grupos.append(actual)
            actual = []
        actual.append(i)
    if actual:
        grupos.append(actual)
    return [np.average(g, weights=conteo[g]) for g in grupos]


def lineas(c):
    n = c.shape[0]
    minimo, fusion = MIN_RECTA * n, FUSION * n
    # bordes verticales: transiciones izq-der contadas por columna (y horizontales al revés)
    dx = np.abs(np.diff(c.astype(np.int8), axis=1)).sum(0)
    dy = np.abs(np.diff(c.astype(np.int8), axis=0)).sum(1)
    xs = [x + 1 for x in picos(dx, minimo, fusion)]
    ys = [y + 1 for y in picos(dy, minimo, fusion)]
    # círculos: bordes en diagonal (lejos de los ejes) contados por radio
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    r = np.hypot(xx - n / 2, yy - n / 2)
    ang = np.abs(np.arctan2(yy - n / 2, xx - n / 2)) % (np.pi / 2)
    diagonal = np.abs(ang - np.pi / 4) < np.radians(12)
    borde = np.zeros_like(c)
    borde[:, 1:] |= c[:, 1:] != c[:, :-1]
    borde[1:] |= c[1:] != c[:-1]
    if not SIMETRIA:
        # sin simetría los arcos pueden estar en cualquier ángulo (p. ej. el arco izquierdo
        # de 福): vale todo borde cuya normal apunte al centro y no sea horizontal/vertical
        f = c.astype(float)
        f = (f + np.roll(f, 1, 0) + np.roll(f, -1, 0) + np.roll(f, 1, 1) + np.roll(f, -1, 1)) / 5
        gy_, gx_ = np.gradient(f)
        g = np.hypot(gx_, gy_) + 1e-9
        radial = np.abs((gx_ * (xx - n / 2) + gy_ * (yy - n / 2)) / (g * (r + 1e-9))) > 0.98
        eje = np.maximum(np.abs(gx_), np.abs(gy_)) / g > 0.995
        diagonal = radial & ~eje & (g > 0.1)
    hist = np.bincount(r[borde & diagonal].astype(int), minlength=n)
    umbral = (0.25 if SIMETRIA else 0.1) * hist.max()
    if not SIMETRIA:
        # un arco corto con el centro algo desplazado reparte sus votos entre radios
        # vecinos y ninguno llega al umbral (los ganchos de shou-cruz): se suma la ventana
        hist = np.convolve(hist, np.ones(int(fusion) | 1), "same")
    radios = picos(hist, umbral, fusion)
    if not SIMETRIA:
        # un arco es casi vertical/horizontal cerca de su tangente y engaña al conteo:
        # fuera las rectas cuyo apoyo cae sobre un círculo ya detectado
        def sobre_arco(rs):
            return len(rs) and np.mean(np.min(np.abs(rs[:, None] - np.array(radios)[None]), 1) < fusion) > 0.6
        bx = np.zeros_like(c); bx[:, 1:] = c[:, 1:] != c[:, :-1]
        by = np.zeros_like(c); by[1:] = c[1:] != c[:-1]
        xs = [x for x in xs if not sobre_arco(r[:, int(round(x))][bx[:, int(round(x))]])]
        ys = [y for y in ys if not sobre_arco(r[int(round(y))][by[int(round(y))]])]
    return xs, ys, radios, n


def diagonales(c, minimo, xs_=(), ys_=(), radios_=()):
    """Rectas inclinadas (Hough sobre el borde), p. ej. el trazo oblicuo de 福.
    Devuelve (ángulo de la normal, distancia al origen, tramo inicio, tramo fin)."""
    n = c.shape[0]
    borde = np.zeros_like(c)
    borde[:, 1:] |= c[:, 1:] != c[:, :-1]
    borde[1:] |= c[1:] != c[:-1]
    ys, xs = np.nonzero(borde)
    # fuera lo que ya explican rectas y círculos: si no, sus tangentes ganan la votación
    tol = FUSION * n
    explicado = np.zeros(len(xs), bool)
    for x in xs_:
        explicado |= np.abs(xs + 0.5 - x) < tol
    for y in ys_:
        explicado |= np.abs(ys + 0.5 - y) < tol
    # los arcos no quitan píxeles sueltos: una recta que cruza un arco casi tangente
    # (el brazo de shou-cruz) perdía su tramo central y no llegaba a detectarse.
    # Se marca qué píxeles caen en un arco y se descarta la recta si casi todo su apoyo es arco
    en_arco = np.zeros(len(xs), bool)
    for cx, cy, rr, *lado in radios_:
        cerca = np.abs(np.hypot(xs + 0.5 - cx, ys + 0.5 - cy) - rr) < tol
        if lado and lado[0]:  # arco de una sola mitad: al otro lado no explica nada
            cerca &= (xs + 0.5 - n / 2) * lado[0] > 0
        en_arco |= cerca
    ys, xs, en_arco = ys[~explicado], xs[~explicado], en_arco[~explicado]
    angulos = np.radians(np.arange(0, 180, 0.5))
    angulos = angulos[np.array([min(a % 90, 90 - a % 90) > 8 for a in np.degrees(angulos)])]
    rho = np.outer(xs + 0.5, np.cos(angulos)) + np.outer(ys + 0.5, np.sin(angulos))
    rmax = int(np.ceil(np.hypot(n, n)))
    acc = np.zeros((len(angulos), 2 * rmax + 1), int)
    for k in range(len(angulos)):
        acc[k] += np.bincount(np.round(rho[:, k]).astype(int) + rmax, minlength=2 * rmax + 1)
    lineas_ = []
    vivo = np.ones(len(xs), bool)
    idx = np.round(rho).astype(int) + rmax
    filas = np.arange(len(angulos))
    while True:
        k, r = np.unravel_index(acc.argmax(), acc.shape)
        if acc[k, r] < minimo:
            return lineas_
        a, d = angulos[k], r - rmax
        # píxeles que explica esta recta: se retiran de la votación. Si no, un borde
        # levemente curvo daba decenas de rectas casi iguales que cortaban el dibujo en tiras
        en = vivo & (np.abs(rho[:, k] - d) < tol)
        for i in np.nonzero(en)[0]:
            acc[filas, idx[i]] -= 1
        vivo &= ~en
        # descarta tangentes al borde del disco y a los arcos: ahí el círculo imita rectas
        if abs(d - n / 2 * (np.cos(a) + np.sin(a))) < 0.4 * n and en_arco[en].mean() < 0.6:
            # tramos con apoyo real en el borde, no la recta infinita: bordes de ganchos
            # opuestos pueden caer en la misma recta, y de min a max la cruzaba entera
            s_ = np.sort(-(xs[en] + 0.5) * np.sin(a) + (ys[en] + 0.5) * np.cos(a))
            for tramo in np.split(s_, np.nonzero(np.diff(s_) > 0.02 * n)[0] + 1):
                if tramo[-1] - tramo[0] >= MIN_RECTA * n:
                    lineas_.append((a, d, tramo[0] - 0.03 * n, tramo[-1] + 0.03 * n))


def simetrico(vals, n):
    """Empareja cada valor con su espejo y promedia: el dibujo queda exacto."""
    centrados = sorted({round(abs(v - n / 2), 1) for v in vals})
    unidos = picos_lista(centrados, FUSION * n)
    return sorted({n / 2 + s_ * d for d in unidos for s_ in (-1, 1)})


def picos_lista(vals, fusion):
    grupos = []
    for v in vals:
        if grupos and v - grupos[-1][-1] <= fusion:
            grupos[-1].append(v)
        else:
            grupos.append([v])
    return [float(np.mean(g)) for g in grupos]


def ajustar_circulo(c, r0, xs, ys, n, lado=0):
    """Centro y radio propios de un arco (mínimos cuadrados, método de Kåsa). En dibujos
    sin simetría doble los arcos interiores no siempre comparten centro con el disco:
    con centro común, un lado encaja y el otro sale con quiebros."""
    borde = np.zeros_like(c)
    borde[:, 1:] |= c[:, 1:] != c[:, :-1]
    borde[1:] |= c[1:] != c[:-1]
    py, px = np.nonzero(borde)
    px, py = px + 0.5, py + 0.5
    tol = FUSION * n
    sel = np.abs(np.hypot(px - n / 2, py - n / 2) - r0) < 0.01 * n
    for x in xs:
        sel &= np.abs(px - x) > tol
    for y in ys:
        sel &= np.abs(py - y) > tol
    if lado:  # -1 izquierda, +1 derecha: cada mitad puede ser una pieza con su propio arco
        sel &= (px - n / 2) * lado > 0
    cx, cy, r = n / 2, n / 2, r0
    for _ in range(3):  # reajuste con los puntos que de verdad caen en el arco
        if sel.sum() < 50:
            return n / 2, n / 2, r0
        X, Y = px[sel], py[sel]
        A = np.stack([X, Y, np.ones_like(X)], 1)
        sol = np.linalg.lstsq(A, X ** 2 + Y ** 2, rcond=None)[0]
        cx, cy = sol[0] / 2, sol[1] / 2
        r = np.sqrt(sol[2] + cx ** 2 + cy ** 2)
        sel &= np.abs(np.hypot(px - cx, py - cy) - r) < 0.004 * n
    if SIM_AB:
        cy = n / 2
    if SIM_LR:  # arco que existe a ambos lados de un dibujo simétrico: centro en el eje
        cx = n / 2
    if np.hypot(cx - n / 2, cy - n / 2) > 0.03 * n or abs(r - r0) > 0.03 * n:
        return n / 2, n / 2, r0  # ajuste raro: mejor el centro común
    # el ajuste solo vale si explica más borde que el círculo concéntrico: con pocos
    # puntos puede engancharse a otros bordes cercanos (囍: radio 567 en vez de 534)
    lado_ok = (px - n / 2) * lado > 0 if lado else np.ones(len(px), bool)
    apoyo = lambda x0, y0, rr: np.sum(lado_ok & (np.abs(np.hypot(px - x0, py - y0) - rr) < 0.004 * n))
    if apoyo(cx, cy, r) < apoyo(n / 2, n / 2, r0):
        return n / 2, n / 2, r0
    return cx, cy, r


def tramos(c, y, n):
    """Tramos de la horizontal y (en c; para una vertical, pasar c.T) con borde real
    a menos de FUSION, alargados 0,03·n por cada lado como las diagonales."""
    tol = max(1, int(round(FUSION * n)))
    fila = int(round(y))
    borde = np.zeros(n, bool)
    for f in range(max(1, fila - tol), min(n, fila + tol + 1)):
        borde |= c[f] != c[f - 1]
    x_ = np.nonzero(borde)[0]
    if not len(x_):
        return []
    grupos = np.split(x_, np.nonzero(np.diff(x_) > 0.02 * n)[0] + 1)
    return [(g[0] - 0.03 * n, g[-1] + 1 + 0.03 * n) for g in grupos if g[-1] - g[0] >= MIN_RECTA * n]


def redibujar(c, xs, ys, radios, n):
    R = n / 2
    centro = Point(R, R)
    # sin simetría doble, dos círculos casi iguales suelen ser un solo arco algo
    # descentrado: si se dejan los dos, el voto salta entre ellos y deja un escalón
    radios = sorted(set(picos_lista(sorted(radios + [R]), (FUSION if SIMETRIA else 0.015) * n)))
    radios[-1] = R  # el borde exterior es el disco completo
    if not SIM_AB:
        trazos = [LineString([(x, -1), (x, n + 1)]) for x in xs]
        trazos += [LineString([(-1, y), (n + 1, y)]) for y in ys]
    else:
        # con --simetria-ab, solo donde la recta tiene borde de verdad: una horizontal
        # infinita partía la punta de un gancho lejano y dejaba un escalón (shou-cruz).
        # En --sin-simetria no: fu-circular necesita las rectas enteras y sin ellas falla
        trazos = [LineString([(x, a), (x, b)]) for x in xs for a, b in tramos(c.T, x, n)]
        trazos += [LineString([(a, y), (b, y)]) for y in ys for a, b in tramos(c, y, n)]
    if SIMETRIA:
        circulos = [(R, R, r, 0) for r in radios]
    else:
        circulos = [(R, R, R, 0)] + [(*ajustar_circulo(c, r, xs, ys, n, l), l) for r in radios[:-1] for l in (-1, 1)]
    for cx, cy, r, l in circulos:
        aro = Point(cx, cy).buffer(r, quad_segs=SEGMENTOS // 4).exterior
        if l:  # solo su mitad (con un poco de solape para que corte bien en el eje)
            aro = aro.intersection(box(R - l * 0.01 * n, -n, R + l * 2 * n, 2 * n) if l > 0
                                   else box(-n, -n, R + 0.01 * n, 2 * n))
        trazos.append(aro)
    for a, d, s0, s1 in ([] if SIMETRIA else diagonales(c, 0.02 * n, xs, ys, circulos)):
        p0 = np.array([np.cos(a), np.sin(a)]) * d
        t_ = np.array([-np.sin(a), np.cos(a)])
        trazos.append(LineString([p0 + t_ * s0, p0 + t_ * s1]))
    caras = [f for f in polygonize(unary_union(trazos)) if f.representative_point().distance(centro) < R]

    rojas = []
    for f in caras:
        x0, y0, x1, y1 = [int(v) for v in f.bounds]
        gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
        dentro = shapely.contains_xy(f, gx.ravel(), gy.ravel())
        if dentro.sum() == 0:
            dentro_c = [c[min(int(f.centroid.y), n - 1), min(int(f.centroid.x), n - 1)]]
        else:
            dentro_c = c[np.clip(gy.ravel()[dentro].astype(int), 0, n - 1),
                         np.clip(gx.ravel()[dentro].astype(int), 0, n - 1)]
        if np.mean(dentro_c) > 0.5:
            rojas.append(f)
    geo = unary_union(rojas).simplify(1e-6 * n)  # quita vértices colineales
    geo = corregir(geo, c)
    # espinas y muescas finas que deja el remiendo donde una recta cruza la punta de un
    # gancho. Apertura en inglete: quita espinas sin tocar las esquinas que sobresalen.
    # Cierre redondo: rellena muescas en cuña (en inglete se reconstruirían). Solo se
    # aplica a trozos pequeños: las cuñas largas y finas son remiendos buenos (bordes
    # que en la imagen están algo inclinados) y deben quedarse
    k, pequeno = 0.004 * n, (0.01 * n) ** 2
    quitar = geo.difference(geo.buffer(-k, join_style=2).buffer(k, join_style=2))
    geo = geo.difference(unary_union([q for q in s.lista(quitar) if q.area < pequeno]))
    poner = geo.buffer(k, quad_segs=1).buffer(-k, quad_segs=1).difference(geo)
    geo = geo.union(unary_union([q for q in s.lista(poner) if q.area < pequeno])).buffer(0)
    if SIM_AB:
        geo = espejo_ab(geo, c)
    if SIM_LR:
        geo = espejo_lr(geo, c)
    return geo, len(caras)


def espejo_lr(geo, c):
    """Lo mismo que espejo_ab pero izquierda-derecha: se trasponen x e y, se refleja
    arriba-abajo y se deshace la trasposición."""
    from shapely.ops import transform
    trasponer = lambda g: transform(lambda x, y: (y, x), g)
    return trasponer(espejo_ab(trasponer(geo), c.T))


def espejo_ab(geo, c):
    """Rectas inclinadas y remiendos se calculan por separado en cada mitad y rompen la
    simetría arriba-abajo: se queda la mitad que mejor casa con la imagen y se refleja."""
    from shapely import affinity
    n = c.shape[0]
    arriba, abajo = box(-n, -n, 2 * n, n / 2), box(-n, n / 2, 2 * n, 2 * n)

    def acierto(mitad, filas):
        from PIL import Image, ImageDraw
        lienzo = Image.new("L", (n, n), 0)
        d = ImageDraw.Draw(lienzo)
        for p in s.lista(mitad):
            d.polygon(list(p.exterior.coords), fill=255)
            for h in p.interiors:
                d.polygon(list(h.coords), fill=0)
        v = (np.asarray(lienzo) > 127)[filas]
        ref = c[filas]
        return (v & ref).sum() / (v | ref).sum()

    sup, inf = geo.intersection(arriba), geo.intersection(abajo)
    if acierto(sup, slice(0, n // 2)) >= acierto(inf, slice(n // 2, n)):
        mitad = sup
    else:
        mitad = inf
    refl = affinity.scale(mitad, 1, -1, origin=(n / 2, n / 2))
    return unary_union([mitad.buffer(0), refl.buffer(0)]).buffer(1e-6 * n).buffer(-1e-6 * n)


def corregir(geo, c, borde=None):
    """Voto por caras: si una cara queda partida entre trazo y fondo, la mayoría
    se equivoca en el trozo menor. Se calcan las zonas donde el vector y la imagen
    discrepan (ignorando la franja de `borde` px de los contornos) y se suman o restan."""
    from PIL import Image, ImageDraw
    n = c.shape[0]
    # tiras de menos del 0,6 % del diámetro son desviación del arco, no un error:
    # remendarlas deja quiebros en bordes que deberían ser curvas
    borde = borde or max(3, int(0.003 * n))
    lienzo = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(lienzo)
    for p in s.lista(geo):
        d.polygon(list(p.exterior.coords), fill=255)
        for h in p.interiors:
            d.polygon(list(h.coords), fill=0)
    vec = np.asarray(lienzo) > 127

    def abrir(m):  # apertura morfológica: quita franjas de menos de 2·borde px
        e = m.copy()
        for _ in range(borde):
            e = e & np.roll(e, 1, 0) & np.roll(e, -1, 0) & np.roll(e, 1, 1) & np.roll(e, -1, 1)
        for _ in range(borde):
            e = e | np.roll(e, 1, 0) | np.roll(e, -1, 0) | np.roll(e, 1, 1) | np.roll(e, -1, 1)
        return e

    def calcar(m):
        cajas = []
        for y in np.nonzero(m.any(1))[0]:
            fila = np.concatenate([[0], m[y].astype(np.int8), [0]])
            dd = np.diff(fila)
            for x0, x1 in zip(np.where(dd == 1)[0], np.where(dd == -1)[0]):
                cajas.append(box(x0, y, x1, y + 1))
        if not cajas:
            return None
        partes = [q for q in s.lista(unary_union(cajas)) if q.area > (0.01 * n) ** 2]
        # suelen ser cuñas: su envolvente convexa da lados rectos; si no se parece
        # (solidez < 0.8), simplificación fuerte en vez de la escalera de píxeles
        partes = [q.convex_hull if q.area > 0.8 * q.convex_hull.area else q.simplify(0.003 * n)
                  for q in partes]
        return unary_union(partes) if partes else None

    falta, sobra = calcar(abrir(c & ~vec)), calcar(abrir(vec & ~c))
    if falta is not None:
        geo = geo.union(falta)
    if sobra is not None:
        geo = geo.difference(sobra)
    # costuras del remiendo con la geometría: grietas finas (restos de la punta de un
    # hueco) que en 3D se ven como bultos. Se cierran solo alrededor de cada remiendo
    for rem in [q for q in (falta, sobra) if q is not None]:
        zona = rem.buffer(0.02 * n)
        k = 0.0001 * n
        cerrado = geo.buffer(k).buffer(-k).intersection(zona)
        geo = geo.union(cerrado)
    return geo


def borde_limpio(geo, k=0.01):
    """Junto al borde del disco rellena muescas (< 2k) del ruido de la imagen
    y recorta con un círculo perfecto."""
    R = s.DIAMETRO / 2
    disco = Point(0, 0).buffer(R, quad_segs=SEGMENTOS // 4)
    banda = disco.difference(Point(0, 0).buffer(R - 3 * k * s.DIAMETRO, quad_segs=SEGMENTOS // 4))
    cerrado = geo.buffer(k * s.DIAMETRO).buffer(-k * s.DIAMETRO)
    geo = geo.difference(banda).union(cerrado.intersection(banda)).intersection(disco)
    # la intersección puede dejar líneas o puntos sueltos: solo interesan los polígonos
    return unary_union([g for g in getattr(geo, "geoms", [geo]) if g.geom_type in ("Polygon", "MultiPolygon")])


def sin_microaristas(geo, minimo):
    """Colapsa aristas más cortas que el bisel (quedan en cruces recta-círculo)."""
    def anillo(coords):
        a = [np.asarray(v) for v in coords[:-1]]
        cambio = True
        while cambio and len(a) > 3:
            cambio = False
            for i in range(len(a)):
                j = (i + 1) % len(a)
                if np.linalg.norm(a[j] - a[i]) < minimo:
                    a[i] = (a[i] + a[j]) / 2
                    del a[j]
                    cambio = True
                    break
        return a
    # buffer(0) repara el raro polígono que el colapso deja autointersectado
    return unary_union([Polygon(anillo(p.exterior.coords), [anillo(h.coords) for h in p.interiors]).buffer(0)
                        for p in s.lista(geo)])


def main(fuente, nombre):
    c = cuadrar(s.mascara(fuente))
    xs, ys, radios, n = lineas(c)
    if SIMETRIA:
        xs, ys = simetrico(xs, n), simetrico(ys, n)
    elif SIM_AB:
        ys = simetrico(ys, n)
    elif SIM_LR:
        xs = simetrico(xs, n)
    geo, ncaras = redibujar(c, xs, ys, radios, n)
    if DISCO:  # el recuadro del dibujo no es el círculo: se escala y centra con el disco
        from shapely import affinity
        k = s.DIAMETRO / n
        geo = affinity.affine_transform(geo, [k, 0, 0, -k, -n / 2 * k, n / 2 * k])
    else:
        geo = s.normalizar(geo)
    geo = sin_microaristas(borde_limpio(geo), 0.003 * s.DIAMETRO)
    if DISCO and abs(ACHATADO - 1) > 0.002:  # fiel a la imagen: devuelve su achatado
        from shapely import affinity
        geo = affinity.scale(geo, 1, ACHATADO, origin=(0, 0))
    # esquinas que entran casi vivas: con radio grande, en ángulos agudos rellenan un gajo
    # que no está en el original; el canto solo necesita el radio en las que sobresalen
    geo = s.redondear_planta(geo, s.BISEL * s.DIAMETRO * 1.3, s.BISEL * s.DIAMETRO * 0.6)
    info = s.exportar(geo, nombre)
    iou = s.comprobar(geo, fuente, s.RAIZ / "svg" / f"{nombre}.check.png")
    print(json.dumps({"nombre": nombre, "verticales": len(xs), "horizontales": len(ys),
                      "circulos": len(radios), "caras": ncaras, **info,
                      "iou_vs_fuente": round(float(iou), 4)}, ensure_ascii=False))


if __name__ == "__main__":
    if "--simetria-ab" in sys.argv:
        sys.argv[sys.argv.index("--simetria-ab")] = "--sin-simetria"
        SIM_AB = True
    if "--simetria-lr" in sys.argv:
        sys.argv[sys.argv.index("--simetria-lr")] = "--sin-simetria"
        SIM_LR = True
    if "--sin-simetria" in sys.argv:
        SIMETRIA = False
        MIN_RECTA = 0.012  # sin simetría que refuerce, hay que aceptar bordes más cortos
        sys.argv.remove("--sin-simetria")
    if "--ligera" in sys.argv:
        # menos segmentos en círculos, canto y esquinas; a distancia de galería no se nota
        SEGMENTOS, s.PASOS, s.ESQUINA = 144, 3, 4
        sys.argv.remove("--ligera")
        sys.argv[2] += "-ligera"
    main(sys.argv[1], sys.argv[2])
