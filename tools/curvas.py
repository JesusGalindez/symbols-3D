"""Anillos densos (polilíneas) -> nodos Bézier, y vuelta. Sondeo 4.0 de docs/PLAN-EDITOR.md.

Uso:  .venv/bin/python tools/curvas.py [--tol 0.0005] [--verificar]

Cada anillo se parte en tramos de forma codiciosa: desde un nodo, el tramo más largo
que ajusta dentro de la tolerancia con una recta, un arco (por los dos extremos) o una
cúbica (Schneider: extremos fijos, tiradores por mínimos cuadrados con
reparametrización de Newton). Los SVG ya traen las esquinas redondeadas en tramitos
de 1e-5 (casi ningún vértice gira más de 30°), así que no se parte por esquinas: se
empieza en el punto más afilado del anillo y el ajuste decide dónde cortar.

Formato de nodo (el de 4.1): {"p": [x, y], "ent": [dx, dy] | None, "sal": [dx, dy] | None}
con tiradores relativos a p; sin tirador, ese lado es recto.
"""
import argparse
import bisect
import math
import sys
import time
from pathlib import Path

import numpy as np

K_ARCO = 4 / 3  # tirador de un arco de ángulo a: radio · 4/3 · tan(a/4)


def cruz(u, v):  # producto vectorial 2D (np.cross ya no admite vectores de 2)
    return u[..., 0] * v[..., 1] - u[..., 1] * v[..., 0]


def _bezier(P, t):
    t = t[:, None]
    u = 1 - t
    return u ** 3 * P[0] + 3 * u * u * t * P[1] + 3 * u * t * t * P[2] + t ** 3 * P[3]


def _derivadas(P, t):
    t = t[:, None]
    u = 1 - t
    d1 = 3 * (u * u * (P[1] - P[0]) + 2 * u * t * (P[2] - P[1]) + t * t * (P[3] - P[2]))
    d2 = 6 * (u * (P[2] - 2 * P[1] + P[0]) + t * (P[3] - 2 * P[2] + P[1]))
    return d1, d2


def _cuerda(pts):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    return d / d[-1] if d[-1] > 0 else d


def ajustar_cubica(pts, tol):
    """Cúbica con extremos fijos; None si no baja de tol."""
    P0, P3 = pts[0], pts[-1]
    t = _cuerda(pts)
    for _ in range(6):
        u = 1 - t
        b1, b2 = 3 * u * u * t, 3 * u * t * t
        resto = pts - (u ** 3)[:, None] * P0 - (t ** 3)[:, None] * P3
        A = np.stack([b1, b2], 1)
        try:
            sol, *_ = np.linalg.lstsq(A, resto, rcond=None)
        except np.linalg.LinAlgError:
            return None
        P = np.array([P0, sol[0], sol[1], P3])
        # Newton: el parámetro de cada punto, el de su punto más cercano en la curva
        c = _bezier(P, t)
        d1, d2 = _derivadas(P, t)
        num = ((c - pts) * d1).sum(1)
        den = (d1 * d1).sum(1) + ((c - pts) * d2).sum(1)
        t = np.clip(t - np.where(np.abs(den) > 1e-12, num / den, 0), 0, 1)
        t[0], t[-1] = 0, 1
    if np.hypot(*(_bezier(P, t) - pts).T).max() > tol or np.any(np.diff(t) < 0):
        return None
    # y en los dos sentidos: entre dos puntos seguidos la curva no se aleja de su segmento
    # (con pocos puntos, una cúbica puede pasar por todos y hacer un bucle entre ellos)
    for f in (0.25, 0.5, 0.75):
        q = _bezier(P, t[:-1] + f * np.diff(t))
        a, v = pts[:-1], np.diff(pts, axis=0)
        L2 = (v * v).sum(1)
        k = np.clip(np.where(L2 > 0, ((q - a) * v).sum(1) / np.where(L2 > 0, L2, 1), 0), 0, 1)
        if np.hypot(*(q - a - k[:, None] * v).T).max() > tol:
            return None
    return P


