"""Unión de datasets públicos para entrenar (PT-08, #31).

Lo que se cuida aquí es lo que, si falla, no avisa: una clase mal traducida, una persona
sin etiquetar que el modelo aprende como fondo, o una imagen repetida entre entrenamiento y
validación que infla la métrica.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from gepp_core import Caja, ClaseDetectada
from gepp_vision.dataset import UMBRAL_DUPLICADO, Particion
from gepp_vision.entrenamiento import (
    CLASES_V1,
    CategoriaDesconocida,
    Fuente,
    a_coco,
    cargar_fuentes,
    completar,
    desde_coco,
    desde_voc,
    particion_estable,
    quitar_fugas,
)

P, C, V = ClaseDetectada.PERSONA, ClaseDetectada.CASCO, ClaseDetectada.CHALECO

FUENTE = Fuente(
    nombre="css",
    licencia="CC BY 4.0",
    clases={"Hardhat": C, "Safety Vest": V, "Person": P, "NO-Hardhat": None},
    exhaustivas=frozenset({C, V}),
)


def _coco(*anotaciones: tuple[int, list[float]], categorias: dict[int, str] | None = None) -> dict:
    cats = categorias or {
        0: "workers",
        1: "Hardhat",
        2: "NO-Hardhat",
        3: "Person",
        4: "Safety Vest",
    }
    return {
        "images": [{"id": 7, "file_name": "a.jpg", "width": 200, "height": 100}],
        "categories": [{"id": i, "name": n} for i, n in cats.items()],
        "annotations": [
            {"id": k, "image_id": 7, "category_id": cat, "bbox": bbox}
            for k, (cat, bbox) in enumerate(anotaciones)
        ],
    }


# --- traducción de clases -------------------------------------------------------------


def test_traduce_las_clases_y_normaliza_las_cajas() -> None:
    [img] = desde_coco(_coco((1, [20, 10, 40, 30]), (4, [0, 0, 200, 100])), FUENTE)
    assert img.archivo == "a.jpg"
    assert img.cajas == [(C, Caja(0.1, 0.1, 0.3, 0.4)), (V, Caja(0.0, 0.0, 1.0, 1.0))]


def test_una_clase_mapeada_a_nada_se_descarta_a_proposito() -> None:
    [img] = desde_coco(_coco((2, [20, 10, 40, 30])), FUENTE)
    assert img.cajas == []


def test_una_categoria_que_la_fuente_no_declara_detiene_todo() -> None:
    coco = _coco((1, [0, 0, 10, 10]), (5, [0, 0, 10, 10]), categorias={1: "Hardhat", 5: "Mask"})
    with pytest.raises(CategoriaDesconocida, match="Mask"):
        desde_coco(coco, FUENTE)


def test_una_categoria_agrupadora_sin_anotaciones_no_cuenta_como_desconocida() -> None:
    # Roboflow exporta la categoría 0 ("workers") como padre de las demás, sin cajas.
    [img] = desde_coco(_coco((1, [20, 10, 40, 30])), FUENTE)
    assert len(img.cajas) == 1


@pytest.mark.parametrize("bbox", [[10, 10, 0, 5], [10, 10, 5, 0], [250, 10, 5, 5]])
def test_las_cajas_vacias_o_fuera_del_cuadro_se_descartan(bbox: list[float]) -> None:
    [img] = desde_coco(_coco((1, bbox)), FUENTE)
    assert img.cajas == []


def test_una_caja_que_se_sale_del_cuadro_se_recorta_al_borde() -> None:
    [img] = desde_coco(_coco((1, [180, 90, 40, 30])), FUENTE)
    assert img.cajas == [(C, Caja(0.9, 0.9, 1.0, 1.0))]


VOC = """<annotation><filename>h1.png</filename><size><width>400</width><height>200</height>
<depth>3</depth></size>
<object><name>helmet</name><bndbox><xmin>40</xmin><ymin>20</ymin><xmax>80</xmax><ymax>60</ymax>
</bndbox></object>
<object><name>head</name><bndbox><xmin>0</xmin><ymin>0</ymin><xmax>10</xmax><ymax>10</ymax>
</bndbox></object></annotation>"""


def test_voc_se_traduce_igual_que_coco() -> None:
    fuente = Fuente("hhd", "CC0 1.0", {"helmet": C, "head": None, "person": P}, frozenset({C}))
    img = desde_voc(VOC, fuente)
    assert img.archivo == "h1.png"
    assert (img.ancho, img.alto) == (400, 200)
    assert img.cajas == [(C, Caja(0.1, 0.1, 0.2, 0.3))]


def test_voc_con_una_clase_no_declarada_detiene_todo() -> None:
    fuente = Fuente("hhd", "CC0 1.0", {"helmet": C}, frozenset({C}))
    with pytest.raises(CategoriaDesconocida, match="head"):
        desde_voc(VOC, fuente)


# --- archivo de fuentes ---------------------------------------------------------------


def test_el_archivo_de_fuentes_del_repo_es_valido() -> None:
    fuentes = cargar_fuentes(Path(__file__).resolve().parents[1] / "scripts/fuentes.yaml")
    assert fuentes, "sin fuentes no hay entrenamiento"
    for f in fuentes:
        assert f.licencia, f"{f.nombre} sin licencia: no entra (07-datasets)"
        assert set(f.clases.values()) - {None} <= set(CLASES_V1)


def test_una_clase_propia_inexistente_en_el_archivo_falla(tmp_path: Path) -> None:
    ruta = tmp_path / "f.yaml"
    ruta.write_text(
        "fuentes:\n  - nombre: x\n    licencia: CC0\n    origen: {}\n"
        "    clases: {helmet: kasco}\n    exhaustivas: []\n"
    )
    with pytest.raises(ValueError, match="kasco"):
        cargar_fuentes(ruta)


# --- completar personas ---------------------------------------------------------------


def test_completar_agrega_solo_las_propuestas_que_no_estan_ya_etiquetadas() -> None:
    existente = Caja(0.0, 0.0, 0.5, 0.5)
    ya_esta = Caja(0.01, 0.01, 0.5, 0.5)  # IoU ~0,96 con la existente
    nueva = Caja(0.6, 0.6, 0.9, 0.9)
    assert completar([existente], [ya_esta, nueva]) == [nueva]


@pytest.mark.parametrize(
    ("desplazamiento", "se_agrega"),
    # Valores diádicos: el IoU sale exacto en coma flotante (1; 0,5; 0,2).
    [(0.0, False), (0.25, False), (0.5, True)],
)
def test_completar_en_el_umbral_de_solapamiento(desplazamiento: float, se_agrega: bool) -> None:
    existente = Caja(0.0, 0.0, 0.75, 0.5)
    propuesta = Caja(desplazamiento, 0.0, 0.75 + desplazamiento, 0.5)
    assert (completar([existente], [propuesta]) == [propuesta]) is se_agrega


def test_completar_sin_nada_previo_agrega_todo() -> None:
    propuestas = [Caja(0.1, 0.1, 0.2, 0.2), Caja(0.5, 0.5, 0.7, 0.9)]
    assert completar([], propuestas) == propuestas


# --- fugas entre particiones ----------------------------------------------------------


E, VA, PR = Particion.ENTRENAMIENTO, Particion.VALIDACION, Particion.PRUEBA


def test_una_imagen_de_entrenamiento_casi_igual_a_una_de_validacion_se_va() -> None:
    hashes = [0b1111, 0b1110, 0xFFFF_FFFF_0000_0000]  # el tercero, a 30+ bits de los otros
    assert quitar_fugas(hashes, [E, VA, E]) == {0}


def test_entre_validacion_y_prueba_cede_validacion() -> None:
    assert quitar_fugas([0b1111, 0b1110], [VA, PR]) == {0}


def test_dos_casi_iguales_en_la_misma_particion_no_son_fuga() -> None:
    assert quitar_fugas([0b1111, 0b1110], [E, E]) == set()


@pytest.mark.parametrize(
    ("bits", "es_fuga"), [(UMBRAL_DUPLICADO, True), (UMBRAL_DUPLICADO + 1, False)]
)
def test_fuga_en_el_umbral_exacto(bits: int, es_fuga: bool) -> None:
    lejano = (1 << bits) - 1  # difiere de 0 en exactamente `bits` bits
    assert (quitar_fugas([0, lejano], [E, PR]) == {0}) is es_fuga


def test_fugas_con_hashes_de_64_bits_completos() -> None:
    alto = (1 << 64) - 1
    assert quitar_fugas([alto, alto ^ 1], [E, VA]) == {0}


# --- partición y salida ---------------------------------------------------------------


def test_la_particion_estable_no_depende_del_orden_ni_de_la_corrida() -> None:
    nombres = [f"img_{i}.jpg" for i in range(2000)]
    primera = [particion_estable(n) for n in nombres]
    assert primera == [particion_estable(n) for n in nombres]
    proporcion = {p: primera.count(p) / len(nombres) for p in Particion}
    assert 0.75 < proporcion[E] < 0.85
    assert 0.07 < proporcion[VA] < 0.13
    assert 0.07 < proporcion[PR] < 0.13


def test_a_coco_usa_las_tres_clases_v1_y_marca_lo_automatico() -> None:
    [img] = desde_coco(_coco((1, [20, 10, 40, 30])), FUENTE)
    coco = a_coco([(img, "css__a.jpg", [Caja(0.5, 0.5, 1.0, 1.0)])])
    assert [c["name"] for c in coco["categories"]] == ["persona", "casco", "chaleco"]
    casco, persona = coco["annotations"]
    assert casco["bbox"] == pytest.approx([20, 10, 40, 30])
    assert casco["category_id"] == CLASES_V1[C]
    assert casco["automatica"] is False
    assert persona["category_id"] == CLASES_V1[P]
    assert persona["automatica"] is True
    assert persona["area"] == pytest.approx(100 * 50)
    assert coco["images"] == [{"id": 1, "file_name": "css__a.jpg", "width": 200, "height": 100}]
