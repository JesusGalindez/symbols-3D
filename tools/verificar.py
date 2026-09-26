"""Verificador estricto: ¿el GLB se parece a la imagen y está bien construido?

Uso:  .venv/bin/python tools/verificar.py glb/X.glb fuentes/X.png [--informe salida.png]

Compara la silueta del modelo (proyección frontal) con la máscara de la imagen y
revisa la malla. Cada criterio sale PASA/FALLA con su valor y su umbral; si falla
alguno, termina con código 1. El informe marca en la imagen las zonas que no
coinciden, numeradas de peor a mejor (rojo = solo en la imagen, verde = solo en el modelo).

Las distancias van en % del diámetro del símbolo.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
import simbolo as s  # noqa: E402

N = 1200  # resolución de comparación

# Umbrales. El parecido se mide contra la imagen tal cual; contorno y zonas, contra la
# imagen con el mismo redondeo de esquinas que el modelo, así que ahí no hay holgura
# para el acabado: lo que quede es error de trazo.
UMBRALES = {
    "iou_min": 0.97,          # parecido global con la imagen original
    "contorno_p95_max": 0.3,  # el 95 % del contorno a menos de esto
    "contorno_max_max": 0.8,  # ningún punto del contorno más lejos que esto
    "zona_max_max": 0.02,     # mayor zona de discrepancia, en % del área del disco
}


def silueta_modelo(glb, k=1.0):
    escena = trimesh.load(glb, process=False)
    geos = list(escena.geometry.values())
    # una sola geometría: concatenate recalcula normales y taparía las del archivo
    m = geos[0] if len(geos) == 1 else trimesh.util.concatenate(geos)
    # encuadre igual que la imagen: centrado y con el lado mayor ocupando N
    # (un símbolo es un disco, pero un texto es más ancho que alto)
    lo, hi = m.vertices[:, :2].min(0), m.vertices[:, :2].max(0)
    ctr, lado = (lo + hi) / 2, (hi - lo).max() * k
    lienzo = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(lienzo)
    for t in m.vertices[m.faces][:, :, :2]:
        d.polygon([((x - ctr[0]) / lado * N + N / 2, N / 2 - (y - ctr[1]) / lado * N) for x, y in t],
                  fill=255)
    global ESCALA_MODELO
    ESCALA_MODELO = lado / k  # el canto se mide en unidades del modelo
    return np.asarray(lienzo) > 127, m


def silueta_imagen(fuente):
    m = s.mascara(fuente)
    ys, xs = np.nonzero(m)
    c = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    global PX
    PX = 100 * s.ESCALA / max(c.shape)  # un píxel del original, en % del diámetro
    lado = max(c.shape)  # igual que normalizar(): encaja el lado mayor
    cuadro = np.zeros((lado, lado), bool)
    cuadro[(lado - c.shape[0]) // 2:(lado - c.shape[0]) // 2 + c.shape[0],
           (lado - c.shape[1]) // 2:(lado - c.shape[1]) // 2 + c.shape[1]] = c
    return np.asarray(Image.fromarray(cuadro.astype(np.uint8) * 255).resize((N, N))) > 127


def alinear(glb, ref):
    """Registro antes de medir: el encuadre por rectángulo envolvente se descuadra si el
    redondeo recorta una punta extrema. Se prueban escalas cercanas y, para cada una, la
    traslación de máxima correlación. Solo corrige el encuadre global: un error local
    sigue ahí."""
    from scipy.signal import fftconvolve
    mejor = None
    for k in (0.99, 0.995, 1.0, 1.005, 1.01):
        vec, m = silueta_modelo(glb, k)
        corr = fftconvolve(ref.astype(np.float32), vec[::-1, ::-1].astype(np.float32), mode="same")
        dy, dx = np.unravel_index(corr.argmax(), corr.shape)
        dy, dx = dy - N // 2, dx - N // 2
        if abs(dx) > 30 or abs(dy) > 30:
            dx = dy = 0
        v = np.roll(vec, (dy, dx), (0, 1))
        iou = (ref & v).sum() / (ref | v).sum()
        if mejor is None or iou > mejor[0]:
            mejor = (iou, v, m, k, dx, dy)
    return mejor


def disco(r):
    r = max(1, int(round(r)))
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


def con_acabado(ref):
    """La imagen con el mismo redondeo de esquinas que lleva el modelo (convexas 1,3×canto,
    cóncavas 0,6×canto, ver redibujar.py): la reproducción perfecta con este acabado.
    Contra esto, cualquier diferencia es un error, no el redondeo."""
    b = s.BISEL * s.DIAMETRO / ESCALA_MODELO * N  # radio del canto en px de comparación
    abierta = ndimage.binary_opening(ref, disco(1.3 * b))
    return ndimage.binary_closing(np.pad(abierta, 20), disco(0.6 * b))[20:-20, 20:-20]


def contorno(m):
    return m & ~ndimage.binary_erosion(m)


def topologia(m):
    piezas = ndimage.label(m)[1]
    fondo, nf = ndimage.label(~m)
    # huecos = zonas de fondo que no tocan el borde de la imagen
    borde = set(np.unique(np.concatenate([fondo[0], fondo[-1], fondo[:, 0], fondo[:, -1]])))
    huecos = len(set(range(1, nf + 1)) - borde)
    return piezas, huecos


def revisar_malla(m):
    r = {}
    unida = m.copy()
    unida.merge_vertices(merge_tex=True, merge_norm=True)
    r["estanca"] = bool(unida.is_watertight)
    cuerpos = unida.split(only_watertight=False)
    fondo = m.vertices[:, 2].max()
    # canto redondeado: cada cuerpo tiene anillos a alturas intermedias, no solo 0 y fondo
    sin_canto = sum(1 for b in cuerpos if len(np.unique(np.round(b.vertices[:, 2], 6))) <= 2)
    r["piezas_sin_canto"] = sin_canto
    z = m.vertices[:, 2]
    n = m.vertex_normals
    r["normal_frente_ok"] = bool(np.allclose(n[np.isclose(z, fondo)], [0, 0, 1], atol=1e-3))
    r["normal_dorso_ok"] = bool(np.allclose(n[np.isclose(z, z.min())], [0, 0, -1], atol=1e-3))
    mat = getattr(m.visual, "material", None)
    r["material"] = getattr(mat, "name", None)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("fuente")
    ap.add_argument("--informe")
    a = ap.parse_args()

    original = silueta_imagen(a.fuente)
    iou, vec, malla, k, dx, dy = alinear(a.glb, original)  # iou: contra la imagen tal cual
    print(f"alineado: escala {k}, desplazamiento ({dx}, {dy}) px")
    ref = con_acabado(original)  # el resto, contra la imagen con el acabado aplicado

    # distancia simétrica entre contornos
    cr, cv = contorno(ref), contorno(vec)
    d_a_ref = ndimage.distance_transform_edt(~cr)[cv]
    d_a_vec = ndimage.distance_transform_edt(~cv)[cr]
    dist = np.concatenate([d_a_ref, d_a_vec]) / N * 100
    p95, dmax = float(np.percentile(dist, 95)), float(dist.max())

    # zonas de discrepancia (se ignora la franja de 2 px del propio contorno)
    diff = ndimage.binary_opening(ref ^ vec, iterations=2)
    lab, nz = ndimage.label(diff)
    area_disco = np.pi * (N / 2) ** 2
    zonas = []
    for k, sl in enumerate(ndimage.find_objects(lab), 1):
        msk = lab[sl] == k
        area = msk.sum()
        cy, cx = ndimage.center_of_mass(msk)
        tipo = "sobra" if vec[sl][msk].any() else "falta"
        zonas.append((area / area_disco * 100, tipo, int(cx + sl[1].start), int(cy + sl[0].start)))
    zonas.sort(reverse=True)
    zmax = zonas[0][0] if zonas else 0.0

    top_ref, top_vec = topologia(original), topologia(vec)
    mal = revisar_malla(malla)

    # no se puede exigir más precisión que la de la imagen: con fuentes pequeñas las
    # tolerancias de distancia pasan a medio píxel (p95) y 1,5 píxeles (máximo) del original
    u = dict(UMBRALES)
    u["contorno_p95_max"] = round(max(u["contorno_p95_max"], 0.5 * PX), 2)
    u["contorno_max_max"] = round(max(u["contorno_max_max"], 1.5 * PX), 2)
    u["zona_max_max"] = round(max(u["zona_max_max"], 0.02 * (PX / 0.25) ** 2), 3)
    print(f"píxel del original = {PX:.2f} % del diámetro")
    checks = [
        ("parecido (IoU)", iou >= UMBRALES["iou_min"], f"{iou:.4f} ≥ {UMBRALES['iou_min']}"),
        ("contorno p95", p95 <= u["contorno_p95_max"], f"{p95:.2f} % ≤ {u['contorno_p95_max']} %"),
        ("contorno máximo", dmax <= u["contorno_max_max"], f"{dmax:.2f} % ≤ {u['contorno_max_max']} %"),
        ("mayor zona de error", zmax <= u["zona_max_max"], f"{zmax:.3f} % ≤ {u['zona_max_max']} %"),
        ("piezas", top_ref[0] == top_vec[0], f"modelo {top_vec[0]} / imagen {top_ref[0]}"),
        ("huecos", top_ref[1] == top_vec[1], f"modelo {top_vec[1]} / imagen {top_ref[1]}"),
        ("malla cerrada", mal["estanca"], str(mal["estanca"])),
        ("canto en todas las piezas", mal["piezas_sin_canto"] == 0, f"{mal['piezas_sin_canto']} sin canto"),
        ("normal del frente exacta", mal["normal_frente_ok"], str(mal["normal_frente_ok"])),
        ("normal del dorso exacta", mal["normal_dorso_ok"], str(mal["normal_dorso_ok"])),
        ("material", mal["material"] == "laca", str(mal["material"])),
    ]
    ok = all(c[1] for c in checks)
    for nombre, bien, valor in checks:
        print(f"{'PASA ' if bien else 'FALLA'}  {nombre:28s} {valor}")
    print(f"\n{'APROBADO' if ok else 'RECHAZADO'} — {sum(not c[1] for c in checks)} fallos")
    if zonas:
        print("peores zonas (% área, tipo, x, y a 1200 px):")
        for i, z in enumerate(zonas[:8], 1):
            print(f"  {i}. {z[0]:.3f} % {z[1]} en ({z[2]}, {z[3]})")

    if a.informe:
        img = np.full((N, N, 3), 255, np.uint8)
        img[ref & vec] = [230, 120, 110]
        img[ref & ~vec] = [200, 0, 0]
        img[vec & ~ref] = [0, 170, 0]
        im = Image.fromarray(img)
        d = ImageDraw.Draw(im)
        for i, z in enumerate(zonas[:8], 1):
            d.ellipse((z[2] - 22, z[3] - 22, z[2] + 22, z[3] + 22), outline=(0, 0, 255), width=3)
            d.text((z[2] + 25, z[3] - 10), str(i), fill=(0, 0, 255))
        im.save(a.informe)

    print(json.dumps({"aprobado": ok, "iou": round(float(iou), 4), "contorno_p95": round(p95, 3),
                      "contorno_max": round(dmax, 3), "zona_max": round(zmax, 4)}))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