def ajustar_arco(pts, tol):
    """Arco por los dos extremos (centro en su mediatriz, mínimos cuadrados). Devuelve
    (centro, radio, barrido con signo) o None."""
    a, b = pts[0], pts[-1]
    m, v = (a + b) / 2, b - a
    L = np.hypot(*v)
    if L < 1e-9 or len(pts) < 4:
        return None
    n = np.array([-v[1], v[0]]) / L
    # |p − (m + s n)|² = |a − (m + s n)|²  es lineal en s para cada punto
    q, qa = pts - m, a - m
    s_i_num = (q * q).sum(1) - (qa * qa).sum()
    s_i_den = 2 * (q @ n - qa @ n)
    ok = np.abs(s_i_den) > 1e-12
    if ok.sum() < 2:
        return None
    s = (s_i_den[ok] * s_i_num[ok]).sum() / (s_i_den[ok] ** 2).sum()
    c = m + s * n
    r = np.hypot(*(a - c))
    if r > 50:
        return None
    if np.abs(np.hypot(*(pts - c).T) - r).max() > tol:
        return None
    ang = np.unwrap(np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0]))
    d = np.diff(ang)
    if not (np.all(d >= -1e-9) or np.all(d <= 1e-9)):  # los puntos avanzan en un sentido
        return None
    if (r * (1 - np.cos(d / 2))).max() > tol:  # entre dos puntos, el arco no se aleja de la cuerda
        return None
    return c, r, ang[-1] - ang[0]


def arco_a_cubicas(c, r, a0, barrido):
    n = max(1, math.ceil(abs(barrido) / (math.pi / 2) - 1e-9))
    h = barrido / n
    k = K_ARCO * math.tan(h / 4) * r
    out = []
    for i in range(n):
        t0, t1 = a0 + i * h, a0 + (i + 1) * h
        p0 = c + r * np.array([math.cos(t0), math.sin(t0)])
        p1 = c + r * np.array([math.cos(t1), math.sin(t1)])
        out.append(np.array([p0, p0 + k * np.array([-math.sin(t0), math.cos(t0)]),
                             p1 - k * np.array([-math.sin(t1), math.cos(t1)]), p1]))
    return out


TOL_EXTREMO = 1e-9  # sobre la recta: un escalón de 1e-6 (el redondeo del SVG) ya inclina el borde


def ajustar_tramo(pts, tol):
    """Recta, arco o cúbica(s); None si nada ajusta. Cada tramo = lista de [P0..P3] o 'recta'."""
    a, b = pts[0], pts[-1]
    v = b - a
    L = np.hypot(*v)
    if L > 1e-12 and np.abs(cruz(v, pts - a)).max() / L <= tol:
        # y sus extremos, sobre la prolongación de su segmento más largo: si no, la recta se
        # alargaba hasta el redondeo de la esquina y un borde horizontal salía inclinado
        # ~0,05° (el imán y alinear perdían la horizontal exacta; medido en shou-cruz)
        seg = np.diff(pts, axis=0)
        k = int(np.argmax(np.hypot(*seg.T)))
        u = seg[k] / np.hypot(*seg[k])
        if max(abs(cruz(u, a - pts[k])), abs(cruz(u, b - pts[k]))) <= TOL_EXTREMO:
            return ("recta", None)
    arco = ajustar_arco(pts, tol)
    if arco:
        c, r, barrido = arco
        return ("arco", arco_a_cubicas(c, r, math.atan2(a[1] - c[1], a[0] - c[0]), barrido))
    P = ajustar_cubica(pts, tol)
    return ("cubica", [P]) if P is not None else None


def _mas_afilado(r):
    """Índice del punto que más gira en 0,01 de recorrido: ahí empieza el anillo."""
    v = np.roll(r, -1, 0) - r
    ang = np.arctan2(v[:, 1], v[:, 0])
    giro = np.abs(np.angle(np.exp(1j * (ang - np.roll(ang, 1)))))
    largo = np.hypot(*v.T)
    paso = max(1, int(round(0.01 / max(np.median(largo), 1e-9))))
    return int(np.argmax(np.convolve(np.r_[giro, giro[:paso]], np.ones(paso), "valid")[:len(r)] + 0)) + paso // 2


