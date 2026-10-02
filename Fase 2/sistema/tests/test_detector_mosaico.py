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
from gepp_vision.detectores.mosaico import (
    DetectorMosaico,
    Mosaico,
    posiciones,
    sin_repetidos,
)

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
        (300, 640, 128, [0]),  # más corto que un mosaico: uno solo
        (640, 640, 128, [0]),  # exacto
        (1000, 640, 128, [0, 360]),  # el último se alinea al final
        (1600, 640, 160, [0, 480, 960]),  # paso 480; 960 + 640 = 1600 justo
    ],
)
def test_posiciones(largo: int, lado: int, solape: int, esperado: list[int]) -> None:
    assert posiciones(largo, lado, solape) == esperado


def test_dos_mosaicos_vecinos_se_solapan_al_menos_lo_pedido() -> None:
    for largo in range(641, 3000, 37):
        inicio = posiciones(largo, 640, 200)
        assert inicio[0] == 0 and inicio[-1] + 640 == largo
        assert all(b - a <= 640 - 200 for a, b in pairwise(inicio))


@pytest.mark.parametrize(
    "parametros",
    [
        {"factor": 0},
        {"lado": 0},
        {"objeto_max_px": 0},
        {"objeto_max_px": 400},  # 400 x 2 = 800 >= 640: ningún mosaico lo contendría entero
    ],
)
def test_parametros_invalidos(parametros: dict[str, float]) -> None:
    base = {"recorte": Caja(0, 0, 1, 1), "factor": 2.0, "lado": 640, "objeto_max_px": 100}
    with pytest.raises(ValueError):
        Mosaico(**(base | parametros))  # type: ignore[arg-type]


# --- geometría --------------------------------------------------------------------------

FOSO = Caja(0.25, 0.25, 0.75, 0.75)


def test_un_objeto_vuelve_a_su_lugar_en_el_cuadro_completo() -> None:
    mosaico = DetectorMosaico(Blancos(), Mosaico(FOSO, 2.0, 640, 100))
    [d] = mosaico.detectar(_cuadro((900, 500, 20)), cuadro_idx=3, capture_ts=T0)
    assert d.caja.x1 == pytest.approx(900 / 1920, abs=1e-3)
    assert d.caja.y1 == pytest.approx(500 / 1080, abs=1e-3)
    assert d.caja.x2 == pytest.approx(920 / 1920, abs=1e-3)
    assert d.caja.y2 == pytest.approx(520 / 1080, abs=1e-3)
    assert (d.cuadro_idx, d.capture_ts) == (3, T0)


def test_el_modelo_recibe_mosaicos_del_lado_pedido_y_ampliados() -> None:
    interno = Blancos()
    # Recorte de 960x540 ampliado 2x = 1920x1080, mosaicos de 640.
    m = Mosaico(FOSO, 2.0, 640, 100)
    DetectorMosaico(interno, m).detectar(_cuadro(), cuadro_idx=0, capture_ts=T0)
    assert set(interno.recibidas) == {(640, 640)}
    assert len(interno.recibidas) == len(posiciones(1920, 640, m.solape_px)) * len(
        posiciones(1080, 640, m.solape_px)
    )


#: El recorte del foso del video de prueba, en px del cuadro de 1920x1080.
FOSO_REAL = (600, 220, 1400, 730)


