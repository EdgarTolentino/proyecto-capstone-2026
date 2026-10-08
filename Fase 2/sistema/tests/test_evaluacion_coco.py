"""Lectura de COCO 1.0 para evaluar (#31): imágenes por file_name, clases por nombre."""

from __future__ import annotations

from typing import Any

import pytest
from gepp_vision.evaluacion.coco import (
    CajaPx,
    EntradaInvalida,
    en_region,
    imagenes_comunes,
    leer_coco,
)

CATEGORIAS = {"persona": 1, "casco": 2, "chaleco": 3}
HD = (1920, 1080)


def _coco(
    cajas: list[tuple[str, str, list[float], float | None]],
    *,
    imagenes: dict[str, tuple[int, int]] | None = None,
    categorias: dict[str, int] | None = None,
) -> dict[str, Any]:
    imagenes = imagenes or {"a.jpg": HD}
    categorias = categorias or CATEGORIAS
    ids = {n: i for i, n in enumerate(imagenes, start=1)}
    anotaciones = []
    for n, (archivo, clase, bbox, score) in enumerate(cajas, start=1):
        a: dict[str, Any] = {
            "id": n,
            "image_id": ids[archivo],
            "category_id": categorias[clase],
            "bbox": bbox,
            "area": bbox[2] * bbox[3],
            "iscrowd": 0,
        }
        if score is not None:
            a["score"] = score
        anotaciones.append(a)
    return {
        "categories": [{"id": i, "name": c} for c, i in categorias.items()],
        "images": [
            {"id": ids[n], "file_name": n, "width": w, "height": h}
            for n, (w, h) in imagenes.items()
        ],
        "annotations": anotaciones,
    }


def test_las_clases_se_leen_por_nombre_no_por_id() -> None:
    # CVAT numera según el orden de las etiquetas del proyecto: aquí casco es el 1.
    d = _coco(
        [("a.jpg", "casco", [10, 10, 20, 20], None), ("a.jpg", "persona", [0, 0, 50, 100], None)],
        categorias={"casco": 1, "persona": 2, "chaleco": 3},
    )
    assert [c.clase for c in leer_coco(d, predicciones=False).cajas] == ["casco", "persona"]


def test_tiene_pequenos_se_ignora_y_otro_nombre_desconocido_detiene() -> None:
    # La exportación real de CVAT trae el tag en categories, sin cajas (4-oct).
    d = _coco([], categorias={**CATEGORIAS, "tiene_pequenos": 4})
    assert leer_coco(d, predicciones=False).cajas == ()
    with pytest.raises(EntradaInvalida, match="guante"):
        leer_coco(_coco([], categorias={"persona": 1, "guante": 2}), predicciones=False)


@pytest.mark.parametrize("etiqueta", ["tiene_pequenos", "negativo_duro", "grupo_denso"])
def test_cada_etiqueta_de_imagen_se_ignora_con_y_sin_anotaciones(etiqueta: str) -> None:
    categorias = {**CATEGORIAS, etiqueta: 4}
    sin_cajas = leer_coco(_coco([], categorias=categorias), predicciones=False)
    assert sin_cajas.cajas == ()
    # CVAT no la exporta con cajas, pero si una anotación la usara tampoco es una caja
    con_anotacion = _coco(
        [("a.jpg", "persona", [0, 0, 50, 100], None), ("a.jpg", etiqueta, [1, 1, 5, 5], None)],
        categorias=categorias,
    )
    assert [c.clase for c in leer_coco(con_anotacion, predicciones=False).cajas] == ["persona"]


def test_las_tres_etiquetas_de_imagen_juntas_no_afectan_la_lectura() -> None:
    con = _coco(
        [("a.jpg", "casco", [10, 10, 20, 20], None)],
        categorias={**CATEGORIAS, "tiene_pequenos": 4, "negativo_duro": 5, "grupo_denso": 6},
    )
    sin = _coco([("a.jpg", "casco", [10, 10, 20, 20], None)])
    assert leer_coco(con, predicciones=False) == leer_coco(sin, predicciones=False)


@pytest.mark.parametrize("nombre", ["arnes", "negativo_duro ", "Grupo_Denso", ""])
def test_un_nombre_parecido_a_una_etiqueta_de_imagen_sigue_deteniendo(nombre: str) -> None:
    with pytest.raises(EntradaInvalida, match="categoría desconocida"):
        leer_coco(_coco([], categorias={**CATEGORIAS, nombre: 4}), predicciones=False)