def ajustar_anillo(anillo, tol=0.0005, cerrado=True):
    """Polilínea cerrada -> (nodos, tipos de tramo). cerrado=False: un camino abierto (el
    lápiz, G7), que empieza y acaba en sus extremos."""
    r = np.asarray(anillo, float)
    if cerrado:
        i0 = _mas_afilado(r) % len(r)
        r = np.roll(r, -i0, 0)
        pts = np.vstack([r, r[:1]])  # cerrado: el último punto es el primero
    else:
        pts = r
    n = len(pts)
    tramos = []  # (i, j, tipo, cubicas)
    i = 0
    while i < n - 1:
        # galope y luego búsqueda binaria del tramo más largo que ajusta. Tras un fallo se
        # prueban aún dos tramos el doble de largos: con 3 o 4 puntos, una cúbica puede no
        # ajustar y sí hacerlo con más (los escalones de 1e-5 del vectorizado)
        bien, k, fallos, mal = (i + 1, ("recta", None)), 2, 0, None
        while True:
            j = min(i + k, n - 1)
            f = ajustar_tramo(pts[i:j + 1], tol)
            if f is None:
                mal = mal if mal is not None and mal > bien[0] else j
                fallos += 1
            else:
                bien, fallos, mal = (j, f), 0, None
            if j == n - 1 or fallos > 2:
                break
            k *= 2
        if mal is not None:
            lo, hi = bien[0], mal
            while hi - lo > 1:
                mid = (lo + hi) // 2
                f = ajustar_tramo(pts[i:mid + 1], tol)
                if f is None:
                    hi = mid
                else:
                    lo, bien = mid, (mid, f)
        j, (tipo, cub) = bien
        tramos.append((i, j, tipo, cub))
        i = j
    # a nodos: cada tramo recto no pone tiradores; las cúbicas, su sal y el ent del siguiente
    nodos = []
    for i, j, tipo, cub in tramos:
        if tipo == "recta":
            nodos.append({"p": pts[i].tolist(), "ent": None, "sal": None})
            continue
        for P in cub:
            nodos.append({"p": P[0].tolist(), "ent": None, "sal": (P[1] - P[0]).tolist()})
            nodos.append({"p": P[3].tolist(), "ent": (P[2] - P[3]).tolist(), "sal": None, "_fin": True})
    # fundir el final de cada cúbica con el principio del tramo siguiente (mismo punto)
    fundidos = []
    for nd in nodos:
        if fundidos and fundidos[-1].get("_fin") and np.allclose(fundidos[-1]["p"], nd["p"], atol=1e-12):
            fundidos[-1] = {"p": fundidos[-1]["p"], "ent": fundidos[-1]["ent"], "sal": nd["sal"]}
        else:
            fundidos.append(nd)
    if not cerrado:
        if not fundidos[-1].get("_fin"):  # acaba en una recta: falta su punto final
            fundidos.append({"p": pts[-1].tolist(), "ent": None, "sal": None})
    elif len(fundidos) > 1 and fundidos[-1].get("_fin"):  # el último cierra en el primero
        fundidos[0]["ent"] = fundidos[-1]["ent"]
        fundidos.pop()
    for nd in fundidos:
        nd.pop("_fin", None)
    return fundidos, [t[2] for t in tramos]


