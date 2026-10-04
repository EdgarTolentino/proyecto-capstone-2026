"""Nivel 1 (#31): mAP con pycocotools y precisión y recall al umbral de la regla."""

from __future__ import annotations

import pytest
from gepp_vision.evaluacion.coco import ArchivoCoco, CajaPx
from gepp_vision.evaluacion.deteccion import (
    MAX_DETS,
    MetricasClase,
    MetricasRegion,
    evaluar,
    evaluar_regiones,
)

HD = (1920, 1080)
UNA = {"a.jpg": HD}


def _v(clase: str, x: float, y: float, ancho: float, alto: float, archivo: str = "a.jpg") -> CajaPx:
    return CajaPx(archivo, clase, x, y, ancho, alto)


def _p(
    clase: str,
    x: float,
    y: float,
    ancho: float,
    alto: float,
    score: float = 0.9,
    archivo: str = "a.jpg",
) -> CajaPx:
    return CajaPx(archivo, clase, x, y, ancho, alto, score)


def _clase(m: MetricasRegion, nombre: str) -> MetricasClase:
    return next(c for c in m.clases if c.clase == nombre)


def test_prediccion_identica_a_la_verdad_da_uno() -> None:
    verdad = [_v("persona", 0, 0, 50, 100), _v("persona", 500, 0, 50, 100)]
    m = evaluar(verdad, [_p(c.clase, c.x, c.y, c.ancho, c.alto) for c in verdad], UNA)
    p = _clase(m, "persona")
    assert (p.map50, p.map50_95, p.precision, p.recall) == (1.0, 1.0, 1.0, 1.0)
    assert m.map50 == m.map50_95 == 1.0


def test_sin_predicciones_da_cero_sin_pasar_por_cocoeval() -> None:
    # pycocotools se cae con loadRes([]): esta ruta no debe llegar ahí.
    m = evaluar([_v("persona", 0, 0, 50, 100)], [], UNA)
    p = _clase(m, "persona")
    assert (p.map50, p.map50_95, p.recall, p.precision) == (0.0, 0.0, 0.0, None)
    assert m.map50_95 == 0.0


def test_una_de_mas_y_una_de_menos() -> None:
    verdad = [_v("persona", 0, 0, 50, 100), _v("persona", 500, 0, 50, 100)]
    predichas = [_p("persona", 0, 0, 50, 100), _p("persona", 1000, 0, 50, 100)]
    p = _clase(evaluar(verdad, predichas, UNA), "persona")
    assert (p.n_verdad, p.n_predichas, p.precision, p.recall) == (2, 2, 0.5, 0.5)


def test_imagen_sin_verdad_con_prediccion_cuenta_como_falso_positivo() -> None:
    dos = {"a.jpg": HD, "b.jpg": HD}
    # La falsa va con más confianza: con empate, COCO ordena primero la de a.jpg y da 1,0.
    predichas = [
        _p("persona", 0, 0, 50, 100, 0.75),
        _p("persona", 0, 0, 50, 100, 0.875, archivo="b.jpg"),
    ]
    m = evaluar([_v("persona", 0, 0, 50, 100)], predichas, dos)
    p = _clase(m, "persona")
    assert (p.precision, p.recall) == (0.5, 1.0)
    assert p.map50 == 0.5  # al recall 1 la precisión es 1/2, y así en toda la curva


@pytest.mark.parametrize(("alto_predicho", "empareja"), [(10.0, True), (9.9, False)])
def test_iou_justo_en_cero_coma_cinco_empareja(alto_predicho: float, empareja: bool) -> None:
    # Verdad 20x10 (200 px²) y predicción 10x10 en la misma esquina: IoU = 100/200 = 0,5.
    m = evaluar([_v("persona", 0, 0, 20, 10)], [_p("persona", 0, 0, 10, alto_predicho)], UNA)
    assert _clase(m, "persona").recall == (1.0 if empareja else 0.0)


@pytest.mark.parametrize(
    ("score", "umbral", "cuenta"),
    [(0.45, 0.45, True), (0.5, 0.5, True), (0.25, 0.5, False), (0.75, 0.5, True)],
)
def test_umbral_de_confianza(score: float, umbral: float, cuenta: bool) -> None:
    m = evaluar([_v("persona", 0, 0, 50, 100)], [_p("persona", 0, 0, 50, 100, score)], UNA, umbral)
    assert _clase(m, "persona").n_predichas == (1 if cuenta else 0)