def test_prediccion_sin_score_detiene_y_la_verdad_descarta_el_score() -> None:
    sin_score = _coco([("a.jpg", "persona", [0, 0, 50, 100], None)])
    with pytest.raises(EntradaInvalida, match="score"):
        leer_coco(sin_score, predicciones=True)
    con_score = _coco([("a.jpg", "persona", [0, 0, 50, 100], 0.75)])
    assert leer_coco(con_score, predicciones=False).cajas[0].score is None
    assert leer_coco(con_score, predicciones=True).cajas[0].score == 0.75


def test_imagen_repetida_detiene() -> None:
    d = _coco([])
    d["images"].append({"id": 2, "file_name": "a.jpg", "width": 1920, "height": 1080})
    with pytest.raises(EntradaInvalida, match="repetida"):
        leer_coco(d, predicciones=False)


@pytest.mark.parametrize(("campo", "valor"), [("category_id", 9), ("image_id", 9)])
def test_anotacion_que_apunta_a_algo_que_no_existe_detiene(campo: str, valor: int) -> None:
    d = _coco([("a.jpg", "persona", [0, 0, 50, 100], None)])
    d["annotations"][0][campo] = valor
    with pytest.raises(EntradaInvalida):
        leer_coco(d, predicciones=False)


@pytest.mark.parametrize("bbox", [[0, 0, 0, 100], [0, 0, 50, 0]])
def test_caja_sin_area_detiene_con_el_archivo(bbox: list[float]) -> None:
    with pytest.raises(EntradaInvalida, match=r"a\.jpg"):
        leer_coco(_coco([("a.jpg", "persona", bbox, None)]), predicciones=False)


def test_imagenes_comunes_son_las_de_la_verdad_y_sobran_predicciones() -> None:
    verdad = leer_coco(_coco([], imagenes={"b.jpg": HD, "a.jpg": HD}), predicciones=False)
    predichas = leer_coco(
        _coco([], imagenes={"a.jpg": HD, "b.jpg": HD, "c.jpg": HD}), predicciones=True
    )
    assert imagenes_comunes(verdad, predichas) == ["a.jpg", "b.jpg"]
    assert imagenes_comunes(verdad, predichas, solo=["b.jpg"]) == ["b.jpg"]


@pytest.mark.parametrize(
    ("verdad", "predichas", "solo", "mensaje"),
    [
        ({"a.jpg": HD, "b.jpg": HD}, {"a.jpg": HD}, None, "predicciones"),
        ({"a.jpg": HD}, {"a.jpg": (960, 540)}, None, "tamaño"),
        ({"a.jpg": HD}, {"a.jpg": HD, "z.jpg": HD}, ["z.jpg"], "verdad"),
        ({"a.jpg": HD}, {"a.jpg": HD}, [], "ninguna"),
    ],
)
def test_imagenes_comunes_detiene(
    verdad: dict[str, tuple[int, int]],
    predichas: dict[str, tuple[int, int]],
    solo: list[str] | None,
    mensaje: str,
) -> None:
    v = leer_coco(_coco([], imagenes=verdad), predicciones=False)
    p = leer_coco(_coco([], imagenes=predichas), predicciones=True)
    with pytest.raises(EntradaInvalida, match=mensaje):
        imagenes_comunes(v, p, solo)


@pytest.mark.parametrize(
    ("en_el_borde", "medio_px_afuera"),
    [
        ((100.0, 150.0), (99.5, 150.0)),  # x1
        ((150.0, 100.0), (150.0, 99.5)),  # y1
        ((200.0, 150.0), (200.5, 150.0)),  # x2
        ((150.0, 200.0), (150.0, 200.5)),  # y2
    ],
    ids=["x1", "y1", "x2", "y2"],
)
def test_el_borde_del_recorte_es_de_adentro_y_cada_caja_va_a_un_solo_lado(
    en_el_borde: tuple[float, float], medio_px_afuera: tuple[float, float]
) -> None:
    recorte = (100.0, 100.0, 200.0, 200.0)

    def caja(centro: tuple[float, float]) -> CajaPx:  # 20x20 px con ese centro
        return CajaPx("a.jpg", "persona", centro[0] - 10.0, centro[1] - 10.0, 20.0, 20.0)

    borde, afuera = caja(en_el_borde), caja(medio_px_afuera)
    assert borde.centro == en_el_borde and afuera.centro == medio_px_afuera
    assert en_region([borde, afuera], recorte, dentro=True) == [borde]
    assert en_region([borde, afuera], recorte, dentro=False) == [afuera]


def test_iou_de_cajas_en_px() -> None:
    a = CajaPx("a.jpg", "persona", 0.0, 0.0, 20.0, 10.0)
    assert a.iou(CajaPx("a.jpg", "persona", 0.0, 0.0, 10.0, 10.0)) == 0.5
    assert a.iou(CajaPx("a.jpg", "persona", 100.0, 0.0, 10.0, 10.0)) == 0.0