def aplanar_t(nodos, tol=0.0001, cerrado=True):
    """Nodos -> polilínea cerrada (sin repetir el primero), con cada punto como
    (x, y, k, t): sale del tramo k (del nodo k al siguiente) en el parámetro t. Cada
    cúbica se parte por la mitad (De Casteljau) hasta que sus tiradores quedan a menos de
    tol de la cuerda. En floats de Python y no numpy: aplanar() de editor.html es esta
    misma, operación por operación, y las dos dan los mismos puntos (lo comprueba
    tests/test_editor.py). cerrado=False: un camino abierto (sin el tramo del último nodo
    al primero), que acaba en el último nodo."""
    out = []
    n = len(nodos)
    for k in range(n if cerrado else n - 1):
        a, b = nodos[k], nodos[(k + 1) % n]
        (x0, y0), (x3, y3) = a["p"], b["p"]
        out.append((x0, y0, k, 0.0))
        if a["sal"] is None and b["ent"] is None:
            continue
        x1, y1 = (x0 + a["sal"][0], y0 + a["sal"][1]) if a["sal"] is not None else (x0, y0)
        x2, y2 = (x3 + b["ent"][0], y3 + b["ent"][1]) if b["ent"] is not None else (x3, y3)
        pila = [(x0, y0, x1, y1, x2, y2, x3, y3, 0.0, 1.0)]
        while pila:
            ax, ay, bx, by, cx, cy, dx, dy, t0, t1 = pila.pop()
            vx, vy = dx - ax, dy - ay
            L = math.hypot(vx, vy)
            if L > 1e-15:
                plano = max(abs(vx * (by - ay) - vy * (bx - ax)), abs(vx * (cy - ay) - vy * (cx - ax))) / L
            else:
                plano = max(math.hypot(bx - ax, by - ay), math.hypot(cx - ax, cy - ay))
            if plano <= tol:
                out.append((dx, dy, k, t1))
                continue
            abx, aby, bcx, bcy, cdx, cdy = (ax + bx) / 2, (ay + by) / 2, (bx + cx) / 2, (by + cy) / 2, (cx + dx) / 2, (cy + dy) / 2
            ex, ey, fx, fy = (abx + bcx) / 2, (aby + bcy) / 2, (bcx + cdx) / 2, (bcy + cdy) / 2
            mx, my, tm = (ex + fx) / 2, (ey + fy) / 2, (t0 + t1) / 2
            pila.append((mx, my, fx, fy, cdx, cdy, dx, dy, tm, t1))
            pila.append((ax, ay, abx, aby, ex, ey, mx, my, t0, tm))
        out.pop()  # el último trozo acaba en el nodo siguiente, que pone él mismo
    if not cerrado and nodos:
        out.append((*nodos[-1]["p"], n - 1, 0.0))
    return out


def aplanar(nodos, tol=0.0001, cerrado=True):
    """Nodos -> polilínea [[x, y], ...], cerrada salvo cerrado=False (ver aplanar_t)."""
    return [[x, y] for x, y, _, _ in aplanar_t(nodos, tol, cerrado)]


def redondear(nodos, cerrado=True):
    """Radio de esquina (G6): cada nodo con "radio" > 0 cuyos dos tramos son rectos se
    sustituye por el arco tangente a los dos (dos nodos y una cúbica de arco), como Figma:
    el radio se limita para que el arco no pase de la mitad del tramo más corto. Los
    extremos de un camino abierto y los nodos alineados no cambian. En floats de Python,
    operación por operación como redondear() de editor.html (lo comprueba una prueba)."""
    n = len(nodos)
    if not any(nd.get("radio") for nd in nodos):
        return nodos
    out = []
    for i, nd in enumerate(nodos):
        r = nd.get("radio") or 0
        if r <= 0 or nd["ent"] is not None or nd["sal"] is not None or (not cerrado and i in (0, n - 1)):
            out.append(nd)
            continue
        a, c = nodos[(i - 1) % n], nodos[(i + 1) % n]
        if a["sal"] is not None or c["ent"] is not None:
            out.append(nd)  # un tramo curvo: la esquina se queda viva
            continue
        bx, by = nd["p"]
        ux, uy = a["p"][0] - bx, a["p"][1] - by
        vx, vy = c["p"][0] - bx, c["p"][1] - by
        la, lc = math.sqrt(ux * ux + uy * uy), math.sqrt(vx * vx + vy * vy)  # no hypot: la misma cuenta que en JS
        if la == 0 or lc == 0:
            out.append(nd)
            continue
        ux, uy, vx, vy = ux / la, uy / la, vx / lc, vy / lc
        ang = math.acos(max(-1.0, min(1.0, ux * vx + uy * vy)))  # el ángulo de la esquina
        if ang < 1e-9 or math.pi - ang < 1e-9:
            out.append(nd)
            continue
        d = min(r / math.tan(ang / 2), la / 2, lc / 2)  # de la esquina al punto de tangencia
        re = d * math.tan(ang / 2)
        k = 4 / 3 * math.tan((math.pi - ang) / 4) * re  # tirador del arco de barrido π − ang
        out.append({"p": [bx + ux * d, by + uy * d], "ent": None, "sal": [-ux * k, -uy * k], "tipo": "vivo"})
        out.append({"p": [bx + vx * d, by + vy * d], "ent": [-vx * k, -vy * k], "sal": None, "tipo": "vivo"})
    return out


