"""Pruebas del servidor del editor y de simbolo.exportar().  Uso: .venv/bin/pytest tests/

Todo se escribe en carpetas temporales (tmp_path): glb/, svg/ y editor/ no se tocan.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import trimesh

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


def test_historial_guarda_copias_y_se_limita(salida):
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
