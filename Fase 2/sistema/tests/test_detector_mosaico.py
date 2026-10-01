"""Detector en mosaico: objetos chicos en cámaras lejanas (#31).

En el video de prueba, un casco del fondo mide ~8 px en el cuadro de 1080. Al achicar el
cuadro a 384 queda en 1-2 px. El mosaico recorta la zona, la amplía y la analiza por partes.
Se prueba con un detector de juguete que encuentra cuadrados blancos: así se comprueba la
geometría sin GPU y sin modelo.
"""

from __future__ import annotations

from datetime import datetime
from itertools import pairwise

import numpy as np
import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_vision import Detector
from gepp_vision.detectores import DetectorFalso, Segmento
from gepp_vision.detectores.falso import DeteccionGuionada
from gepp_vision.detectores.mosaico import DetectorMosaico, Mosaico, fusionar, posiciones

from .conftest import T0
from .contrato_detector import ContratoDetector

P = ClaseDetectada.PERSONA


class Blancos:
    """Detector de juguete: una persona por cada región blanca (255) conexa de la imagen.

    Registra el tamaño de cada imagen que recibe, para comprobar el mosaico."""

    version = "blancos"

    def __init__(self) -> None:
        self.recibidas: list[tuple[int, int]] = []

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        import cv2

        alto, ancho = imagen.shape[:2]
        self.recibidas.append((alto, ancho))
        mascara = (imagen[:, :, 0] == 255).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(mascara)
        salida = []
        for x, y, w, h, _ in stats[1:n]:
            salida.append(
                Deteccion(
                    capture_ts,
                    cuadro_idx,
                    P,
                    Caja(x / ancho, y / alto, (x + w) / ancho, (y + h) / alto),
                    0.9,
                )
            )
        return salida


def _cuadro(*cuadrados: tuple[int, int, int]) -> np.ndarray:
    """Cuadro de 1080x1920 negro con cuadrados blancos (x, y, lado) en píxeles."""
    imagen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for x, y, lado in cuadrados:
        imagen[y : y + lado, x : x + lado] = 255
    return imagen


# --- posiciones de los mosaicos ---------------------------------------------------------


@pytest.mark.parametrize(
    ("largo", "lado", "solape", "esperado"),
    [
        (300, 640, 0.2, [0]),  # más corto que un mosaico: uno solo
        (640, 640, 0.2, [0]),  # exacto
        (1000, 640, 0.2, [0, 360]),  # el último se alinea al final
        (1600, 640, 0.25, [0, 480, 960]),  # paso 480; 960 + 640 = 1600 justo
    ],
)
def test_posiciones(largo: int, lado: int, solape: float, esperado: list[int]) -> None:
    assert posiciones(largo, lado, solape) == esperado


def test_posiciones_cubren_todo_el_largo() -> None:
    for largo in range(641, 3000, 37):
        inicio = posiciones(largo, 640, 0.2)
        assert inicio[0] == 0 and inicio[-1] + 640 == largo
        assert all(b - a <= 640 * 0.8 for a, b in pairwise(inicio))


@pytest.mark.parametrize(
    "parametros",
    [
        {"factor": 0},
        {"lado": 0},
        {"solape": 1.0},
        {"solape": -0.1},
    ],
)
def test_parametros_invalidos(parametros: dict[str, float]) -> None:
    base = {"recorte": Caja(0, 0, 1, 1), "factor": 2.0, "lado": 640, "solape": 0.2}
    with pytest.raises(ValueError):
        Mosaico(**(base | parametros))  # type: ignore[arg-type]


# --- geometría --------------------------------------------------------------------------


def test_un_objeto_vuelve_a_su_lugar_en_el_cuadro_completo() -> None:
    interno = Blancos()
    mosaico = DetectorMosaico(interno, Mosaico(Caja(0.25, 0.25, 0.75, 0.75), 2.0, 640, 0.2))
    [d] = mosaico.detectar(_cuadro((900, 500, 20)), cuadro_idx=3, capture_ts=T0)
    assert d.caja.x1 == pytest.approx(900 / 1920, abs=1e-3)
    assert d.caja.y1 == pytest.approx(500 / 1080, abs=1e-3)
    assert d.caja.x2 == pytest.approx(920 / 1920, abs=1e-3)
    assert d.caja.y2 == pytest.approx(520 / 1080, abs=1e-3)
    assert (d.cuadro_idx, d.capture_ts) == (3, T0)