def partir_camino(nodos, cortes, cerrado):
    """Un camino de nodos partido en los puntos cortes = [(k, t), ...] (tramo k, parámetro
    t): los trozos, abiertos, con las curvas partidas por De Casteljau. Cerrado y con un
    solo corte sale un camino abierto que empieza y acaba en él."""
    n = len(nodos)
    tramos = n if cerrado else n - 1
    cortes = sorted({(k, t) for k, t in cortes if 0 <= k < tramos and 0 <= t <= 1})
    if not cortes:
        return [nodos]
    pos = lambda k, t: k + t  # noqa: E731  (posición a lo largo del camino)

    def punto(k, t):
        P = controles(nodos, k)
        return en_bezier(P, t) if P else [nodos[k]["p"][j] + t * (nodos[(k + 1) % n]["p"][j] - nodos[k]["p"][j]) for j in (0, 1)]

    def trozo(a, b):  # nodos de la posición a a la b (a < b), recorriendo tramos
        out, k = [], int(a[0])
        while True:
            t0 = a[1] if k == a[0] else 0.0
            t1 = b[1] if k == b[0] else 1.0
            P = controles(nodos, k % n)
            p0 = punto(k % n, t0)
            if not out:
                out.append({"p": p0, "ent": None, "sal": None})
            if P:
                Q = sub_bezier(P, t0, t1)
                out[-1]["sal"] = [Q[1][0] - Q[0][0], Q[1][1] - Q[0][1]]
                out.append({"p": Q[3], "ent": [Q[2][0] - Q[3][0], Q[2][1] - Q[3][1]], "sal": None})
            else:
                out.append({"p": punto(k % n, t1), "ent": None, "sal": None})
            if k >= b[0]:
                break
            k += 1
        # sin nodos repetidos (un corte justo en un nodo)
        limpio = [out[0]]
        for q in out[1:]:
            if math.dist(q["p"], limpio[-1]["p"]) < 1e-12:
                limpio[-1]["sal"] = q["sal"]
            else:
                limpio.append(q)
        return limpio

    if cerrado:
        # los trozos van de un corte al siguiente, y el último da la vuelta hasta el primero
        cs = cortes + [(cortes[0][0] + n, cortes[0][1])]
        return [x for x in (trozo(cs[i], cs[i + 1]) for i in range(len(cortes))) if len(x) >= 2]
    cs = [(0, 0.0)] + cortes + [(n - 2, 1.0)]
    return [x for x in (trozo(cs[i], cs[i + 1]) for i in range(len(cs) - 1)) if len(x) >= 2]


def controles(nodos, k):
    """Los cuatro puntos de control del tramo k, o None si es recto."""
    a, b = nodos[k], nodos[(k + 1) % len(nodos)]
    if a["sal"] is None and b["ent"] is None:
        return None
    p0, p3 = a["p"], b["p"]
    p1 = [p0[0] + a["sal"][0], p0[1] + a["sal"][1]] if a["sal"] is not None else p0
    p2 = [p3[0] + b["ent"][0], p3[1] + b["ent"][1]] if b["ent"] is not None else p3
    return [p0, p1, p2, p3]


def en_bezier(P, t):
    u = 1 - t
    return [u * u * u * P[0][j] + 3 * u * u * t * P[1][j] + 3 * u * t * t * P[2][j] + t * t * t * P[3][j] for j in (0, 1)]


