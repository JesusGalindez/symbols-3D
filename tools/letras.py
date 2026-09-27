"""Texto con una fuente tipográfica -> GLB con el mismo acabado que los símbolos.

Uso:
  .venv/bin/python tools/letras.py "AMOR" amor --fuente "/System/Library/Fonts/Avenir Next.ttc" --indice 2
  .venv/bin/python tools/letras.py "福" fu-fuente --fuente "/System/Library/Fonts/Hiragino Sans GB.ttc"
  añade --separadas para un GLB por letra (glb/<nombre>-<i>.glb), --ligera para la versión de galería

La fuente ya trae el contorno vectorial exacto: no hay nada que adivinar. Se aplanan
las curvas, se compone el texto con los avances de la fuente, se aplica el mismo
redondeo de esquinas que a los símbolos y se exporta con simbolo.exportar().
Escribe además fuentes/<nombre>.png (la silueta de la fuente) para tools/verificar.py.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
import simbolo as s  # noqa: E402

PASOS_CURVA = 16  # tramos por curva de Bézier antes de simplificar


def tramo(p0, ctrl, fin):
    t = np.linspace(0, 1, PASOS_CURVA + 1)[1:]
    pts = np.array([p0, *ctrl, fin], float)
    out = []
    for tt in t:  # De Casteljau escalar: claro y sin trucos de forma
        q = pts.copy()
        while len(q) > 1:
            q = q[:-1] * (1 - tt) + q[1:] * tt
        out.append(q[0])
    return out


def anillos(glifo, fuente):
    pen = DecomposingRecordingPen(fuente.getGlyphSet())
    fuente.getGlyphSet()[glifo].draw(pen)
    anillos_, actual = [], []
    for op, args in pen.value:
        if op == "moveTo":
            actual = [np.array(args[0], float)]
        elif op == "lineTo":
            actual.append(np.array(args[0], float))
        elif op == "qCurveTo":  # TrueType: varios controles con puntos implícitos entre ellos
            ctrls = [np.array(a, float) for a in args[:-1]]
            fin = np.array(args[-1], float) if args[-1] is not None else actual[0]
            for i, cp in enumerate(ctrls):
                sig = fin if i == len(ctrls) - 1 else (cp + ctrls[i + 1]) / 2
                actual += tramo(actual[-1], [cp], sig)
        elif op == "curveTo":  # CFF: cúbica
            actual += tramo(actual[-1], [np.array(a, float) for a in args[:-1]], np.array(args[-1], float))
        elif op in ("closePath", "endPath"):
            if len(actual) >= 3:
                anillos_.append(np.array(actual))
            actual = []
    return anillos_


def geometria_glifo(glifo, fuente, dx):
    """Relleno de regla no nula aproximado: los anillos con la orientación mayoritaria
    (por área) son contornos, los contrarios son huecos."""
    polis = [(Polygon(a + [dx, 0]).buffer(0), a) for a in anillos(glifo, fuente)]
    if not polis:
        return None
    firmado = [0.5 * np.sum(a[:, 0] * np.roll(a[:, 1], -1) - np.roll(a[:, 0], -1) * a[:, 1]) for _, a in polis]
    signo = np.sign(sum(firmado))
    llenos = unary_union([p for (p, _), f in zip(polis, firmado) if np.sign(f) == signo])
    huecos = unary_union([p for (p, _), f in zip(polis, firmado) if np.sign(f) != signo])
    return llenos.difference(huecos)


def componer(texto, fuente, espacio):
    cmap, hmtx = fuente.getBestCmap(), fuente["hmtx"]
    em = fuente["head"].unitsPerEm
    x, piezas = 0.0, []
    for ch in texto:
        glifo = cmap.get(ord(ch))
        if glifo is None:
            raise SystemExit(f"la fuente no tiene «{ch}»")
        g = geometria_glifo(glifo, fuente, x)
        if g is not None and not g.is_empty:
            piezas.append(g)
        x += hmtx[glifo][0] + espacio * em
    from shapely import affinity
    piezas = [affinity.scale(p, 1 / em, 1 / em, origin=(0, 0)) for p in piezas]  # 1 = un em
    # centrado en el origen como los símbolos: la fuente pone el texto sobre la línea base
    # y desde el borde izquierdo, y el visor (y cualquier escena) gira alrededor del origen
    x0, y0, x1, y1 = unary_union(piezas).bounds
    return [affinity.translate(p, -(x0 + x1) / 2, -(y0 + y1) / 2) for p in piezas]


def silueta_png(geo, ruta, lado=1600):
    """Silueta de referencia (negro sobre blanco) para verificar.py."""
    lo = np.array(geo.bounds[:2]); hi = np.array(geo.bounds[2:])
    ctr, esc = (lo + hi) / 2, (lado * 0.9) / (hi - lo).max()
    im = Image.new("RGB", (lado, lado), "white")
    d = ImageDraw.Draw(im)
    f = lambda cs: [((x - ctr[0]) * esc + lado / 2, lado / 2 - (y - ctr[1]) * esc) for x, y in cs]
    for p in s.lista(geo):
        d.polygon(f(p.exterior.coords), fill="black")
        for h in p.interiors:
            d.polygon(f(h.coords), fill="white")
    im.save(ruta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("texto")
    ap.add_argument("nombre")
    ap.add_argument("--fuente", default="/System/Library/Fonts/Avenir Next.ttc")
    ap.add_argument("--indice", type=int, default=0, help="estilo dentro de un .ttc")
    ap.add_argument("--espacio", type=float, default=0.02, help="espacio extra entre letras, en em")
    ap.add_argument("--separadas", action="store_true")
    ap.add_argument("--ligera", action="store_true")
    a = ap.parse_args()
    if a.ligera:
        s.PASOS, s.ESQUINA = 3, 4
        a.nombre += "-ligera"
    fuente = TTFont(a.fuente, fontNumber=a.indice)
    letras = componer(a.texto, fuente, a.espacio)
    r = s.BISEL * s.DIAMETRO  # mismo acabado que redibujar.py
    acabar = lambda g: s.redondear_planta(g, r * 1.3, r * 0.6)
    salidas = [(a.nombre, unary_union(letras))]
    if a.separadas:
        salidas += [(f"{a.nombre}-{i}", g) for i, g in enumerate(letras, 1)]
    for nombre, original in salidas:
        # referencia: el contorno exacto de la fuente, sin el redondeo del acabado
        silueta_png(original, s.RAIZ / "fuentes" / f"{nombre}.png")
        g = acabar(original)
        perdido = s.area_perdida(original, g)
        if perdido > s.PERDIDA_MAX:
            print(f"aviso {nombre}: el redondeo se comió el {perdido:.0%} de una pieza; trazos "
                  "demasiado finos para el canto, prueba un estilo más grueso", file=sys.stderr)
        info = s.exportar(g, nombre)
        print(json.dumps({"nombre": nombre, **info}, ensure_ascii=False))

if __name__ == "__main__":
    main()
