"""Imagen de un símbolo plano -> SVG vectorial -> GLB extruido con bisel.

Uso:  .venv/bin/python tools/simbolo.py fuentes/shou-circular.png shou-circular
"""
import json
import sys
from pathlib import Path

import numpy as np
import shapely
import trimesh
from PIL import Image, ImageDraw, ImageFilter
from shapely.geometry import MultiPolygon, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

RAIZ = Path(__file__).resolve().parent.parent
ESCALA = 4          # sobremuestreo antes de trazar: bordes más limpios
DIAMETRO = 1.0      # unidades del GLB (1 = 1 m); la galería escala a gusto
FONDO = 0.07        # profundidad de la extrusión, relativa al diámetro
BISEL = 0.008       # radio del canto redondeado (y de las esquinas en planta)
PASOS = 8           # segmentos del cuarto de círculo
ESQUINA = 12        # segmentos por cuarto de vuelta en las esquinas en planta
COLOR = [0.58, 0.022, 0.012, 1.0]  # laca roja (glTF va en lineal: sRGB ≈ #c8281e)


def mascara(ruta):
    img = np.asarray(Image.open(ruta).convert("RGB")).astype(float)
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    rojez = np.clip((r - (g + b) / 2) / 120, 0, 1)  # 1 = rojo pleno, 0 = crema
    if (rojez > 0.5).mean() < 0.01:  # casi nada rojo: símbolo en tinta negra
        rojez = np.clip((190 - img.mean(-1)) / 120, 0, 1)
    grande = Image.fromarray((rojez * 255).astype(np.uint8)).resize(
        (img.shape[1] * ESCALA, img.shape[0] * ESCALA), Image.BICUBIC)
    if max(img.shape[:2]) < 300:
        # imagen pequeña: el ruido de compresión llega entero a la máscara y el trazo
        # sale con bordes irregulares; un desenfoque suave antes del umbral lo alisa
        grande = grande.filter(ImageFilter.GaussianBlur(ESCALA * 0.8))
    return np.asarray(grande) > 127


def poligonos(m):
    """Une las corridas horizontales de píxeles en polígonos y quita la escalera."""
    cajas = []
    for y in range(m.shape[0]):
        fila = np.concatenate([[0], m[y].astype(np.int8), [0]])
        d = np.diff(fila)
        for x0, x1 in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            cajas.append(box(x0, y, x1, y + 1))
    geo = unary_union(cajas).simplify(ESCALA * 0.6)
    partes = list(geo.geoms) if isinstance(geo, MultiPolygon) else [geo]
    area_max = max(p.area for p in partes)
    partes = [p for p in partes if p.area > area_max * 0.002]  # motas sueltas
    return unary_union(partes)


def normalizar(geo):
    minx, miny, maxx, maxy = geo.bounds
    cx, cy, s = (minx + maxx) / 2, (miny + maxy) / 2, DIAMETRO / max(maxx - minx, maxy - miny)
    from shapely import affinity
    # y de imagen hacia abajo -> y 3D hacia arriba
    return affinity.affine_transform(geo, [s, 0, 0, -s, -cx * s, cy * s])


def lista(geo):
    return list(geo.geoms) if isinstance(geo, MultiPolygon) else [geo]


def svg(geo, ruta):
    r = DIAMETRO / 2
    trazos = []
    for p in lista(geo):
        for anillo in [p.exterior, *p.interiors]:
            pts = " L".join(f"{x:.5f},{-y:.5f}" for x, y in anillo.coords[:-1])
            trazos.append(f"M{pts}Z")
    ruta.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-r} {-r} {2*r} {2*r}">'
        f'<path fill="#c8321e" fill-rule="evenodd" d="{" ".join(trazos)}"/></svg>\n')


def inset(anillo, d):
    """Desplaza cada vértice hacia el material por inglete; conserva la correspondencia."""
    a = np.asarray(anillo.coords[:-1])
    e_prev = a - np.roll(a, 1, axis=0)
    e_next = np.roll(a, -1, axis=0) - a
    izq = lambda e: np.stack([-e[:, 1], e[:, 0]], 1) / np.linalg.norm(e, axis=1)[:, None]
    n1, n2 = izq(e_prev), izq(e_next)
    m = n1 + n2
    m /= np.linalg.norm(m, axis=1)[:, None]
    largo = np.minimum(d / np.clip((m * n1).sum(1), 0.3, None), 3 * d)
    b = a + m * largo[:, None]
    # aristas que al hundirse se dan la vuelta (valles más cortos que d): se funden en un punto
    for _ in range(len(a)):
        e_a = np.roll(a, -1, axis=0) - a
        e_b = np.roll(b, -1, axis=0) - b
        vueltas = np.where((e_a * e_b).sum(1) < 0)[0]
        if not len(vueltas):
            break
        for i in vueltas:
            j = (i + 1) % len(a)
            b[i] = b[j] = (b[i] + b[j]) / 2
    return a, b