def sub_bezier(P, t0, t1):
    """El trozo [t0, t1] de la cúbica P, en el sentido de t0 a t1 (De Casteljau)."""
    if t0 > t1:
        return sub_bezier(P, t1, t0)[::-1]
    lerp = lambda u, v, t: [u[0] + t * (v[0] - u[0]), u[1] + t * (v[1] - u[1])]  # noqa: E731

    def partir(Q, t):  # -> (izquierda, derecha)
        a, b, c = lerp(Q[0], Q[1], t), lerp(Q[1], Q[2], t), lerp(Q[2], Q[3], t)
        d, e = lerp(a, b, t), lerp(b, c, t)
        f = lerp(d, e, t)
        return [Q[0], a, d, f], [f, e, c, Q[3]]
    izq = partir(P, t1)[0] if t1 < 1 else P
    return partir(izq, t0 / t1)[1] if t0 > 0 else izq


def indice(anillos):
    """De los anillos de nodos de una capa (en el mundo): cada punto aplanado -> (anillo,
    tramo, t), y las cuerdas de los tramos curvos, para situar los puntos nuevos de un corte."""
    puntos, cuerdas, ts = {}, [], {}
    for r, nodos in enumerate(anillos):
        pts = aplanar_t(nodos)
        for i, (x, y, k, t) in enumerate(pts):
            puntos.setdefault((x, y), (r, k, t))
            ts.setdefault((r, k), []).append(t)
            x2, y2, k2, t2 = pts[(i + 1) % len(pts)]
            if controles(nodos, k) is not None:
                cuerdas.append((x, y, x2, y2, r, k, t, t2 if k2 == k else 1.0))
    return {"anillos": anillos, "puntos": puntos, "cuerdas": cuerdas, "ts": {rk: sorted(v) for rk, v in ts.items()}}


def recurvar(anillo, ind):
    """Un anillo de una pieza cortada (polígono cerrado sobre la forma aplanada) -> nodos
    con las curvas de la capa original. Cada vértice que sale del aplanado sabe su tramo
    y su t; uno nuevo (donde la cuchilla cruza una cuerda) se lleva a la curva, al mismo
    sitio en las dos piezas que lo comparten. Los trozos seguidos de un mismo tramo se
    rehacen con De Casteljau; lo demás, rectas. Sin tramos curvos da nodos vivos."""
    pts = [list(q) for q in anillo[:-1]]
    info = []
    for q in pts:
        i = ind["puntos"].get((q[0], q[1]))
        if i is None:
            for x, y, x2, y2, r, k, ta, tb in ind["cuerdas"]:
                vx, vy = x2 - x, y2 - y
                L2 = vx * vx + vy * vy
                if L2 == 0:
                    continue
                lam = ((q[0] - x) * vx + (q[1] - y) * vy) / L2
                if -1e-9 <= lam <= 1 + 1e-9 and abs((q[0] - x) * vy - (q[1] - y) * vx) / math.sqrt(L2) < 1e-10:
                    i = (r, k, ta + lam * (tb - ta))
                    q[:] = en_bezier(controles(ind["anillos"][r], k), i[2])
                    break
        info.append(i)
    n = len(pts)

    def en_tramos(i):  # un nodo de la capa es el final (t = 1) del tramo anterior
        if i is None:
            return {}
        r, k, t = i
        m = {(r, k): t}
        if t == 0:
            m[(r, (k - 1) % len(ind["anillos"][r]))] = 1.0
        return m

    def entre(lista, t0, t1):  # ¿algún t del aplanado estrictamente entre t0 y t1?
        lo, hi = min(t0, t1), max(t0, t1)
        return bisect.bisect_right(lista, lo) < bisect.bisect_left(lista, hi)

    lados = []  # por arista i -> i+1: None (recta) o (r, k, ti, tj)
    for i in range(n):
        a, b = en_tramos(info[i]), en_tramos(info[(i + 1) % n])
        # sobre la curva solo si son vecinos en el aplanado: si la cuchilla cruza dos veces
        # un mismo tramo, la arista entre los dos cruces es el corte, no la curva
        comun = next(((rk, a[rk], b[rk]) for rk in a if rk in b and a[rk] != b[rk]
                      and controles(ind["anillos"][rk[0]], rk[1]) is not None
                      and not entre(ind["ts"][rk], a[rk], b[rk])), None)
        lados.append(None if comun is None else (comun[0], comun[1], comun[2]))

    def sigue(e, f):  # dos aristas seguidas del mismo tramo, en el mismo sentido
        return (e is not None and f is not None and e[0] == f[0] and e[2] == f[1]
                and (e[2] - e[1]) * (f[2] - f[1]) > 0)
    inicio = next((i for i in range(n) if not sigue(lados[i - 1], lados[i])), 0)
    nodos, pendiente, i = [], None, 0  # pendiente: el tirador de entrada del nodo siguiente
    while i < n:
        a = (inicio + i) % n
        j = i + 1
        while j < n and sigue(lados[(inicio + j - 1) % n], lados[(inicio + j) % n]):
            j += 1
        b = (inicio + j) % n
        nodo = {"p": pts[a], "ent": pendiente, "sal": None}
        pendiente = None
        if lados[a] is not None:
            (r, k), t0, t1 = lados[a][0], lados[a][1], lados[(inicio + j - 1) % n][2]
            P = sub_bezier(controles(ind["anillos"][r], k), t0, t1)
            nodo["sal"] = [P[1][0] - pts[a][0], P[1][1] - pts[a][1]]
            pendiente = [P[2][0] - pts[b][0], P[2][1] - pts[b][1]]
        nodos.append(nodo)
        i = j
    if pendiente is not None:  # la última arista acaba en el primero
        nodos[0]["ent"] = pendiente
    return nodos


