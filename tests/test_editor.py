"""Pruebas del servidor del editor y de simbolo.exportar().  Uso: .venv/bin/pytest tests/

Todo se escribe en carpetas temporales (tmp_path): glb/, svg/ y editor/ no se tocan.
"""
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
import shapely
import trimesh
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))
import editor  # noqa: E402
import simbolo as s  # noqa: E402

SIMBOLOS = ["amor", "fu-circular", "fu-hiragino", "fu-trazo", "shou-circular", "shou-cruz", "shou-sello", "xi-doble"]


@pytest.fixture
def salida(tmp_path, monkeypatch):
    monkeypatch.setattr(editor, "SALIDA", tmp_path)
    return tmp_path


def en_mundo(doc):
    """Capas con t de solo traslación (las de piezas_svg y piezas_curvas) en el mundo: puntos
    o nodos; los tiradores de un nodo son relativos y no cambian."""
    mover = lambda p, t: [p[0] + t["x"], p[1] + t["y"]]  # noqa: E731
    return [{"op": c["op"], "anillos": [[{**n, "p": mover(n["p"], c["t"])} if isinstance(n, dict) else mover(n, c["t"])
                                         for n in a] for a in c["anillos"]]} for c in doc["capas"]]


def verificar(glb, fuente):
    r = subprocess.run([sys.executable, str(RAIZ / "tools/verificar.py"), str(glb), str(fuente)],
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("nombre", SIMBOLOS)
def test_ida_y_vuelta_sigue_aprobado(nombre, salida):
    """Criterio de F4: abrir un símbolo aprobado (ya ajustado a curvas, como lo abre el
    editor) y generarlo sin tocar: el verificador lo aprueba, con menos del 10 % de nodos.
    fu-circular es la excepción documentada en el plan (sondeo 4.0): su aprobación está en
    el último escalón de píxel del p95 y mover su borde 0,00005 ya lo rechaza; se exige
    que su geometría quede a menos de 0,0003 de la original (error total del sondeo: 0,0002
    del ajuste más pasar arcos a cúbicas y aplanar)."""
    fuente = RAIZ / "fuentes" / f"{nombre}.png"
    if not fuente.exists():  # shou-sello y xi-doble no se publican (marca de agua)
        pytest.skip(f"falta {fuente.name}")
    denso, doc = editor.piezas_svg(nombre), editor.piezas_curvas(nombre)
    nodos = lambda d: sum(len(a) for c in d["capas"] for a in c["anillos"])  # noqa: E731
    assert nodos(doc) <= 0.10 * nodos(denso), (nodos(doc), nodos(denso))
    info = editor.generar(f"{nombre}-prueba", doc, en_mundo(doc))
    assert info["estanca"]
    if nombre == "fu-circular":
        bisel = doc["ajustes"]["bisel"]
        g0, g1 = editor.geometria(en_mundo(denso), bisel), editor.geometria(en_mundo(doc), bisel)
        assert shapely.hausdorff_distance(g0.boundary, g1.boundary, densify=0.05) < 0.0003
        return
    codigo, r = verificar(salida / "glb" / f"{nombre}-prueba.glb", fuente)
    assert codigo == 0 and r["aprobado"], r


def test_aplanar_es_la_misma_en_el_navegador():
    """aplanar() de editor.html y la de tools/curvas.py dan los mismos puntos, bit a bit
    (la del servidor manda; la del navegador es la de la vista)."""
    import re
    import curvas
    fuente = re.search(r"function aplanar\(.*?\n}\n", (RAIZ / "editor.html").read_text(), re.S).group(0)
    anillos = [a for c in editor.piezas_curvas("fu-trazo")["capas"] for a in c["anillos"]]
    anillos.append([{"p": [0.5, 0], "ent": [0, -0.27], "sal": [0, 0.27]}, {"p": [0, 0.5], "ent": [0.27, 0], "sal": None},
                    {"p": [-0.5, 0], "ent": None, "sal": None}])
    js = fuente + f"console.log(JSON.stringify({json.dumps(anillos)}.map((a) => aplanar(a))));"
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == [curvas.aplanar(a) for a in anillos]


def test_documento_version_1_da_la_misma_forma():
    """migrar() convierte cada punto en un nodo vivo: el servidor aplana eso a los mismos
    puntos, así que un documento de la versión 1 genera lo mismo que antes."""
    for c in editor.piezas_svg("shou-cruz")["capas"]:
        nodos = [[{"p": p, "ent": None, "sal": None, "tipo": "vivo"} for p in a] for a in c["anillos"]]
        assert editor.forma_capa(nodos).equals_exact(editor.forma_capa(c["anillos"]), 0)


def test_exportar_con_parametros_no_toca_los_globales(tmp_path):
    antes = (s.FONDO, s.BISEL, list(s.COLOR), s.PASOS)
    (tmp_path / "glb").mkdir(); (tmp_path / "svg").mkdir()
    doc = editor.piezas_svg("xi-doble")
    geo = editor.geometria(en_mundo(doc), 0.012)
    s.exportar(geo, "grueso", fondo=0.12, bisel=0.012, color=[0, 0, 1, 1], carpeta=tmp_path)
    assert (s.FONDO, s.BISEL, list(s.COLOR), s.PASOS) == antes
    m = trimesh.load(tmp_path / "glb" / "grueso.glb", force="mesh")
    alto = m.vertices[:, 2].max() - m.vertices[:, 2].min()
    assert abs(alto - 0.12) < 1e-6


def test_no_pisa_un_simbolo_aprobado(salida):
    doc = editor.piezas_svg("shou-cruz")
    with pytest.raises(ValueError, match="no salió del editor"):
        editor.generar("shou-cruz", doc, en_mundo(doc))
    with pytest.raises(ValueError, match="no salió del editor"):
        editor.guardar("shou-cruz", doc)


def test_historial_guarda_copias_y_se_limita(salida, monkeypatch):
    monkeypatch.setattr(editor, "CADA_COPIA", 0)
    doc = editor.piezas_svg("xi-doble")
    for i in range(editor.COPIAS + 5):
        doc["capas"][0]["t"]["x"] = i / 1000
        editor.guardar("hist", doc)
    editor.guardar("hist", doc)  # igual que el anterior: sin copia nueva
    copias = list((salida / "editor" / ".historial" / "hist").glob("*.json"))
    assert len(copias) == editor.COPIAS
    assert json.loads((salida / "editor" / "hist.json").read_text())["capas"][0]["t"]["x"] == (editor.COPIAS + 4) / 1000


@pytest.mark.parametrize("anillos, piezas", [
    ([[[0, 0], [0.2, 0.2], [0.2, 0], [0, 0.2]]], 2),               # pajarita: el anillo se cruza a sí mismo
    ([[[0, 0], [0.2, 0], [0.2, 0], [0.2, 0.2], [0, 0.2]]], 1),     # nodo repetido
    ([[[0, 0], [0.2, 0], [0.4, 0]]], 0),                           # área cero
    ([[[0, 0], [0.2, 0]]], 0),                                     # menos de 3 nodos
])
def test_geometria_degenerada_no_rompe(anillos, piezas):
    """Lo que puede dejar un arrastre de nodos a medias: el servidor responde sin caerse."""
    geo = editor.geometria([{"op": "unir", "anillos": anillos}], s.BISEL)
    assert len(editor.a_listas(geo)) == piezas


def test_restar_abre_un_hueco():
    cuadro = [[-0.3, -0.3], [0.3, -0.3], [0.3, 0.3], [-0.3, 0.3]]
    agujero = [[-0.1, -0.1], [0.1, -0.1], [0.1, 0.1], [-0.1, 0.1]]
    geo = editor.geometria([{"op": "unir", "anillos": [cuadro]}, {"op": "restar", "anillos": [agujero]}], s.BISEL)
    (poli,) = editor.a_listas(geo)
    assert len(poli) == 2  # exterior + un hueco


# ---------- F1: cuchilla

REJILLA = [[[-0.6, y], [0.6, y]] for y in (-0.2, 0.05, 0.25)] + [[[x, -0.6], [x, 0.6]] for x in (-0.15, 0.1)]


def cortar_como_el_navegador(capas, linea):
    """editor.html: cada pieza pasa a coordenadas locales (menos el centro de su caja) y
    vuelve al mundo al sumarlo; esa ida y vuelta es la que podría abrir una rendija."""
    cortes = {c["id"]: c["piezas"] for c in editor.cortar(capas, linea)["cortes"]}
    nuevas = []
    for c in capas:
        for k, poli in enumerate(cortes.get(c["id"], [])):
            xs, ys = [p[0] for p in poli[0]], [p[1] for p in poli[0]]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            local = [[[x - cx, y - cy] for x, y in a[:-1]] for a in poli]
            nuevas.append({"id": c["id"] * 100 + k, "op": c["op"], "t": (cx, cy),
                           "anillos": [[[x + cx, y + cy] for x, y in a] for a in local]})
        if c["id"] not in cortes:
            nuevas.append(c)
    return nuevas


def test_cortar_en_trazos_sin_mover_sigue_aprobado(salida):
    """Criterio de F1: shou-cruz en ≥ 6 capas, generado sin mover nada → APROBADO
    (el corte no deja grietas)."""
    doc = editor.piezas_svg("shou-cruz")
    capas = [{**c, "id": i + 1} for i, c in enumerate(en_mundo(doc))]
    for linea in REJILLA:
        capas = cortar_como_el_navegador(capas, linea)
    assert len(capas) >= 6
    info = editor.generar("cortada", doc, capas)
    assert info["estanca"] and info["piezas"] == 1
    codigo, r = verificar(salida / "glb" / "cortada.glb", RAIZ / "fuentes" / "shou-cruz.png")
    assert codigo == 0 and r["aprobado"], r


def test_mover_una_pieza_cortada_cambia_solo_su_zona():
    doc = editor.piezas_svg("shou-cruz")
    capas = [{**c, "id": i + 1} for i, c in enumerate(en_mundo(doc))]
    for linea in REJILLA:
        capas = cortar_como_el_navegador(capas, linea)
    antes = editor.geometria(capas, s.BISEL)
    pieza = max(capas, key=lambda c: editor.forma_capa(c["anillos"]).area)
    movida = {**pieza, "anillos": [[[x + 0.03, y] for x, y in a] for a in pieza["anillos"]]}
    despues = editor.geometria([movida if c is pieza else c for c in capas], s.BISEL)
    zona = unary_union([editor.forma_capa(pieza["anillos"]), editor.forma_capa(movida["anillos"])]).envelope
    cambio = antes.symmetric_difference(despues)
    assert cambio.area > 1e-4  # se movió de verdad
    # Fuera de su zona solo puede quedar ruido del redondeo en planta, que se recalcula
    # sobre toda la forma: franjas de ~3e-6 de grosor (medido), 300 veces más finas que
    # un píxel del verificador (1/1200). Se mide el grosor, no el área.
    fuera = cambio.difference(zona.buffer(s.BISEL * 2))
    assert all(2 * p.area / p.length < 1e-5 for p in s.lista(fuera) if not p.is_empty)


def test_corte_que_no_cruza_no_corta():
    cuadro = [[-0.3, -0.3], [0.3, -0.3], [0.3, 0.3], [-0.3, 0.3]]
    capas = [{"id": 1, "op": "unir", "anillos": [cuadro]}]
    assert editor.cortar(capas, [[-0.1, 0], [0.1, 0]])["cortes"] == []   # dentro, a más de 0,15 del borde
    assert editor.cortar(capas, [[-0.5, 0.5], [0.5, 0.5]]) == {"cortes": [], "atraviesa": []}  # por fuera
    (corte,) = editor.cortar(capas, [[-0.5, 0], [0.5, 0]])["cortes"]    # de lado a lado
    assert len(corte["piezas"]) == 2


def test_historial_no_copia_mas_de_una_vez_cada_30_s(salida):
    """El navegador guarda 1,5 s después de cada cambio: sin este límite, las 20 copias
    serían los últimos 30 segundos de trabajo."""
    doc = editor.piezas_svg("xi-doble")
    for i in range(5):
        doc["capas"][0]["t"]["x"] = i / 1000
        editor.guardar("seguido", doc)
    assert len(list((salida / "editor" / ".historial" / "seguido").glob("*.json"))) == 1
    assert json.loads((salida / "editor" / "seguido.json").read_text())["capas"][0]["t"]["x"] == 0.004


def test_parche_al_cerrar_completa_los_nodos_guardados(salida):
    """sendBeacon admite 64 KB; shou-circular ocupa 105. Al cerrar la pestaña se mandan
    sin nodos (anillos "=") las capas que no los cambiaron, y el servidor los completa."""
    doc = editor.piezas_svg("shou-circular")
    for i, c in enumerate(doc["capas"]):
        c["id"] = i + 1
    editor.guardar("grande", doc)
    parche = json.loads(json.dumps(doc))
    parche["capas"][0]["t"]["x"] += 0.01
    for c in parche["capas"]:
        c["anillos"] = "="
    assert len(json.dumps({"nombre": "grande", "doc": parche})) < 64 * 1024
    editor.guardar("grande", editor.completar_parche("grande", parche))
    guardado = json.loads((salida / "editor" / "grande.json").read_text())
    assert guardado["capas"][0]["anillos"] == doc["capas"][0]["anillos"]
    assert guardado["capas"][0]["t"]["x"] == doc["capas"][0]["t"]["x"] + 0.01
    parche["capas"][0].update(id=999, anillos="=")  # completar_parche rellenó el anterior
    with pytest.raises(ValueError, match="parche sin base"):
        editor.completar_parche("grande", parche)


def test_extremo_dentro_del_trazo_se_prolonga_solo_hasta_salir():
    """A mano alzada es fácil empezar o acabar encima del trazo: ese extremo se prolonga
    hasta salir de él, pero no más de 0,15 (no llega a cortar trazos que no se tocaron)."""
    barra = [[-0.4, -0.05], [0.4, -0.05], [0.4, 0.05], [-0.4, 0.05]]
    capas = [{"id": 1, "op": "unir", "anillos": [barra]}]
    (corte,) = editor.cortar(capas, [[0, 0.02], [0, -0.2]])["cortes"]   # empieza dentro de la barra
    assert len(corte["piezas"]) == 2
    (corte,) = editor.cortar(capas, [[0, 0.01], [0, -0.01]])["cortes"]  # las dos puntas dentro
    assert len(corte["piezas"]) == 2
    ancha = [[-0.4, -0.4], [0.4, -0.4], [0.4, 0.4], [-0.4, 0.4]]
    assert editor.cortar([{"id": 2, "op": "unir", "anillos": [ancha]}], [[0, 0.01], [0, -0.01]])["cortes"] == []


def test_costuras_se_suman_hasta_separar(salida):
    """shou-cruz: sus mitades izquierda y derecha solo se tocan por el anillo, arriba y
    abajo. Un corte arriba no separa nada (queda como costura); con el de abajo, dos
    mitades. Y generado sin mover nada sigue APROBADO."""
    doc = editor.piezas_svg("shou-cruz")
    capa = {**en_mundo(doc)[0], "id": 1}
    arriba, abajo = [[0, 0.56], [0, 0.38]], [[0, -0.56], [0, -0.38]]
    r = editor.cortar([capa], arriba)
    assert r == {"cortes": [], "atraviesa": [1]}
    r = editor.cortar([{**capa, "costuras": [arriba]}], abajo)
    (corte,) = r["cortes"]
    assert len(corte["piezas"]) == 2
    capas = [{"id": k, "op": "unir", "anillos": poli} for k, poli in enumerate(corte["piezas"])]
    editor.generar("mitades", doc, capas)
    codigo, v = verificar(salida / "glb" / "mitades.glb", RAIZ / "fuentes" / "shou-cruz.png")
    assert codigo == 0 and v["aprobado"], v


# ---------- sugerencias de corte

def capas_de(nombre):
    doc = editor.piezas_svg(nombre)
    return doc, [{**c, "id": i + 1} for i, c in enumerate(en_mundo(doc))]


def aplicar(capas, linea, sig):
    """Lo que hace el navegador con la respuesta de /api/cortar: costuras y piezas nuevas."""
    r = editor.cortar(capas, linea)
    for id_ in r["atraviesa"]:
        c = next(c for c in capas if c["id"] == id_)
        c["costuras"] = [*c.get("costuras", []), linea]
    for corte in r["cortes"]:
        i = next(k for k, c in enumerate(capas) if c["id"] == corte["id"])
        capas[i:i + 1] = [{"id": next(sig), "op": capas[i]["op"], "anillos": p} for p in corte["piezas"]]
    return r


def test_sugerencias_de_shou_cruz_caen_en_el_material():
    _, capas = capas_de("shou-cruz")
    sug = editor.sugerencias(capas)
    assert len(sug) == 40  # sondeo 2026-09-26: las 40 en uniones reales
    for linea in sug:  # cada una, sola, corta o queda como costura: nunca «no pasa por nada»
        r = editor.cortar(capas, linea)
        assert r["cortes"] or r["atraviesa"]


def test_aplicar_todas_las_sugerencias_sigue_aprobado(salida):
    """Todas las sugerencias, una tras otra (con costuras): piezas válidas, y el símbolo
    generado sin mover nada sigue APROBADO."""
    import itertools
    doc, capas = capas_de("shou-cruz")
    sig = itertools.count(100)
    for linea in editor.sugerencias(capas):
        aplicar(capas, linea, sig)
    assert len(capas) >= 20
    assert all(Polygon(c["anillos"][0], c["anillos"][1:]).is_valid for c in capas)
    editor.generar("sugerida", doc, capas)
    codigo, v = verificar(salida / "glb" / "sugerida.glb", RAIZ / "fuentes" / "shou-cruz.png")
    assert codigo == 0 and v["aprobado"], v


def test_soltar_una_barra_con_tres_clics():
    """La tarea de usuario de F1 con sugerencias: la barra superior derecha de shou-cruz
    se suelta con las 3 de sus uniones (conector, tallo y anillo)."""
    import itertools
    _, capas = capas_de("shou-cruz")
    medio = lambda s: ((s[0][0] + s[1][0]) / 2, (s[0][1] + s[1][1]) / 2)
    suyas = [s for s in editor.sugerencias(capas) if 0.02 < medio(s)[1] < 0.14 and medio(s)[0] > 0.05][:3]
    sig = itertools.count(100)
    for linea in suyas:
        aplicar(capas, linea, sig)
    areas = sorted(editor.forma_capa(c["anillos"]).area for c in capas)
    assert any(abs(a - 0.0253) < 5e-4 for a in areas), areas


def test_pares_casi_paralelos_se_funden():
    """xi-doble: 4 pares de bordes casi alineados (a ~0,015) dejaban una astilla entre sus
    dos cortes; se funden en uno por el medio (56 → 52)."""
    _, capas = capas_de("xi-doble")
    sug = editor.sugerencias(capas)
    assert len(sug) == 52
    for i, a in enumerate(sug):
        for b in sug[i + 1:]:
            la, lb = LineString(a), LineString(b)
            ua = ((a[1][0] - a[0][0]) / la.length, (a[1][1] - a[0][1]) / la.length)
            paralelas = abs(ua[0] * (b[1][0] - b[0][0]) + ua[1] * (b[1][1] - b[0][1])) >= lb.length * 0.996
            assert not (paralelas and la.distance(lb) < 0.02)


def test_astilla_se_funde_con_su_vecina():
    """Dos cortes que se cruzan junto a una esquina dejan un cuadradito (aquí 0,005 × 0,005,
    como el de shou-cruz): no es una capa, se funde con su vecina. Las tiras de 0,005 ×
    0,595 sí quedan (0,003 de área, por encima del umbral de 1e-4)."""
    cuadro = [[-0.3, -0.3], [0.3, -0.3], [0.3, 0.3], [-0.3, 0.3]]
    capas = [{"id": 1, "op": "unir", "anillos": [cuadro], "costuras": [[[0.295, 0.4], [0.295, -0.4]]]}]
    (corte,) = editor.cortar(capas, [[-0.4, 0.295], [0.4, 0.295]])["cortes"]
    areas = [Polygon(p[0], p[1:]).area for p in corte["piezas"]]
    assert len(areas) == 3 and min(areas) > 1e-4, areas
    assert abs(sum(areas) - 0.36) < 1e-12


def test_bordes_rectos_para_el_iman():
    """Los bordes rectos que usa el imán de la cuchilla: los de las barras, exactos; y ningún
    arco del anillo de shou-cruz pasa por recto (1° de tolerancia da tramos < 0,015)."""
    _, capas = capas_de("shou-cruz")
    bordes = editor.bordes_rectos(capas)
    assert len(bordes) > 100
    assert all(len(b) == 3 and b[2] == 1 for b in bordes)  # [a, b, id de la capa]
    assert [[0.29894, 0.04164], [0.06227, 0.04164]] in [[[round(v, 5) for v in q] for q in b[:2]] for b in bordes]
    radio = lambda q: math.hypot(*q)
    assert not any(radio(a) > 0.45 and radio(b) > 0.45 and abs(radio(a) - radio(b)) < 1e-3 and math.dist(a, b) > 0.02
                   for a, b, _ in bordes)  # ninguna «recta» sobre el anillo exterior


# ---------- F2: simetría en vivo

def agujero(cx, cy, r=0.02):
    return [[cx + r * math.cos(k / 24 * 2 * math.pi), cy + r * math.sin(k / 24 * 2 * math.pi)] for k in range(24)]


@pytest.mark.parametrize("simetria, izquierda, derecha", [
    (None, True, False),                    # sin simetría: el hueco solo donde se hizo
    ({"lr": True, "x": -1}, True, True),    # manda la izquierda: el hueco en los dos lados
    ({"lr": True, "x": 1}, False, False),   # manda la derecha (sin hueco): desaparece
])
def test_simetria_refleja_la_mitad_que_manda(simetria, izquierda, derecha):
    """No vale resultado ∪ reflejo: el hueco de la mitad que manda quedaría tapado."""
    _, capas = capas_de("xi-doble")
    geo = editor.geometria(capas + [{"id": 99, "op": "restar", "anillos": [agujero(-0.3, 0.1)]}], s.BISEL, simetria)
    assert (not geo.contains(Point(-0.3, 0.1))) == izquierda
    assert (not geo.contains(Point(0.3, 0.1))) == derecha


def test_simetria_ab_y_doble():
    _, capas = capas_de("xi-doble")
    hueco = [{"id": 99, "op": "restar", "anillos": [agujero(-0.3, 0.1)]}]
    ab = editor.geometria(capas + hueco, s.BISEL, {"ab": True, "y": 1})
    assert not ab.contains(Point(-0.3, 0.1)) and not ab.contains(Point(-0.3, -0.1))
    doble = editor.geometria(capas + hueco, s.BISEL, {"lr": True, "ab": True, "x": -1, "y": 1})
    assert all(not doble.contains(Point(x, y)) for x in (-0.3, 0.3) for y in (-0.1, 0.1))


def test_simetria_generada_glb_simetrico(salida):
    """Criterio de F2: con simetría izq. ↔ der., un hueco en la mitad que manda sale en los
    dos lados del GLB, y su silueta coincide con su reflejo (IoU ≥ 0,999)."""
    import verificar
    doc, capas = capas_de("xi-doble")
    doc["simetria"] = {"lr": True, "x": -1}
    info = editor.generar("simetrico", doc, capas + [{"id": 99, "op": "restar", "anillos": [agujero(-0.3, 0.1)]}])
    assert info["estanca"]
    m, _ = verificar.silueta_modelo(salida / "glb" / "simetrico.glb")
    iou = (m & m[:, ::-1]).sum() / (m | m[:, ::-1]).sum()
    assert iou >= 0.999, iou


def test_simetria_no_degrada_un_simbolo_simetrico(salida):
    """xi-doble se aprobó con --simetria-lr: rehecho desde su mitad izquierda sigue APROBADO."""
    doc, capas = capas_de("xi-doble")
    doc["simetria"] = {"lr": True, "x": -1}
    editor.generar("xi-mitad", doc, capas)
    codigo, v = verificar(salida / "glb" / "xi-mitad.glb", RAIZ / "fuentes" / "xi-doble.png")
    assert codigo == 0 and v["aprobado"], v


def circulo_bezier(r=0.3):
    k = r * 0.5522847498
    return [{"p": [x, y], "ent": [y / r * k, -x / r * k], "sal": [-y / r * k, x / r * k], "tipo": "espejo"}
            for x, y in [(r, 0), (0, r), (-r, 0), (0, -r)]]


def test_la_cuchilla_parte_curvas_sin_aplanarlas():
    """4.3: un círculo de 4 cúbicas cortado por y = 0,1 da dos piezas con curvas (no cientos
    de puntos): la de arriba, 2 cruces + el nodo de arriba; la de abajo, 2 cruces + 3
    nodos. Sobre el mismo círculo (< 1e-4) y con la costura en los mismos dos puntos (los
    cruces se llevan a la curva: se mueven de y = 0,1 lo que la cuerda del aplanado)."""
    import curvas
    capa = {"id": 1, "op": "unir", "anillos": [circulo_bezier()]}
    r = editor.cortar([capa], [[-0.5, 0.1], [0.5, 0.1]])
    piezas = r["cortes"][0]["piezas"]
    assert sorted(len(p[0]) for p in piezas) == [3, 5]
    circulo = editor.forma_capa(capa["anillos"])
    cruces = []
    for p in piezas:
        plano = Polygon(curvas.aplanar(p[0]))
        mitad = circulo.intersection(box(-1, 0.1, 1, 1) if plano.centroid.y > 0.1 else box(-1, -1, 1, 0.1))
        assert shapely.hausdorff_distance(plano.boundary, mitad.boundary, densify=0.05) < 1e-4
        assert all(n["ent"] or n["sal"] for n in p[0])  # cada nodo toca una curva
        cruces.append(sorted(tuple(n["p"]) for n in p[0] if abs(n["p"][1] - 0.1) < 1e-4))
    assert cruces[0] == cruces[1] and len(cruces[0]) == 2  # la costura, en los mismos dos puntos


def test_cortar_shou_cruz_en_curvas_sigue_aprobado(salida):
    """Criterio de F1 con curvas: las 40 sugerencias sobre shou-cruz ya en curvas dan piezas
    válidas con sus curvas (no polígonos densos), y generado sin mover nada, APROBADO."""
    import itertools
    doc = editor.piezas_curvas("shou-cruz")
    capas = [{**c, "id": i + 1} for i, c in enumerate(en_mundo(doc))]
    sig = itertools.count(100)
    for linea in editor.sugerencias(capas):
        aplicar(capas, linea, sig)
    assert len(capas) >= 20
    assert all(editor.forma_capa(c["anillos"]).is_valid for c in capas)
    nodos = [n for c in capas for a in c["anillos"] for n in a]
    assert len(nodos) < 400 and sum(1 for n in nodos if n["ent"] or n["sal"]) > 150
    editor.generar("sugerida-curvas", doc, capas)
    codigo, v = verificar(salida / "glb" / "sugerida-curvas.glb", RAIZ / "fuentes" / "shou-cruz.png")
    assert codigo == 0 and v["aprobado"], v
