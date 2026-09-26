"""Pruebas del servidor del editor y de simbolo.exportar().  Uso: .venv/bin/pytest tests/

Todo se escribe en carpetas temporales (tmp_path): glb/, svg/ y editor/ no se tocan.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import trimesh
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
    return [{"op": c["op"], "anillos": [[[x + c["t"]["x"], y + c["t"]["y"]] for x, y in a] for a in c["anillos"]]}
            for c in doc["capas"]]


def verificar(glb, fuente):
    r = subprocess.run([sys.executable, str(RAIZ / "tools/verificar.py"), str(glb), str(fuente)],
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("nombre", SIMBOLOS)
def test_ida_y_vuelta_sigue_aprobado(nombre, salida):
    """Abrir un símbolo aprobado en el editor y generarlo sin tocar: el verificador lo aprueba."""
    fuente = RAIZ / "fuentes" / f"{nombre}.png"
    if not fuente.exists():  # shou-sello y xi-doble no se publican (marca de agua)
        pytest.skip(f"falta {fuente.name}")
    doc = editor.piezas_svg(nombre)
    info = editor.generar(f"{nombre}-prueba", doc, en_mundo(doc))
    assert info["estanca"]
    codigo, r = verificar(salida / "glb" / f"{nombre}-prueba.glb", fuente)
    assert codigo == 0 and r["aprobado"], r


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