@pytest.mark.parametrize(
    ("recorte_px", "factor"),
    [((0, 0, 1920, 1080), 1.0), (FOSO_REAL, 2.0)],
    ids=["completo-x1", "foso-x2"],
)
@pytest.mark.parametrize("ancho", [41, 81, 100])  # los de la revisión y el máximo
def test_cada_objeto_se_cuenta_una_vez_este_donde_este(
    recorte_px: tuple[int, int, int, int], factor: float, ancho: int
) -> None:
    """El caso de la revisión: personas del foso de 41-81 px, más anchas que el solape
    anterior, salían partidas en dos mosaicos y se contaban 2 o 4 veces."""
    rx0, ry0, rx1, ry1 = recorte_px
    recorte = Caja(rx0 / 1920, ry0 / 1080, rx1 / 1920, ry1 / 1080)
    mosaico = DetectorMosaico(Blancos(), Mosaico(recorte, factor, 384, 100))
    for x in range(rx0, rx1 - ancho, 29):  # 29 no divide al paso: recorre todos los desfases
        for y in (ry0, (ry0 + ry1) // 2, ry1 - ancho):
            detecciones = mosaico.detectar(_cuadro((x, y, ancho)), cuadro_idx=0, capture_ts=T0)
            assert len(detecciones) == 1, f"objeto de {ancho} px en ({x}, {y})"
            caja = detecciones[0].caja
            assert caja.x1 == pytest.approx(x / 1920, abs=1e-3), "llegó un pedazo, no el objeto"
            assert caja.x2 == pytest.approx((x + ancho) / 1920, abs=1e-3)


def test_el_foso_real_cabe_en_el_tope_de_mosaicos() -> None:
    rx0, ry0, rx1, ry1 = FOSO_REAL
    m = Mosaico(Caja(rx0 / 1920, ry0 / 1080, rx1 / 1920, ry1 / 1080), 2.0, 384, 100)
    interno = Blancos()
    DetectorMosaico(interno, m).detectar(_cuadro(), cuadro_idx=0, capture_ts=T0)
    assert len(interno.recibidas) == 60  # 10 columnas x 6 filas


def test_objetos_fuera_del_recorte_no_se_ven() -> None:
    mosaico = DetectorMosaico(Blancos(), Mosaico(Caja(0.5, 0.0, 1.0, 1.0), 1.0, 640, 100))
    assert mosaico.detectar(_cuadro((100, 100, 30)), cuadro_idx=0, capture_ts=T0) == []


def test_con_cuadro_completo_tambien_ve_lo_que_queda_fuera_del_recorte() -> None:
    """Una persona cerca de la cámara cae fuera del foso: el pase completo la recupera."""
    m = Mosaico(Caja(0.5, 0.0, 1.0, 1.0), 1.0, 640, 100, con_cuadro_completo=True)
    # Una dentro del recorte (la ven los dos pases: debe quedar una sola) y otra fuera.
    detecciones = DetectorMosaico(Blancos(), m).detectar(
        _cuadro((100, 100, 90), (1500, 100, 90)), cuadro_idx=0, capture_ts=T0
    )
    assert len(detecciones) == 2


class DesplazadoEnCompleto(Blancos):
    """Como `Blancos`, pero en el cuadro entero devuelve la caja corrida: así se comportan
    dos pases a escalas distintas sobre la misma persona (IoU bajo entre ellas)."""

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        salida = super().detectar(imagen, cuadro_idx=cuadro_idx, capture_ts=capture_ts)
        if imagen.shape[:2] != (1080, 1920):
            return salida
        return [
            Deteccion(
                d.capture_ts,
                d.cuadro_idx,
                d.clase,
                Caja(
                    d.caja.x1 + d.caja.ancho / 2, d.caja.y1, d.caja.x2 + d.caja.ancho / 2, d.caja.y2
                ),
                d.confianza,
            )
            for d in salida
        ]


def test_dentro_del_recorte_el_pase_completo_no_duplica_lo_que_ve_el_mosaico() -> None:
    m = Mosaico(Caja(0.25, 0.25, 0.75, 0.75), 1.0, 384, 100, con_cuadro_completo=True)
    # Una persona chica dentro del foso: la ven los dos pases, con cajas distintas.
    detecciones = DetectorMosaico(DesplazadoEnCompleto(), m).detectar(
        _cuadro((900, 500, 40)), cuadro_idx=0, capture_ts=T0
    )
    [d] = detecciones
    assert d.caja.x1 == pytest.approx(900 / 1920, abs=1e-3), "quedó la del pase completo"


def test_una_persona_grande_dentro_del_recorte_la_aporta_el_pase_completo() -> None:
    """Más grande que objeto_max_px: el mosaico la ve cortada y la descarta."""
    m = Mosaico(Caja(0.25, 0.25, 0.75, 0.75), 2.0, 384, 60, con_cuadro_completo=True)
    detecciones = DetectorMosaico(Blancos(), m).detectar(
        _cuadro((800, 400, 250)), cuadro_idx=0, capture_ts=T0
    )
    assert len(detecciones) == 1


def test_un_objeto_mas_grande_de_lo_previsto_que_cabe_en_un_mosaico_sale_una_vez() -> None:
    """150 px > objeto_max_px, pero cabe entero en un mosaico de 384: lo ven el mosaico y el
    pase completo. Debe aportarlo solo el pase completo."""
    m = Mosaico(Caja(0.25, 0.25, 0.75, 0.75), 1.0, 384, 100, con_cuadro_completo=True)
    detecciones = DetectorMosaico(Blancos(), m).detectar(
        _cuadro((560, 330, 150)), cuadro_idx=0, capture_ts=T0
    )
    assert len(detecciones) == 1


def test_un_recorte_vacio_igual_corre_el_pase_completo() -> None:
    m = Mosaico(Caja(0.5, 0.5, 0.5001, 0.5001), 1.0, 640, 100, con_cuadro_completo=True)
    detecciones = DetectorMosaico(Blancos(), m).detectar(
        _cuadro((100, 100, 30)), cuadro_idx=0, capture_ts=T0
    )
    assert len(detecciones) == 1


def test_demasiados_mosaicos_por_cuadro_se_rechazan() -> None:
    mosaico = DetectorMosaico(Blancos(), Mosaico(Caja(0, 0, 1, 1), 4.0, 384, 50))
    with pytest.raises(ValueError, match="mosaicos"):
        mosaico.detectar(_cuadro(), cuadro_idx=0, capture_ts=T0)


# --- un objeto, una detección ------------------------------------------------


class CajaSegunMosaico(Blancos):
    """Como `Blancos`, pero cada mosaico dibuja la caja corrida un 15 % hacia el borde más
    cercano: así se comporta un modelo real con contexto distinto. Dos mosaicos que ven el
    mismo objeto dan cajas con IoU ~0,54, bajo un umbral de fusión de 0,6 (en el video de
    prueba se vio IoU 0,60). Y si el objeto está justo en la frontera entre dos mosaicos,
    cada uno lo dibuja del lado del otro."""

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        salida = []
        for d in super().detectar(imagen, cuadro_idx=cuadro_idx, capture_ts=capture_ts):
            corrimiento = 0.15 * d.caja.ancho * (1 if d.caja.centro[0] > 0.5 else -1)
            caja = Caja(d.caja.x1 + corrimiento, d.caja.y1, d.caja.x2 + corrimiento, d.caja.y2)
            salida.append(Deteccion(d.capture_ts, d.cuadro_idx, d.clase, caja, d.confianza))
        return salida


@pytest.mark.parametrize("ancho", [41, 81])
def test_aunque_cada_mosaico_dibuje_distinto_el_objeto_sale_una_vez(ancho: int) -> None:
    rx0, ry0, rx1, ry1 = FOSO_REAL
    recorte = Caja(rx0 / 1920, ry0 / 1080, rx1 / 1920, ry1 / 1080)
    mosaico = DetectorMosaico(CajaSegunMosaico(), Mosaico(recorte, 2.0, 384, 100))
    for x in range(rx0 + 20, rx1 - ancho - 20, 7):  # paso fino: pasa por cada frontera
        detecciones = mosaico.detectar(_cuadro((x, 470, ancho)), cuadro_idx=0, capture_ts=T0)
        assert len(detecciones) == 1, f"objeto de {ancho} px en x={x}: {len(detecciones)}"


def test_dentro_de_un_mosaico_no_se_fusiona_nada() -> None:
    """Un casco dentro de su persona y una persona tapada por otra: todo lo que el modelo
    ve en un mismo mosaico sale tal cual."""
    persona = DeteccionGuionada(P, Caja(0.2, 0.2, 0.5, 0.9), 0.9)
    casco = DeteccionGuionada(ClaseDetectada.CASCO, Caja(0.25, 0.2, 0.35, 0.3), 0.8)
    tapada = DeteccionGuionada(P, Caja(0.3, 0.25, 0.4, 0.5), 0.8)
    interno = DetectorFalso([Segmento(0.0, 10.0, (persona, casco, tapada))])
    # Un recorte que cabe en un solo mosaico.
    m = Mosaico(Caja(0.0, 0.0, 0.1, 0.1), 1.0, 384, 100)
    detecciones = DetectorMosaico(interno, m).detectar(_cuadro(), cuadro_idx=0, capture_ts=T0)
    assert sorted(str(d.clase) for d in detecciones) == ["casco", "persona", "persona"]


def _p(x1: float, x2: float, conf: float = 0.9, clase: ClaseDetectada = P) -> Deteccion:
    return Deteccion(T0, 0, clase, Caja(x1, 0.2, x2, 0.6), conf)


def test_sin_repetidos_une_el_mismo_objeto_visto_por_dos_mosaicos() -> None:
    a, b = _p(0.20, 0.30, 0.7), _p(0.23, 0.33, 0.9)  # centros a 0,3 del ancho
    assert sin_repetidos([[a], [b]]) == [b]


def test_sin_repetidos_no_compara_dentro_de_un_mismo_mosaico() -> None:
    a, b = _p(0.20, 0.30, 0.7), _p(0.23, 0.33, 0.9)
    assert sorted(sin_repetidos([[a, b]]), key=lambda d: d.confianza) == [a, b]


@pytest.mark.parametrize(
    ("otra", "esperadas"),
    [
        (_p(0.26, 0.36), 2),  # centros a 0,6 del ancho: dos personas distintas
        (_p(0.23, 0.33, clase=ClaseDetectada.CASCO), 2),  # otra clase
    ],
)
def test_sin_repetidos_respeta_objetos_distintos(otra: Deteccion, esperadas: int) -> None:
    assert len(sin_repetidos([[_p(0.20, 0.30)], [otra]])) == esperadas


def test_un_objeto_que_cruza_el_borde_del_recorte_sale_entero_del_pase_completo() -> None:
    m = Mosaico(Caja(0.5, 0.0, 1.0, 1.0), 1.0, 384, 100, con_cuadro_completo=True)
    # De 940 a 990: la mitad izquierda queda fuera del recorte (que empieza en 960).
    [d] = DetectorMosaico(Blancos(), m).detectar(
        _cuadro((940, 300, 50)), cuadro_idx=0, capture_ts=T0
    )
    assert d.caja.x1 == pytest.approx(940 / 1920, abs=1e-3)


def test_la_version_dice_que_es_mosaico_y_de_que_modelo() -> None:
    mosaico = DetectorMosaico(Blancos(), Mosaico(Caja(0.101, 0, 1, 1), 2.0, 640, 100))
    otro = DetectorMosaico(Blancos(), Mosaico(Caja(0.104, 0, 1, 1), 2.0, 640, 100))
    assert "mosaico" in mosaico.version and "blancos" in mosaico.version
    assert mosaico.version != otro.version  # se audita por versión: no puede colapsar


# --- batería común ----------------------------------------------------------------------


class TestDetectorMosaico(ContratoDetector):
    @pytest.fixture
    def detector(self) -> Detector:
        caja = Caja(0.4, 0.4, 0.6, 0.6)
        guion = [Segmento(0.0, 10.0, (DeteccionGuionada(P, caja, 0.8),))]
        return DetectorMosaico(DetectorFalso(guion), Mosaico(Caja(0, 0, 1, 1), 2.0, 64, 10))
