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
import shapely.affinity
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
                                         for n in a] for a in c["anillos"]],
             **{k: c[k] for k in ("trazo", "abierto") if k in c}} for c in doc["capas"]]


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
    js = fuente + (f"console.log(JSON.stringify([...{json.dumps(anillos)}.map((a) => aplanar(a)), "
                   f"...{json.dumps(anillos)}.map((a) => aplanar(a, 0.0001, false))]));")
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == [curvas.aplanar(a) for a in anillos] + [curvas.aplanar(a, cerrado=False) for a in anillos]


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
    if not (RAIZ / "fuentes" / "xi-doble.png").exists():  # no se publica (marca de agua)
        pytest.skip("falta xi-doble.png")
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


def test_generar_rechaza_un_trazo_fino(salida):
    """Criterio de F5: un trazo de 0,01 de ancho (el canto se lo come entero) → RECHAZADO y
    solo la detallada; sin él, APROBADO y las tres versiones. Por pieza: junto a un cuadrado
    grande, el trazo fino apenas mueve la pérdida total (la de letras.py no lo veía)."""
    cuadro = lambda x, y, w, h: {"op": "unir", "anillos": [[[x - w / 2, y - h / 2], [x + w / 2, y - h / 2],  # noqa: E731
                                                            [x + w / 2, y + h / 2], [x - w / 2, y + h / 2]]]}
    doc = {"version": 2, "capas": [], "ajustes": dict(editor.AJUSTES)}
    capas = [cuadro(0, 0, 0.6, 0.6), cuadro(0, 0.4, 0.3, 0.01)]
    base = editor.planta(capas)
    assert 1 - editor.acabar(base, s.BISEL).area / base.area < s.PERDIDA_MAX  # en total no se ve
    r = editor.generar("fino", doc, capas)
    assert not r["aprobado"] and [c["que"] for c in r["comprobaciones"] if not c["pasa"]] == ["trazo fino"]
    assert r["archivos"] == ["glb/fino.glb"] and not (salida / "glb" / "fino-ligera.glb").exists()
    r = editor.generar("fino", doc, capas[:1])
    assert r["aprobado"] and len(r["archivos"]) == 3 and r["aviso_web"] is None