def test_el_modelo_recibe_mosaicos_del_lado_pedido_y_ampliados() -> None:
    interno = Blancos()
    # Recorte de 960x540 ampliado 2x = 1920x1080: 4 mosaicos de ancho y 3 de alto a 640.
    DetectorMosaico(interno, Mosaico(Caja(0.25, 0.25, 0.75, 0.75), 2.0, 640, 0.2)).detectar(
        _cuadro(), cuadro_idx=0, capture_ts=T0
    )
    assert set(interno.recibidas) == {(640, 640)}
    assert len(interno.recibidas) == len(posiciones(1920, 640, 0.2)) * len(
        posiciones(1080, 640, 0.2)
    )


def test_un_objeto_en_el_solape_no_se_cuenta_dos_veces() -> None:
    interno = Blancos()
    mosaico = DetectorMosaico(interno, Mosaico(Caja(0, 0, 1, 1), 1.0, 640, 0.25))
    # x de 500 a 530: dentro del mosaico que parte en 0 y del que parte en 480.
    detecciones = mosaico.detectar(_cuadro((500, 100, 30)), cuadro_idx=0, capture_ts=T0)
    assert len(detecciones) == 1


def test_objetos_fuera_del_recorte_no_se_ven() -> None:
    mosaico = DetectorMosaico(Blancos(), Mosaico(Caja(0.5, 0.0, 1.0, 1.0), 1.0, 640, 0.2))
    assert mosaico.detectar(_cuadro((100, 100, 30)), cuadro_idx=0, capture_ts=T0) == []


def test_con_cuadro_completo_tambien_ve_lo_que_queda_fuera_del_recorte() -> None:
    """Una persona cerca de la cámara cae fuera del foso: el pase completo la recupera."""
    m = Mosaico(Caja(0.5, 0.0, 1.0, 1.0), 1.0, 640, 0.2, con_cuadro_completo=True)
    # Una dentro del recorte (la ven los dos pases: debe quedar una sola) y otra fuera.
    detecciones = DetectorMosaico(Blancos(), m).detectar(
        _cuadro((100, 100, 200), (1500, 100, 200)), cuadro_idx=0, capture_ts=T0
    )
    assert len(detecciones) == 2


def test_dos_objetos_juntos_de_la_misma_clase_no_se_fusionan() -> None:
    mosaico = DetectorMosaico(Blancos(), Mosaico(Caja(0, 0, 1, 1), 1.0, 640, 0.2))
    detecciones = mosaico.detectar(
        _cuadro((100, 100, 30), (140, 100, 30)), cuadro_idx=0, capture_ts=T0
    )
    assert len(detecciones) == 2


def test_un_casco_dentro_de_la_persona_no_se_fusiona_con_ella() -> None:
    """El caso de todos los días: la caja del casco cae entera dentro de la de la persona."""
    persona = Deteccion(T0, 0, P, Caja(0.2, 0.2, 0.4, 0.8), 0.9)
    casco = Deteccion(T0, 0, ClaseDetectada.CASCO, Caja(0.25, 0.2, 0.35, 0.3), 0.8)
    assert fusionar([persona, casco]) == [persona, casco]


def test_la_misma_persona_cortada_por_el_borde_se_fusiona() -> None:
    entera = Deteccion(T0, 0, P, Caja(0.2, 0.2, 0.4, 0.8), 0.9)
    cortada = Deteccion(T0, 0, P, Caja(0.2, 0.2, 0.28, 0.8), 0.7)  # IoU 0,4, contenida entera
    assert fusionar([cortada, entera]) == [entera]


def test_la_version_dice_que_es_mosaico_y_de_que_modelo() -> None:
    mosaico = DetectorMosaico(Blancos(), Mosaico(Caja(0, 0, 1, 1), 2.0, 640, 0.2))
    assert "mosaico" in mosaico.version and "blancos" in mosaico.version


# --- batería común ----------------------------------------------------------------------


class TestDetectorMosaico(ContratoDetector):
    @pytest.fixture
    def detector(self) -> Detector:
        guion = [Segmento(0.0, 10.0, (DeteccionGuionada(P, Caja(0.4, 0.4, 0.6, 0.6), 0.8),))]
        return DetectorMosaico(DetectorFalso(guion), Mosaico(Caja(0, 0, 1, 1), 2.0, 64, 0.2))