@pytest.mark.parametrize("umbral", [0.0, 1.5])
def test_umbral_fuera_de_rango_detiene(umbral: float) -> None:
    with pytest.raises(ValueError, match="umbral"):
        evaluar([], [], UNA, umbral)


def test_max_dets_no_pierde_las_predicciones_sobre_cien() -> None:
    # Con el maxDets de COCO (100), 150 cajas perfectas dan mAP50 0,66 (comprobado el 4-oct).
    verdad = [_v("persona", (i % 15) * 120, (i // 15) * 100, 30, 60) for i in range(150)]
    m = evaluar(verdad, [_p(c.clase, c.x, c.y, c.ancho, c.alto) for c in verdad], UNA)
    assert MAX_DETS >= 150
    assert m.max_predicciones == 150
    assert _clase(m, "persona").map50 == 1.0


def test_clase_sin_verdad_no_tiene_map_y_con_verdad_sin_prediccion_da_cero() -> None:
    verdad = [_v("persona", 0, 0, 50, 100), _v("casco", 500, 0, 20, 20)]
    m = evaluar(verdad, [_p("persona", 0, 0, 50, 100)], UNA)
    assert _clase(m, "chaleco").map50_95 is None
    assert _clase(m, "casco").map50_95 == 0.0
    # persona 1 y casco 0; chaleco no entra al promedio. approx: COCO divide con un epsilon.
    assert m.map50_95 == pytest.approx(0.5)


def test_una_caja_chica_cuenta_solo_en_chico() -> None:
    m = evaluar([_v("casco", 100, 100, 20, 20)], [_p("casco", 100, 100, 20, 20)], UNA)
    por_tamano = _clase(m, "casco").map50_95_por_tamano
    # approx: COCO divide con un epsilon y el promedio sale 0,9999999999999998.
    assert por_tamano == {
        "todos": pytest.approx(1.0),
        "chico": pytest.approx(1.0),
        "mediano": None,
        "grande": None,
    }


@pytest.mark.parametrize(
    "predichas", [[], [_p("persona", 1000, 0, 50, 100)]], ids=["sin", "con-otra-clase"]
)
def test_el_borde_de_area_cuenta_en_los_dos_rangos_con_y_sin_predicciones(
    predichas: list[CajaPx],
) -> None:
    # 32x32 = 1024 px²: pycocotools lo cuenta como chico y como mediano. La ruta sin
    # predicciones (sin COCOeval) tiene que dar lo mismo que la que sí pasa por COCOeval.
    m = evaluar([_v("casco", 100, 100, 32, 32)], predichas, UNA)
    assert _clase(m, "casco").map50_95_por_tamano == {
        "todos": 0.0,
        "chico": 0.0,
        "mediano": 0.0,
        "grande": None,
    }


def test_dentro_y_fuera_se_evaluan_por_separado_sobre_las_mismas_imagenes() -> None:
    recorte = (0.0, 0.0, 960.0, 540.0)
    verdad = ArchivoCoco(
        {"a.jpg": HD, "b.jpg": HD},
        (_v("persona", 100, 100, 50, 100), _v("persona", 1500, 800, 50, 100, archivo="b.jpg")),
        "",
    )
    predichas = ArchivoCoco(
        {"a.jpg": HD, "b.jpg": HD, "c.jpg": HD},
        (_p("persona", 100, 100, 50, 100), _p("persona", 100, 100, 50, 100, archivo="c.jpg")),
        "modelo",
    )
    r = evaluar_regiones(verdad, predichas, ["a.jpg", "b.jpg"], recorte)
    assert _clase(r["dentro"], "persona").recall == 1.0
    assert _clase(r["dentro"], "persona").n_predichas == 1  # c.jpg no se evalúa
    assert _clase(r["fuera"], "persona").recall == 0.0
    # Con --imagenes-de solo entra a.jpg: la caja verdadera de b.jpg no se cuenta.
    solo_a = evaluar_regiones(verdad, predichas, ["a.jpg"], recorte)
    assert _clase(solo_a["fuera"], "persona").n_verdad == 0