# ---------- F6: importar SVG
LOGO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 160">
  <style>.rojo{fill:#e30613} .linea{fill:none}</style>
  <defs><path id="oculto" d="M0 0h500v500z"/></defs>
  <circle class="rojo" cx="60" cy="60" r="40"/>
  <path class="linea" d="M0 0L240 160"/>
  <g transform="rotate(30 170 50)"><rect x="130" y="20" width="80" height="60" rx="15" ry="10"/></g>
  <path d="M20 150C20 110 100 110 100 150ZM130 150q30-40 60 0t40 0z"/>
  <path d="M140 95a25 25 0 1 1 50 0a25 25 0 1 1-50 0zM152 95a13 13 0 1 0 26 0a13 13 0 1 0-26 0z"/>
</svg>"""


def bezier_densa(P, n=4000):
    """La cúbica muestreada a mano (sin pasar por curvas.aplanar ni por el importador)."""
    return [tuple((1 - t) ** 3 * P[0][j] + 3 * (1 - t) ** 2 * t * P[1][j] + 3 * (1 - t) * t * t * P[2][j] + t ** 3 * P[3][j]
                  for j in (0, 1)) for t in (k / n for k in range(n + 1))]


def logo_exacto():
    """El dibujo de LOGO, en coordenadas del SVG, de las fórmulas de cada figura."""
    from shapely import affinity
    circulo = Point(60, 60).buffer(40, quad_segs=1024)
    esquina = lambda x, y: affinity.scale(Point(x, y).buffer(1, quad_segs=1024), 15, 10, origin=(x, y))  # noqa: E731
    rect = unary_union([box(145, 20, 195, 80), box(130, 30, 210, 70),
                        *(esquina(x, y) for x in (145, 195) for y in (30, 70))])
    rect = affinity.rotate(rect, 30, origin=(170, 50))
    gota = Polygon(bezier_densa([(20, 150), (20, 110), (100, 110), (100, 150)]))
    # q30-40 60 0 t40 0: dos lóbulos (cuadráticas; el control de la t, el de la q reflejado)
    q1 = [(130 + 2 * t * (1 - t) * 30 + t * t * 60, 150 - 2 * t * (1 - t) * 40) for t in (k / 4000 for k in range(4001))]
    q2 = [(190 + 2 * t * (1 - t) * 30 + t * t * 40, 150 + 2 * t * (1 - t) * 40) for t in (k / 4000 for k in range(4001))]
    lobulos = shapely.make_valid(Polygon(q1 + q2))
    anillo = Point(165, 95).buffer(25, quad_segs=1024).difference(Point(165, 95).buffer(13, quad_segs=1024))
    return unary_union([circulo, rect, gota, lobulos, anillo])


def test_importar_svg_iou_con_su_dibujo(salida):
    """Criterio de F6: un SVG con arcos, cúbicas, cuadráticas, transform y estilos de clase
    importado → IoU ≥ 0,999 con el dibujo exacto de sus figuras (fórmulas, no el importador)."""
    from shapely import affinity
    r = editor.importar("Logo Final.svg", LOGO)
    assert r["nombre"] == "logo-final"
    doc, m = r["doc"], r["marco"]
    assert len(doc["capas"]) == 4 and all(c["op"] == "unir" for c in doc["capas"])  # sin lo que no pinta ni defs
    nodos = [n for c in doc["capas"] for a in c["anillos"] for n in a]
    assert sum(1 for n in nodos if n["ent"] or n["sal"]) >= 20 and len(nodos) < 60  # curvas, no polígonos
    hecho = editor.planta(en_mundo(doc))
    exacto = affinity.scale(affinity.translate(logo_exacto(), -m["cx"], -m["cy"]), m["s"], -m["s"], origin=(0, 0))
    iou = hecho.intersection(exacto).area / hecho.union(exacto).area
    assert iou >= 0.999, iou
    b = hecho.bounds
    assert abs(max(b[2] - b[0], b[3] - b[1]) - 1) < 1e-3 and abs(b[0] + b[2]) < 1e-3 and abs(b[1] + b[3]) < 1e-3
    info = editor.generar(r["nombre"], doc, en_mundo(doc))
    assert info["estanca"] and info["aprobado"]


@pytest.mark.parametrize("d, regla, area", [
    ("M0 0h10v10h-10zM3 3h4v4h-4z", "nonzero", 100),      # mismo sentido: nonzero lo rellena
    ("M0 0h10v10h-10zM3 3v4h4v-4z", "nonzero", 84),       # sentido contrario: hueco
    ("M0 0h10v10h-10zM3 3h4v4h-4z", "evenodd", 84),
    ("M0 0h6v6h-6zM4 4h6v6h-6z", "nonzero", 68),          # dos que se solapan: unión
    ("M0 0h6v6h-6zM4 4h6v6h-6z", "evenodd", 64),
])
def test_importar_respeta_la_regla_de_relleno(d, regla, area):
    capas, m = editor.leer_svg.leer(f'<svg xmlns="http://www.w3.org/2000/svg"><path fill-rule="{regla}" d="{d}"/></svg>')
    assert abs(editor.planta([{"op": c["op"], "anillos": c["anillos"]} for c in capas]).area / m["s"] ** 2 - area) < 1e-6


def test_importar_trayectos_raros():
    """Banderas de arco pegadas («a5 5 0 105 0»), dibujar tras Z sin M (otra subruta desde
    el inicio de la anterior) y números como «1.5.5» (= 1.5 y .5)."""
    sub = editor.leer_svg.subrutas("M0 0h10v10h-10zl5 0 0 5z")
    assert [r[0] for r in sub] == [(0, 0), (0, 0)] and sub[1][1][0] == ("recta", (5, 0))
    arco = editor.leer_svg.subrutas("M0 0a5 5 0 105 0")[0][1]
    assert len(arco) >= 3 and arco[-1][-1] == (5, 0)  # arco grande: tres cuartos de vuelta
    assert editor.leer_svg.subrutas("M1.5.5L2 2")[0][0] == (1.5, 0.5)
    with pytest.raises(ValueError):
        editor.leer_svg.leer('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0L9 9" fill="none"/></svg>')  # ni relleno ni trazo


def iou(a, b):
    return a.intersection(b).area / a.union(b).area


def test_exportar_svg_y_volver_a_importar():
    """Solo capas que unen: una ruta por capa con los nodos tal cual, y reimportado da la
    misma forma. Con una resta y simetría: la forma combinada, reajustada a curvas."""
    r = editor.importar("logo.svg", LOGO)
    capas = [{**c, "anillos": a} for c, a in zip(r["doc"]["capas"], (x["anillos"] for x in en_mundo(r["doc"])))]
    texto = editor.exportar_svg(capas, None, [0.6, 0.05, 0.03, 1])
    assert texto.count("<path") == 4 and 'fill="#cb3f30"' in texto and 'id="Círculo 1"' in texto
    vuelta = editor.importar("vuelta.svg", texto)["doc"]
    assert sum(len(a) for c in vuelta["capas"] for a in c["anillos"]) == sum(len(a) for c in capas for a in c["anillos"])
    assert iou(editor.planta(en_mundo(vuelta)), editor.planta(capas)) > 0.99999

    hueco = {"nombre": "Hueco", "op": "restar", "anillos": [[{"p": [x, y], "ent": None, "sal": None}
                                                             for x, y in ((-0.45, 0.2), (-0.2, 0.2), (-0.2, 0.3), (-0.45, 0.3))]]}
    sim = {"lr": True, "x": -1}
    texto = editor.exportar_svg([*capas, hueco], sim, [0.6, 0.05, 0.03, 1])
    assert texto.count("<path") == 1 and "C" in texto
    vuelta = editor.importar("vuelta.svg", texto)
    esperado = editor.planta([*capas, hueco], sim)
    # el importador lo escala a diámetro 1: se compara en la escala del diseño
    hecho = shapely.affinity.scale(editor.planta(en_mundo(vuelta["doc"])), 1 / vuelta["marco"]["s"] / 1000,
                                   1 / vuelta["marco"]["s"] / 1000, origin=(0, 0))
    hecho = shapely.affinity.translate(hecho, *(esperado.centroid.coords[0][k] - hecho.centroid.coords[0][k] for k in (0, 1)))
    assert iou(hecho, esperado) > 0.999


def test_campos_desconocidos_se_rechazan(salida):
    """G0: un campo que este editor no conoce no se borra en silencio al guardar: se rechaza
    y el error lo nombra."""
    doc = editor.piezas_curvas("xi-doble")
    doc["capas"][0]["inventado"] = 1
    doc["capas"][1]["anillos"][0][0]["otro"] = 2
    with pytest.raises(ValueError, match="capa.inventado, nodo.otro"):
        editor.guardar("con-campos-raros", doc)
    assert not (salida / "editor" / "con-campos-raros.json").exists()


# ---------- G2: caminos abiertos y trazos
def camino(*pts, abierto=True, **trazo):
    """Capa de trazo en el mundo con un camino de nodos vivos."""
    return {"id": 1, "op": "unir", "anillos": [[{"p": list(p), "ent": None, "sal": None} for p in pts]],
            "abierto": abierto, "trazo": {**editor.TRAZO, **trazo}}


def test_trazo_recto_tiene_el_area_exacta():
    """Criterio de G2: ancho 0,03 y extremos planos, L × 0,03 (< 1e-9); redondos, más un
    círculo de radio 0,015 (< 1e-5, por el aplanado del arco)."""
    L = 0.4
    plano = editor.forma_de(camino((-0.2, 0.1), (0.2, 0.1), extremos="plano"))
    assert abs(plano.area - L * 0.03) < 1e-9
    redondo = editor.forma_de(camino((-0.2, 0.1), (0.2, 0.1), extremos="redondo"))
    assert abs(redondo.area - (L * 0.03 + math.pi * 0.015 ** 2)) < 1e-5


def test_trazo_con_extremos_planos_es_el_rectangulo():
    """Un trazo recto de extremos planos es el rectángulo que dibujaría a mano: la misma
    planta (diferencia < 1e-12) y generado APROBADO."""
    rect = {"op": "unir", "anillos": [[[-0.3, 0.05], [0.3, 0.05], [0.3, 0.13], [-0.3, 0.13]]]}
    trazo = camino((-0.3, 0.09), (0.3, 0.09), ancho=0.08, extremos="plano")
    base = {"op": "unir", "anillos": [[[-0.2, -0.3], [0.2, -0.3], [0.2, 0.0], [-0.2, 0.0]]]}
    a, b = editor.planta([base, rect]), editor.planta([base, trazo])
    assert a.symmetric_difference(b).area < 1e-12


def test_sin_trazo_no_hay_camino_abierto():
    c = camino((0, 0), (0.2, 0))
    del c["trazo"]
    with pytest.raises(ValueError, match="necesita un trazo"):
        editor.forma_de(c)


def test_trazo_cerrado_centro_dentro_fuera():
    """Un cuadrado de lado 0,4 con trazo 0,02: centrado, un marco de 0,38 a 0,42; dentro,
    de 0,36 a 0,4; fuera, de 0,4 a 0,44 (uniones en inglete: esquinas vivas)."""
    cuadro = [(-0.2, -0.2), (0.2, -0.2), (0.2, 0.2), (-0.2, 0.2)]
    for pos, (a, b) in {"centro": (0.38, 0.42), "dentro": (0.36, 0.4), "fuera": (0.4, 0.44)}.items():
        g = editor.forma_de(camino(*cuadro, abierto=False, ancho=0.02, uniones="inglete", posicion=pos))
        assert abs(g.area - (b * b - a * a)) < 1e-9, pos


def test_contornear_un_trazo_curvo():
    """Contornear un trazo curvo da un relleno con curvas y la misma forma (IoU ≥ 0,999)."""
    c = camino((-0.3, 0), (0.3, 0), ancho=0.05)
    c["anillos"][0][0]["sal"], c["anillos"][0][1]["ent"] = [0.2, 0.3], [-0.2, 0.3]
    [r] = editor.contornear([c])
    hecho, antes = editor.forma_capa(r["anillos"]), editor.forma_de(c)
    assert iou(hecho, antes) >= 0.999
    assert any(n["ent"] or n["sal"] for a in r["anillos"] for n in a) and sum(map(len, r["anillos"])) < 40


def test_la_cuchilla_parte_el_esqueleto_de_un_trazo():
    """Un trazo recto cortado por la mitad: dos trazos abiertos de área L/2 · a (planos)."""
    c = camino((-0.2, 0), (0.2, 0), ancho=0.04, extremos="plano")
    r = editor.cortar([c], [[0.0, -0.3], [0.0, 0.3]])
    [corte] = r["cortes"]
    assert corte["abiertos"] == [True, True] and len(corte["piezas"]) == 2
    for poli in corte["piezas"]:
        assert abs(editor.forma_de({**c, "anillos": poli}).area - 0.2 * 0.04) < 1e-12
    # por el grosor pero sin cruzar el esqueleto: no corta y lo dice
    r = editor.cortar([c], [[-0.25, 0.01], [0.25, 0.015]])
    assert not r["cortes"] and r["sin_esqueleto"] == [1]


def test_engrosar_lo_necesario_aprueba_el_trazo_fino(salida):
    """Criterio de G2: el caso RECHAZADO de F5 (un trazo de 0,01) pasa a APROBADO con el
    menor d que aprueba (± 1e-4)."""
    cuadro = lambda x, y, w, h: {"op": "unir", "nombre": "c", "anillos": [[[x - w / 2, y - h / 2], [x + w / 2, y - h / 2],  # noqa: E731
                                                                          [x + w / 2, y + h / 2], [x - w / 2, y + h / 2]]]}
    capas = [cuadro(0, 0, 0.6, 0.6), {**cuadro(0, 0.4, 0.3, 0.01), "nombre": "fino"}]
    r = editor.engrosar_lo_necesario(capas, s.BISEL)
    d = r["d"]
    assert [c for c in r["capas"]] and len(r["capas"]) == 1  # solo la culpable
    nuevas = [capas[0], {**capas[1], "anillos": r["capas"][0]["anillos"]}]
    doc = {"version": 2, "capas": [], "ajustes": dict(editor.AJUSTES)}
    assert editor.generar("engrosado", doc, nuevas)["aprobado"]
    menos = [capas[0], {**capas[1], "anillos": [list(a.coords)[:-1] for a in [editor.forma_capa(capas[1]["anillos"]).buffer(
        d - 2e-4, join_style="mitre").exterior]]}]
    base = editor.planta(menos)
    assert s.area_perdida(base, editor.acabar(base, s.BISEL)) > s.PERDIDA_MAX  # con 2e-4 menos, no aprueba


TRAZOS_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">
  <line x1="20" y1="20" x2="180" y2="20" stroke="#000" stroke-width="8"/>
  <polyline points="20,50 100,80 180,50" fill="none" stroke="#000" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M40 90A60 60 0 0 1 160 90" fill="none" stroke="red" stroke-width="4" stroke-linecap="square"/>
</svg>"""


def test_importar_trazos_de_un_svg():
    """Criterio de G2: línea, polilínea y arco con sus extremos → capas de trazo con IoU ≥
    0,999 contra su dibujo exacto; exportadas e importadas otra vez, las mismas capas."""
    from shapely import affinity
    r = editor.importar("trazos.svg", TRAZOS_SVG)
    capas = r["doc"]["capas"]
    assert [c.get("abierto") for c in capas] == [True] * 3 and [c["trazo"]["extremos"] for c in capas] == ["plano", "redondo", "cuadrado"]
    arco = [(100 - 60 * math.cos(a), 90 - 60 * math.sin(a)) for a in (k * math.pi / 4000 for k in range(4001))]
    exacto = unary_union([LineString([(20, 20), (180, 20)]).buffer(4, cap_style="flat"),
                          LineString([(20, 50), (100, 80), (180, 50)]).buffer(3, quad_segs=256),
                          LineString(arco).buffer(2, cap_style="square", join_style="mitre")])
    m = r["marco"]
    exacto = affinity.scale(affinity.translate(exacto, -m["cx"], -m["cy"]), m["s"], -m["s"], origin=(0, 0))
    hecho = editor.planta(en_mundo(r["doc"]))
    assert iou(hecho, exacto) >= 0.999
    mundo = [{**c, "anillos": a} for c, a in zip(capas, (x["anillos"] for x in en_mundo(r["doc"])))]
    texto = editor.exportar_svg(mundo, None, [0.6, 0.05, 0.03, 1])
    assert texto.count('fill="none"') == 3 and "stroke-linecap" in texto
    vuelta = editor.importar("vuelta.svg", texto)["doc"]["capas"]
    assert [(c.get("abierto"), c["trazo"]["extremos"]) for c in vuelta] == [(c.get("abierto"), c["trazo"]["extremos"]) for c in capas]
    # el grosor, a una parte en 1e-4: la vuelta reescala por la caja, que el redondeo de la
    # exportación (milésimas con 3 decimales) mueve un poco
    assert all(abs(v["trazo"]["ancho"] / c["trazo"]["ancho"] - 1) < 1e-4 for v, c in zip(vuelta, capas))


def test_trazo_con_escala_no_uniforme_se_contornea():
    """Con transform="scale(2 1)" el grosor variaría: el importador lo contornea."""
    capas, _ = editor.leer_svg.leer('<svg xmlns="http://www.w3.org/2000/svg"><g transform="scale(2 1)">'
                                    '<circle cx="50" cy="50" r="40" fill="none" stroke="#000" stroke-width="10"/></g></svg>')
    assert len(capas) == 1 and "trazo" not in capas[0] and len(capas[0]["anillos"]) == 2  # un anillo con su hueco


def test_los_extremos_de_un_camino_son_objetivos_del_iman():
    c = camino((-0.2, 0), (0.1, 0.05), (0.2, 0.3))
    extremos = [(a, b) for a, b, _ in editor.bordes_rectos([c]) if a == b]
    assert extremos == [([-0.2, 0], [-0.2, 0]), ([0.2, 0.3], [0.2, 0.3])]


# ---------- G4: booleanas y aplanar
@pytest.mark.parametrize("op, fn", [("unir", "union"), ("restar", "difference"), ("intersecar", "intersection"),
                                    ("excluir", "symmetric_difference")])
def test_cada_operacion_es_la_de_shapely(op, fn):
    """Criterio de G4: la planta con cada operación coincide con shapely sobre las mismas formas."""
    a = {"op": "unir", "anillos": [[[-0.3, -0.2], [0.1, -0.2], [0.1, 0.2], [-0.3, 0.2]]]}
    b = {"op": op, "anillos": [[[-0.1, -0.1], [0.3, -0.1], [0.3, 0.3], [-0.1, 0.3]]]}
    esperado = getattr(editor.forma_de(a), fn)(editor.forma_de(b))
    assert editor.planta([a, b]).symmetric_difference(esperado).area < 1e-9


def test_booleana_de_varias_capas():
    cuadro = lambda x: {"op": "restar", "anillos": [[[x, 0], [x + 0.2, 0], [x + 0.2, 0.2], [x, 0.2]]]}  # noqa: E731
    capas = [cuadro(0), cuadro(0.1), cuadro(0.15)]  # la op de cada una no cuenta
    area = lambda op: editor.forma_capa(editor.booleana(capas, op)).area  # noqa: E731
    assert abs(area("unir") - 0.35 * 0.2) < 1e-6 and abs(area("intersecar") - 0.05 * 0.2) < 1e-6
    assert abs(area("restar") - 0.1 * 0.2) < 1e-6 and abs(area("excluir") - (0.1 + 0.05 + 0.05) * 0.2) < 1e-6


def test_aplanar_shou_cruz_cortado_sigue_aprobado(salida):
    """Criterio de G4: aplanar las piezas de shou-cruz cortadas con las 40 sugerencias y
    generarlo sigue APROBADO con el verificador, con ≤ 1,2 × los nodos del símbolo sin cortar."""
    import itertools
    doc = editor.piezas_curvas("shou-cruz")
    capas = [{**c, "id": i + 1} for i, c in enumerate(en_mundo(doc))]
    sig = itertools.count(100)
    for linea in editor.sugerencias(capas):
        aplicar(capas, linea, sig)
    assert len(capas) >= 20
    anillos = editor.aplanar(capas)
    nodos = lambda a: sum(map(len, a))  # noqa: E731
    assert nodos(anillos) <= 1.2 * nodos([a for c in doc["capas"] for a in c["anillos"]]), nodos(anillos)
    plana = [{"op": "unir", "anillos": anillos}]
    editor.generar("aplanado", doc, plana)
    codigo, v = verificar(salida / "glb" / "aplanado.glb", RAIZ / "fuentes" / "shou-cruz.png")
    assert codigo == 0 and v["aprobado"], v


# ---------- G5: grupos
@pytest.mark.parametrize("nombre", SIMBOLOS[:6])
def test_meter_todo_en_un_grupo_no_cambia_la_planta(nombre):
    """Criterio de G5 (regla 9): los símbolos de la galería, con todas sus capas dentro de
    un grupo normal, dan la misma planta (diferencia simétrica < 1e-12)."""
    capas = en_mundo(editor.piezas_curvas(nombre))
    agrupadas = [{**c, "grupo": 1} for c in capas]
    grupos = [{"id": 1, "nombre": "Todo", "op": "unir", "visible": True}]
    a, b = editor.planta(capas), editor.planta(agrupadas, None, grupos)
    assert a.symmetric_difference(b).area < 1e-12


def test_grupo_booleano_restar_es_restar_las_capas():
    """Un grupo booleano «restar» da lo mismo que las capas sueltas con «restar» (sin nada
    debajo); con una capa debajo, el grupo solo resta dentro de sí."""
    cuadro = lambda x, op="unir", **k: {"op": op, "anillos": [[[x, 0], [x + 0.3, 0], [x + 0.3, 0.3], [x, 0.3]]], **k}  # noqa: E731
    sueltas = [cuadro(0), cuadro(0.1, "restar"), cuadro(0.2, "restar")]
    grupo = [cuadro(0, grupo=5), cuadro(0.1, grupo=5), cuadro(0.2, grupo=5)]
    g = [{"id": 5, "op": "unir", "booleana": "restar", "visible": True}]
    assert editor.planta(sueltas).symmetric_difference(editor.planta(grupo, None, g)).area < 1e-12
    debajo = [cuadro(-0.2)] + grupo  # la capa de abajo no la toca la resta del grupo
    assert abs(editor.planta(debajo, None, g).area - (0.3 * 0.3 + 0.1 * 0.3 - 0.1 * 0.3)) < 1e-9


def test_grupos_anidados_y_el_sitio_de_un_grupo():
    """Un grupo ocupa el sitio de su capa más baja: un grupo que interseca, con una capa
    encima fuera de él que une, deja esa capa entera."""
    cuadro = lambda x, y, w, op="unir", **k: {"op": op, "anillos": [[[x, y], [x + w, y], [x + w, y + w], [x, y + w]]], **k}  # noqa: E731
    capas = [cuadro(0, 0, 0.4), cuadro(0.2, 0.2, 0.4, grupo=2), cuadro(0.3, 0.3, 0.05, grupo=3), cuadro(0.9, 0, 0.1)]
    grupos = [{"id": 2, "op": "intersecar", "visible": True}, {"id": 3, "op": "unir", "grupo": 2, "visible": True}]
    # grupo 2 = cuadro 0,2..0,6 ∪ (grupo 3: cuadrito) → interseca con el de abajo (0..0,4): 0,2 × 0,2
    assert abs(editor.planta(capas, None, grupos).area - (0.2 * 0.2 + 0.1 * 0.1)) < 1e-9


# ---------- G6: esquinas y curvar
def test_radio_de_esquina_da_el_area_del_cuadrado_redondeado():
    """Criterio de G6: radio 0,05 en las cuatro esquinas de un cuadrado de lado 0,4 da
    0,16 − (4 − π) · 0,05². Tolerancia 5e-6 y no 1e-6: un cuarto de círculo en cúbica (el
    de Figma y SVG) abomba 2,7e-4 del radio, y con cuatro de radio 0,05 eso son 2,2e-6 de
    área de más. Se mide la curva aplanada muy fina: el aplanado del servidor (1e-4, hacia
    dentro) quita 1,3e-5 más, como en cualquier curva del editor."""
    sq = [{"p": p, "ent": None, "sal": None, "radio": 0.05} for p in ([-0.2, -0.2], [0.2, -0.2], [0.2, 0.2], [-0.2, 0.2])]
    r = editor.curvas.redondear(sq)
    assert len(r) == 8
    assert abs(Polygon(editor.curvas.aplanar(r, 1e-9)).area - (0.16 - (4 - math.pi) * 0.05 ** 2)) < 5e-6
    assert abs(editor.forma_de({"op": "unir", "anillos": [sq]}).area - (0.16 - (4 - math.pi) * 0.05 ** 2)) < 2e-5


def test_radio_limitado_en_un_triangulo_agudo():
    """Un radio enorme en un triángulo muy agudo se limita a la mitad del tramo más corto y
    la forma sigue válida (como Figma)."""
    tri = [{"p": p, "ent": None, "sal": None, "radio": 1.0} for p in ([0, 0], [0.4, 0.02], [0.4, -0.02])]
    g = editor.forma_de({"op": "unir", "anillos": [tri]})
    assert g.is_valid and 0 < g.area < 0.4 * 0.04 / 2


def test_radio_en_un_trazo_cerrado():
    sq = [{"p": p, "ent": None, "sal": None, "radio": 0.05} for p in ([-0.2, -0.2], [0.2, -0.2], [0.2, 0.2], [-0.2, 0.2])]
    c = {"op": "unir", "anillos": [sq], "trazo": {**editor.TRAZO, "ancho": 0.02}}
    sin = {**c, "anillos": [[{k: v for k, v in n.items() if k != "radio"} for n in sq]]}
    assert editor.forma_de(c).area < editor.forma_de(sin).area  # las esquinas del marco, redondeadas


def test_redondear_es_la_misma_en_el_navegador():
    """Paridad (< 1e-12): redondear() de editor.html y la de tools/curvas.py."""
    import re
    fuente = re.search(r"function redondear\(.*?\n}\n", (RAIZ / "editor.html").read_text(), re.S).group(0)
    anillos = [[{"p": p, "ent": None, "sal": None, "tipo": "vivo", "radio": r} for p, r in
                (([-0.2, -0.2], 0.05), ([0.3, -0.1], 0.2), ([0.25, 0.3], 0.01), ([-0.3, 0.2], 0))]]
    js = fuente + f"console.log(JSON.stringify({json.dumps(anillos)}.map((a) => redondear(a))));"
    r = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    py = [editor.curvas.redondear(a) for a in anillos]
    plano = lambda x: [v for a in x for n in a for k in ("p", "ent", "sal") if n[k] for v in n[k]]  # noqa: E731
    assert len(plano(r)) == len(plano(py)) and max(abs(a - b) for a, b in zip(plano(r), plano(py))) < 1e-12


# ---------- G7: lápiz
def test_lapiz_de_300_puntos_llega_con_pocos_nodos():
    """Criterio de G7: un trazo de lápiz de 300 puntos (con temblor) llega con ≤ 30 nodos y
    a menos de 0,002 del dibujo, abierto y empezando y acabando en sus extremos."""
    import random
    random.seed(7)
    pts = [(t * 0.6 - 0.3, 0.15 * math.sin(t * 7) + 0.0005 * random.uniform(-1, 1)) for t in (k / 299 for k in range(300))]
    nodos = editor.curvas.ajustar_anillo(pts, 0.002, cerrado=False)[0]
    linea = LineString(editor.curvas.aplanar(nodos, cerrado=False))
    assert len(nodos) <= 30 and max(linea.distance(Point(p)) for p in pts) < 0.002
    assert nodos[0]["p"] == list(pts[0]) and math.dist(nodos[-1]["p"], pts[-1]) < 1e-12


# ---------- G8: texto
FUENTE_PRUEBA = next((f for f in ["/System/Library/Fonts/Hiragino Sans GB.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
                      if Path(f).exists()), None)


@pytest.mark.skipif(FUENTE_PRUEBA is None, reason="sin Hiragino ni DejaVu")
def test_texto_llega_con_los_nodos_exactos_de_la_fuente():
    """Criterio de G8: el texto sale de los glifos como nodos (cuadráticas pasadas a cúbicas
    sin pérdida): aplanado muy fino coincide con letras.py a 256 pasos por curva (IoU ≥
    0,99999). Frente a letras.py tal cual (16 pasos por curva, lo que aproxima él) el IoU
    se queda en ~0,9998. Y nunca hay más nodos que puntos tiene el glifo."""
    import letras
    from fontTools.ttLib import TTFont
    texto = "福" if "Hiragino" in FUENTE_PRUEBA else "AMOR"
    fuente = TTFont(FUENTE_PRUEBA, fontNumber=2 if FUENTE_PRUEBA.endswith(".ttc") else 0)
    capas = editor.texto_a_capas(texto, FUENTE_PRUEBA, 2 if FUENTE_PRUEBA.endswith(".ttc") else 0)
    fino = unary_union([editor.forma_capa([editor.curvas.aplanar(a, 1e-7) for a in c["anillos"]]) if c["op"] == "unir" else Polygon()
                        for c in capas])
    letras.PASOS_CURVA = 256
    try:
        ref = unary_union(letras.componer(texto, fuente, 0.02))
    finally:
        letras.PASOS_CURVA = 16
    assert iou(fino, ref) >= 0.99999
    gs, cmap = fuente.getGlyphSet(), fuente.getBestCmap()
    puntos = sum(len(fuente["glyf"][cmap[ord(ch)]].getCoordinates(fuente["glyf"])[0]) for ch in texto) if "glyf" in fuente else math.inf
    assert sum(len(a) for c in capas for a in c["anillos"]) <= puntos


# ---------- G9: historial y versiones con nombre
def test_version_con_nombre_sobrevive_al_recorte(salida, monkeypatch):
    """Criterio de G9: una versión con nombre sobrevive a 30 guardados (el recorte deja 20
    copias normales y no la toca); el historial la lista con su título."""
    monkeypatch.setattr(editor, "CADA_COPIA", 0)
    doc = editor.piezas_curvas("xi-doble")
    editor.guardar("versiones", doc)
    archivo, x0 = editor.guardar_version("versiones", doc, "Antes de cortar"), doc["capas"][0]["t"]["x"]
    for i in range(30):
        doc["capas"][0]["t"]["x"] = i * 0.001
        editor.guardar("versiones", doc)
    copias = editor.historial("versiones")
    con_nombre = [c for c in copias if c["titulo"]]
    assert len(copias) - len(con_nombre) == editor.COPIAS and [c["archivo"] for c in con_nombre] == [archivo]
    assert con_nombre[0]["titulo"] == "antes de cortar"
    assert editor.leer_copia("versiones", archivo)["capas"][0]["t"]["x"] == x0
    with pytest.raises(ValueError):
        editor.leer_copia("versiones", "../../x.json")


# ---------- G11: simetría rotacional
@pytest.mark.parametrize("n, espejo", [(4, False), (5, False), (6, True)])
def test_simetria_rotacional_es_invariante_al_giro(n, espejo):
    """La planta con simetría de orden n no cambia al girarla 360°/n (< 1e-9), y un anillo
    alrededor del centro sale en una pieza (las n copias se funden sin rendija)."""
    from shapely import affinity
    capas = [{"op": "unir", "anillos": [[[-0.05, 0], [0.05, 0], [0.08, 0.45], [-0.02, 0.4]]]},
             {"op": "unir", "anillos": [[[0.1, 0.1], [0.2, 0.12], [0.15, 0.25]]]}]
    g = editor.planta(capas, {"rot": n, "espejo": espejo})
    assert g.symmetric_difference(affinity.rotate(g, 360 / n, origin=(0, 0))).area < 1e-9
    anillo = [{"op": "unir", "anillos": [list(Point(0, 0).buffer(0.3, quad_segs=32).exterior.coords)[:-1],
                                         list(Point(0.01, 0).buffer(0.2, quad_segs=32).exterior.coords)[:-1]]}]
    a = editor.planta(anillo, {"rot": n, "espejo": espejo})
    assert len(s.lista(a)) == 1 and len(s.lista(a)[0].interiors) == 1


def test_shou_circular_con_simetria_de_orden_2_sigue_aprobado(salida):
    """shou-circular es simétrico al girarlo 180° (no 90°: IoU 0,80); con simetría
    rotacional de orden 2 generado sigue APROBADO por el verificador."""
    doc = editor.piezas_curvas("shou-circular")
    doc["simetria"] = {"rot": 2}
    editor.generar("shou-rot2", doc, en_mundo(doc))
    codigo, v = verificar(salida / "glb" / "shou-rot2.glb", RAIZ / "fuentes" / "shou-circular.png")
    assert codigo == 0 and v["aprobado"], v


def test_simetria_rotacional_no_pierde_piezas():
    """Seis pétalos sueltos (orden 6): seis piezas y seis veces el área del pétalo. Con el
    buffer(±1e-9) en inglete que había al principio, GEOS perdía dos."""
    t, co, si = (0.02, 0.3), math.cos(0.2), math.sin(0.2)
    w = [[t[0] + co * u - si * v, t[1] + si * u + co * v] for u, v in [[-0.05, -0.12], [0.05, -0.12], [0.03, 0.12], [-0.04, 0.1]]]
    capas = [{"op": "unir", "anillos": [w]}]
    g = editor.planta(capas, {"rot": 6})
    assert len(s.lista(g)) == 6 and abs(g.area - 6 * editor.forma_capa([w]).area) < 1e-9