def sin_duplicados(p, minimo):
    """Quita vértices pegados al anterior: una arista casi nula tiene normal basura
    y el inglete del inset sale disparado (simplify no los quita)."""
    def anillo(r):
        a = np.asarray(r.coords[:-1])
        keep = [0]
        for i in range(1, len(a)):
            if np.linalg.norm(a[i] - a[keep[-1]]) >= minimo:
                keep.append(i)
        if np.linalg.norm(a[keep[-1]] - a[keep[0]]) < minimo:
            keep.pop()
        a = a[keep]
        # muescas y picos en V: giro > 60° entre aristas cortas (restos del voto por caras)
        cambio = True
        while cambio and len(a) > 4:
            cambio = False
            e1 = a - np.roll(a, 1, axis=0)
            e2 = np.roll(a, -1, axis=0) - a
            l1, l2 = np.linalg.norm(e1, axis=1), np.linalg.norm(e2, axis=1)
            cos = (e1 * e2).sum(1) / (l1 * l2)
            malos = np.where((cos < np.cos(np.radians(60))) & (np.minimum(l1, l2) < 3 * minimo))[0]
            if len(malos):
                a = np.delete(a, malos[0], axis=0)
                cambio = True
        return a
    return Polygon(anillo(p.exterior), [anillo(h) for h in p.interiors])


def pieza(p, fondo, bisel, pasos=None):
    """Prueba el canto completo y, si no cabe en alguna esquina, uno menor."""
    for f in (1, 0.75, 0.5):
        m, ok = pieza_con(p, fondo, bisel * f, pasos)
        if ok:
            return m, True
    return m, False


def pieza_con(p, fondo, bisel, pasos=None):
    """Extrusión con canto redondeado (cuarto de círculo) delante y detrás.
    orient: el exterior va antihorario, los agujeros horario, así la izquierda
    de cada arista apunta siempre hacia el material."""
    p = orient(sin_duplicados(p.simplify(1e-6 * DIAMETRO), 8e-4 * DIAMETRO))
    anillos = [p.exterior, *p.interiors]
    # perfil de atrás hacia delante: (hundimiento, z)
    th = np.linspace(0, np.pi / 2, (pasos or PASOS) + 1)
    hunde = lambda t: round(bisel * (1 - np.cos(t)), 12)
    atras = [(hunde(t), bisel * (1 - np.sin(t))) for t in th[::-1]]
    delante = [(hunde(t), fondo - bisel + bisel * np.sin(t)) for t in th]
    perfil = atras + delante
    niveles = {d: [inset(r, d)[1] if d else np.asarray(r.coords[:-1]) for r in anillos]
               for d, _ in perfil}
    q = Polygon(niveles[hunde(np.pi / 2)][0], niveles[hunde(np.pi / 2)][1:])
    if not q.is_valid:
        return trimesh.creation.extrude_polygon(p, fondo), False

    v, f = [], []

    def tapa(poly, z, arriba):
        # Delaunay con restricciones: earcut deja huecos al unir agujeros con puntos colineales
        for t in shapely.constrained_delaunay_triangles(poly).geoms:
            t = orient(t, 1 if arriba else -1)
            base = len(v)
            v.extend([[x, y, z] for x, y in t.exterior.coords[:3]])
            f.append([base, base + 1, base + 2])

    def banda(a, za, b, zb):
        n, base = len(a), len(v)
        v.extend([[x, y, za] for x, y in a])
        v.extend([[x, y, zb] for x, y in b])
        for i in range(n):
            j = (i + 1) % n
            f.append([base + i, base + j, base + n + j])
            f.append([base + i, base + n + j, base + n + i])

    for k in range(len(anillos)):
        for (d0, z0), (d1, z1) in zip(perfil, perfil[1:]):
            banda(niveles[d0][k], z0, niveles[d1][k], z1)
    tapa(q, 0, False)
    tapa(q, fondo, True)
    m = trimesh.Trimesh(np.array(v), np.array(f), process=False)
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())  # los que dejan los puntos fundidos del inset
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(m)
    return m, True