def error_max(original, aplanado):
    """Distancia de Hausdorff entre la polilínea original y la aplanada."""
    import shapely
    from shapely.geometry import LinearRing
    return shapely.hausdorff_distance(LinearRing(original), LinearRing(aplanado), densify=0.05)


def main():
    sys.path.insert(0, str(Path(__file__).parent))
    import editor
    import simbolo as s
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=0.0005)
    ap.add_argument("--verificar", action="store_true", help="generar aplanado a un temporal y pasar verificar.py")
    a = ap.parse_args()
    import json
    import subprocess
    import tempfile
    print(f"tolerancia {a.tol} · nodos antes → después · error máx. · tramos recta/arco/cúbica · tiempo")
    for nombre in ["amor", "fu-circular", "fu-hiragino", "fu-trazo", "shou-circular", "shou-cruz", "shou-sello", "xi-doble"]:
        doc = editor.piezas_svg(nombre)
        t0 = time.perf_counter()
        antes = despues = 0
        err = 0.0
        tipos = {"recta": 0, "arco": 0, "cubica": 0}
        capas = []
        for c in doc["capas"]:
            nuevos = []
            for anillo in c["anillos"]:
                nodos, ts = ajustar_anillo(anillo, a.tol)
                antes += len(anillo)
                despues += len(nodos)
                for t in ts:
                    tipos[t] += 1
                plano = aplanar(nodos)
                err = max(err, error_max(anillo, plano))
                nuevos.append(plano)
            capas.append({"op": c["op"], "anillos": [[[x + c["t"]["x"], y + c["t"]["y"]] for x, y in r] for r in nuevos]})
        dt = time.perf_counter() - t0
        linea = (f"{nombre:14} {antes:5} → {despues:4} ({despues / antes:5.1%})  error {err:.5f}  "
                 f"{tipos['recta']:3}/{tipos['arco']:3}/{tipos['cubica']:3}  {dt:5.2f} s")
        if a.verificar:
            fuente = Path(s.RAIZ) / "fuentes" / f"{nombre}.png"
            if fuente.exists():
                with tempfile.TemporaryDirectory() as tmp:
                    editor.SALIDA = Path(tmp)
                    editor.generar(f"{nombre}-curvas", doc, capas)
                    r = subprocess.run([sys.executable, str(Path(__file__).parent / "verificar.py"),
                                        str(Path(tmp) / "glb" / f"{nombre}-curvas.glb"), str(fuente)],
                                       capture_output=True, text=True)
                    v = json.loads(r.stdout.strip().splitlines()[-1])
                    linea += f"  {'APROBADO' if v['aprobado'] else 'RECHAZADO'}"
        print(linea, flush=True)


if __name__ == "__main__":
    main()
