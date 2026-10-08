"""Pre-etiquetas para CVAT (#27): lo que el modelo propone y una persona corrige."""

from __future__ import annotations

import math

import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_vision.entrenamiento import CLASES_V1
from gepp_vision.etiquetado import (
    MINIMO_PX,
    TOLERANCIA_PX,
    a_coco,
    bajo_minimo,
    combinar,
    minimo_px,
)

from .conftest import T0

P, C = ClaseDetectada.PERSONA, ClaseDetectada.CASCO
FOSO = Caja(0.25, 0.25, 0.75, 0.75)


def _d(clase: ClaseDetectada, x1: float, y1: float, x2: float, y2: float) -> Deteccion:
    return Deteccion(T0, 0, clase, Caja(x1, y1, x2, y2), 0.8)


def test_combinar_toma_del_pase_completo_solo_lo_de_fuera_del_recorte() -> None:
    del_mosaico = [_d(P, 0.4, 0.4, 0.45, 0.5)]
    dentro = _d(P, 0.41, 0.4, 0.46, 0.5)  # lo vio también el pase completo: ya está
    fuera = _d(P, 0.8, 0.8, 0.9, 0.95)  # junto a la cámara, fuera del foso
    assert combinar(del_mosaico, [dentro, fuera], FOSO) == [*del_mosaico, fuera]


def test_combinar_decide_por_el_centro() -> None:
    cruza = _d(P, 0.7, 0.5, 0.9, 0.6)  # centro en x=0,8: fuera, aunque empiece dentro
    assert combinar([], [cruza], FOSO) == [cruza]


@pytest.mark.parametrize(
    ("clase", "lado_px", "entra"),
    [
        (C, 7.75, False),  # el casco baja a 8 px (guía §7, 2026-10-08)
        (C, 8, True),
        (C, 8.25, True),
        (P, 9.75, False),  # persona y chaleco siguen en 10 px
        (P, 10, True),
        (ClaseDetectada.CHALECO, 9.75, False),
        (ClaseDetectada.CHALECO, 10, True),
    ],
)
def test_a_coco_respeta_el_tamano_minimo_de_la_guia(
    clase: ClaseDetectada, lado_px: float, entra: bool
) -> None:
    """Guía de etiquetado §4: bajo 10 px de lado no lleva caja; el casco, bajo 8."""
    ancho, alto = 1024, 512  # diádicos: el lado en px sale exacto, sin 9,999...
    d = _d(clase, 0.125, 0.125, 0.125 + lado_px / ancho, 0.125 + 40 / alto)
    coco = a_coco([("a.jpg", ancho, alto, [d])])
    assert len(coco["annotations"]) == int(entra)


def test_a_coco_un_casco_de_8_px_exactos_entra_aunque_la_resta_de_flotantes_no_cierre() -> None:
    assert (0.108 - 0.1) * 1000 < 8  # el defecto: 7,999999999999993
    d = _d(C, 0.1, 0.125, 0.108, 0.25)
    assert len(a_coco([("a.jpg", 1000, 500, [d])])["annotations"]) == 1


@pytest.mark.parametrize(
    ("clase", "lado", "bajo"),
    [
        ("casco", 8, False),
        ("casco", 8 - 5e-7, False),  # dentro de la holgura
        ("casco", 8 - TOLERANCIA_PX, False),  # justo en el borde de la holgura
        ("casco", math.nextafter(8 - TOLERANCIA_PX, 0), True),  # un paso de flotante más abajo
        ("casco", 8 - 2e-6, True),
        ("casco", 7.75, True),
        ("persona", 9.999999999999998, False),
        ("persona", 10, False),
        ("persona", 9.75, True),
        ("chaleco", 9.999999999999998, False),
        ("chaleco", 9.75, True),
    ],
)
def test_bajo_minimo_con_holgura_de_flotantes(clase: str, lado: float, bajo: bool) -> None:
    assert bajo_minimo(lado, 40, clase) is bajo
    assert bajo_minimo(40, lado, clase) is bajo  # el lado chico puede ser el alto


def test_bajo_minimo_con_clase_desconocida() -> None:
    with pytest.raises(ValueError, match="fuera de la v1"):
        bajo_minimo(40, 40, "arnes")


def test_minimo_px_por_clase_y_clase_desconocida() -> None:
    assert [minimo_px(c) for c in ("persona", "chaleco", "casco")] == [MINIMO_PX, MINIMO_PX, 8]
    assert minimo_px(ClaseDetectada.CASCO) == 8  # también con el enum
    for desconocida in ("arnes", "Casco", ""):
        with pytest.raises(ValueError, match="fuera de la v1"):
            minimo_px(desconocida)


def test_a_coco_ignora_una_clase_fuera_de_la_v1_sin_fallar() -> None:
    arnes = _d(ClaseDetectada.ARNES, 0.1, 0.1, 0.3, 0.3)
    assert a_coco([("a.jpg", 1000, 500, [arnes])])["annotations"] == []


def test_a_coco_en_pixeles_con_las_categorias_de_la_v1() -> None:
    coco = a_coco([("a.jpg", 1000, 500, [_d(C, 0.1, 0.2, 0.15, 0.3)])])
    assert [c["name"] for c in coco["categories"]] == [str(c) for c in CLASES_V1]
    [a] = coco["annotations"]
    assert a["category_id"] == CLASES_V1[C]
    assert a["bbox"] == pytest.approx([100, 100, 50, 50])
    assert coco["images"] == [{"id": 1, "file_name": "a.jpg", "width": 1000, "height": 500}]


def test_a_coco_incluye_las_imagenes_sin_detecciones() -> None:
    """Una imagen vacía también se etiqueta: puede tener personas que el modelo no vio."""
    coco = a_coco([("a.jpg", 10, 10, []), ("b.jpg", 10, 10, [])])
    assert [i["file_name"] for i in coco["images"]] == ["a.jpg", "b.jpg"]
    assert coco["annotations"] == []