def redondear_planta(geo, r, r_entrante=None, esquina=None):
    """Redondea en planta esquinas convexas y cóncavas con radio r: aspecto tallado,
    y el canto redondeado (mismo radio) cabe sin cruzarse en esquinas agudas."""
    q = esquina or ESQUINA
    re_ = r if r_entrante is None else r_entrante
    return geo.buffer(-r, quad_segs=q).buffer(r, quad_segs=q).buffer(re_, quad_segs=q).buffer(-re_, quad_segs=q)


def suavizar(m):
    """Normales suaves en curvas y canto redondeado; aristas vivas en las esquinas."""
    # facet_minarea=None: sin eso trimesh sombrea plano las caras grandes (pared, frente)
    # y deja una costura de luz donde se juntan con el canto redondeado
    material = getattr(m.visual, "material", None)
    m = trimesh.graph.smooth_shade(m, angle=np.radians(40), facet_minarea=None)
    if material is not None:  # smooth_shade devuelve la malla sin material
        m.visual = trimesh.visual.TextureVisuals(material=material)
    # frente y dorso planos: normal exacta. Promediada con el canto sale inclinada ~5°
    # y los triángulos largos de la tapa la estiran en rayas de luz
    nv = m.vertex_normals.copy()
    z = m.vertices[:, 2]
    nv[np.isclose(z, z.max())] = [0, 0, 1]
    nv[np.isclose(z, z.min())] = [0, 0, -1]
    m.vertex_normals = nv
    return m


def exportar(geo, nombre, fondo=None, bisel=None, color=None, pasos=None, carpeta=None):
    """Geometría 2D normalizada -> svg/<nombre>.svg y glb/<nombre>.glb con canto
    redondeado, laca roja y normales finales. Común a símbolos y letras.
    Sin argumentos usa los globales del módulo, leídos al llamar (redibujar.py y
    letras.py cambian PASOS para la versión ligera); carpeta: otra raíz de salida."""
    carpeta = Path(carpeta or RAIZ)
    svg(geo, carpeta / "svg" / f"{nombre}.svg")
    mallas, biseladas = [], 0
    for p in lista(geo):
        m, ok = pieza(p, (fondo or FONDO) * DIAMETRO, (bisel or BISEL) * DIAMETRO, pasos)
        mallas.append(m)
        biseladas += ok
    estanca = all(m.is_watertight for m in mallas)
    malla = trimesh.util.concatenate(mallas)
    malla.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
        name="laca", baseColorFactor=color or COLOR, metallicFactor=0.0, roughnessFactor=0.35))
    malla = suavizar(malla)  # después del material: asignarlo borra las normales calculadas
    malla.export(carpeta / "glb" / f"{nombre}.glb")
    return {"piezas": len(mallas), "biseladas": biseladas,
            "triangulos": len(malla.faces), "estanca": bool(estanca)}


def comprobar(geo, fuente, ruta):
    """IoU entre el vector y la máscara original: cuánto se parece el trazo."""
    m = mascara(fuente)
    ys, xs = np.where(m)
    h = w = 600
    lienzo = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(lienzo)
    for p in lista(geo):
        f = lambda c: [((x / DIAMETRO + .5) * w, (.5 - y / DIAMETRO) * h) for x, y in c]
        d.polygon(f(p.exterior.coords), fill=255)
        for i in p.interiors:
            d.polygon(f(i.coords), fill=0)
    recorte = Image.fromarray((m[ys.min():ys.max() + 1, xs.min():xs.max() + 1] * 255).astype(np.uint8))
    lado = max(recorte.size)
    cuadro = Image.new("L", (lado, lado), 0)
    cuadro.paste(recorte, ((lado - recorte.width) // 2, (lado - recorte.height) // 2))
    ref = np.asarray(cuadro.resize((w, h))) > 127
    vec = np.asarray(lienzo) > 127
    Image.fromarray(np.stack([ref * 255, vec * 255, vec * 0], -1).astype(np.uint8)).save(ruta)
    return (ref & vec).sum() / (ref | vec).sum()


def main(fuente, nombre):
    geo = redondear_planta(normalizar(poligonos(mascara(fuente))), BISEL * DIAMETRO * 1.05)
    info = exportar(geo, nombre)
    iou = comprobar(geo, fuente, RAIZ / "svg" / f"{nombre}.check.png")
    print(json.dumps({"nombre": nombre, **info, "iou_vs_fuente": round(float(iou), 4)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
