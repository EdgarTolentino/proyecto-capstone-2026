"""Nivel 0 (#31): kappa de Cohen e IoU medio entre dos etiquetadores."""

from __future__ import annotations

import pytest
from gepp_vision.evaluacion.acuerdo import (
    KAPPA_MINIMO,
    SIN_CAJA,
    UMBRAL_IOU,
    acuerdo,
    bajo_el_minimo,
    emparejar_clases,
    imagenes_de_la_segunda,
    kappa_cohen,
)
from gepp_vision.evaluacion.coco import ArchivoCoco, CajaPx, EntradaInvalida

HD = (1920, 1080)


def _caja(
    clase: str, x: float, y: float, ancho: float, alto: float, archivo: str = "a.jpg"
) -> CajaPx:
    return CajaPx(archivo, clase, x, y, ancho, alto)


def _archivo(
    cajas: list[CajaPx], imagenes: dict[str, tuple[int, int]] | None = None
) -> ArchivoCoco:
    return ArchivoCoco(imagenes if imagenes is not None else {"a.jpg": HD}, tuple(cajas), "")


def test_kappa_con_acuerdo_total_es_uno() -> None:
    assert kappa_cohen([("persona", "persona"), ("casco", "casco")]) == 1.0


def test_kappa_con_acuerdo_igual_al_azar_es_cero() -> None:
    pares = [("persona", "persona"), ("persona", "casco"), ("casco", "persona"), ("casco", "casco")]
    assert kappa_cohen(pares) == 0.0


def test_kappa_con_una_tabla_calculada_a_mano() -> None:
    # 10 pares. Observado 7/10. Primera: persona 5, casco 4, sin caja 1. Segunda: persona 4,
    # casco 4, sin caja 1, chaleco 1. Azar = (5*4 + 4*4 + 1*1)/100 = 37/100.
    # Kappa = (70 - 37)/(100 - 37) = 33/63 = 11/21.
    pares = (
        [("persona", "persona")] * 4
        + [("persona", "casco")]
        + [("casco", "casco")] * 3
        + [("casco", SIN_CAJA)]
        + [(SIN_CAJA, "chaleco")]
    )
    assert kappa_cohen(pares) == pytest.approx(11 / 21)


@pytest.mark.parametrize(
    "pares", [[], [("persona", "persona")] * 3], ids=["vacio", "una-categoria"]
)
def test_kappa_indefinido(pares: list[tuple[str, str]]) -> None:
    assert kappa_cohen(pares) is None


@pytest.mark.parametrize(
    ("kappa", "alerta"), [(0.6875, True), (KAPPA_MINIMO, False), (0.75, False), (None, False)]
)
def test_la_alerta_salta_bajo_el_minimo(kappa: float | None, alerta: bool) -> None:
    assert bajo_el_minimo(kappa) is alerta


def test_las_cajas_se_emparejan_sin_mirar_la_clase() -> None:
    primera = _archivo([_caja("persona", 0, 0, 50, 100)])
    segunda = _archivo([_caja("casco", 0, 0, 50, 100)])
    assert emparejar_clases(primera, segunda, ["a.jpg"]) == [("persona", "casco", 1.0)]


def test_la_caja_que_marco_solo_uno_va_contra_sin_caja() -> None:
    primera = _archivo([_caja("persona", 0, 0, 50, 100), _caja("casco", 500, 0, 20, 20)])
    segunda = _archivo([_caja("persona", 0, 0, 50, 100), _caja("chaleco", 900, 0, 40, 40)])
    assert sorted(emparejar_clases(primera, segunda, ["a.jpg"]), key=str) == sorted(
        [("persona", "persona", 1.0), ("casco", SIN_CAJA, None), (SIN_CAJA, "chaleco", None)],
        key=str,
    )


def test_un_cuadro_que_una_persona_dejo_vacio_baja_el_acuerdo() -> None:
    primera = _archivo([_caja("persona", 0, 0, 50, 100), _caja("persona", 500, 0, 50, 100)])
    resultado = acuerdo(primera, _archivo([]))
    assert (resultado.pares, resultado.solo_primera, resultado.solo_segunda) == (0, 2, 0)
    assert resultado.matriz == {"persona": {SIN_CAJA: 2}}


@pytest.mark.parametrize(("alto", "empareja"), [(10.0, True), (9.9, False)])
def test_iou_justo_en_cero_coma_cinco_empareja(alto: float, empareja: bool) -> None:
    # 20x10 contra 10x10 en la misma esquina: IoU = 100/200 = 0,5.
    primera = _archivo([_caja("persona", 0, 0, 20, 10)])
    segunda = _archivo([_caja("persona", 0, 0, 10, alto)])
    resultado = acuerdo(primera, segunda)
    assert resultado.pares == (1 if empareja else 0)
    assert UMBRAL_IOU == 0.5


def test_iou_medio_de_los_pares() -> None:
    primera = _archivo([_caja("persona", 0, 0, 20, 10), _caja("casco", 500, 0, 20, 20)])
    segunda = _archivo([_caja("persona", 0, 0, 10, 10), _caja("casco", 500, 0, 20, 20)])
    assert acuerdo(primera, segunda).iou_medio == 0.75  # (0,5 + 1,0) / 2
    assert acuerdo(_archivo([]), _archivo([])).iou_medio is None


def test_se_comparan_las_imagenes_de_la_segunda_y_la_primera_puede_traer_mas() -> None:
    primera = _archivo(
        [_caja("persona", 0, 0, 50, 100), _caja("persona", 0, 0, 50, 100, archivo="z.jpg")],
        {"a.jpg": HD, "z.jpg": HD},
    )
    segunda = _archivo([_caja("persona", 0, 0, 50, 100)])
    resultado = acuerdo(primera, segunda)
    assert resultado.imagenes == ("a.jpg",)
    assert (resultado.pares, resultado.solo_primera) == (1, 0)  # la caja de z.jpg no cuenta


@pytest.mark.parametrize(
    ("primera", "segunda", "mensaje"),
    [
        ({"a.jpg": HD}, {"a.jpg": HD, "b.jpg": HD}, r"b\.jpg"),
        ({"a.jpg": HD}, {"a.jpg": (960, 540)}, "tamaño"),
        ({"a.jpg": HD}, {}, "no trae imágenes"),
    ],
)
def test_imagenes_de_la_segunda_detiene(
    primera: dict[str, tuple[int, int]], segunda: dict[str, tuple[int, int]], mensaje: str
) -> None:
    with pytest.raises(EntradaInvalida, match=mensaje):
        imagenes_de_la_segunda(_archivo([], primera), _archivo([], segunda))


def test_acuerdo_de_punta_a_punta() -> None:
    primera = _archivo([_caja("persona", 0, 0, 50, 100), _caja("casco", 500, 0, 20, 20)])
    segunda = _archivo([_caja("persona", 0, 0, 50, 100), _caja("chaleco", 500, 0, 20, 20)])
    resultado = acuerdo(primera, segunda)
    assert resultado.matriz == {"persona": {"persona": 1}, "casco": {"chaleco": 1}}
    assert (resultado.pares, resultado.solo_primera, resultado.solo_segunda) == (2, 0, 0)
    # Observado 1/2; azar = (1*1 + 0)/4 = 1/4 -> kappa = (1/2 - 1/4)/(3/4) = 1/3.
    assert resultado.kappa == pytest.approx(1 / 3)
