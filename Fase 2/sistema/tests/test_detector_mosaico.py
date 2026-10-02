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


TODO = Caja(0.0, 0.0, 1.0, 1.0)


def test_sin_repetidos_une_el_mismo_objeto_visto_por_dos_mosaicos() -> None:
    a, b = _p(0.20, 0.30, 0.7), _p(0.23, 0.33, 0.9)  # centros a 0,3 del ancho
    assert sin_repetidos([(TODO, [a]), (TODO, [b])]) == [b]


def test_sin_repetidos_no_compara_dentro_de_un_mismo_mosaico() -> None:
    a, b = _p(0.20, 0.30, 0.7), _p(0.23, 0.33, 0.9)
    assert sorted(sin_repetidos([(TODO, [a, b])]), key=lambda d: d.confianza) == [a, b]


@pytest.mark.parametrize(
    ("otra", "esperadas"),
    [
        (_p(0.26, 0.36), 2),  # centros a 0,6 del ancho: dos personas distintas
        (_p(0.23, 0.33, clase=ClaseDetectada.CASCO), 2),  # otra clase
    ],
)
def test_sin_repetidos_respeta_objetos_distintos(otra: Deteccion, esperadas: int) -> None:
    assert len(sin_repetidos([(TODO, [_p(0.20, 0.30)]), (TODO, [otra])])) == esperadas


def test_sin_repetidos_no_compara_con_un_mosaico_que_no_podia_verla_entera() -> None:
    """Revisión del #31 (hallazgo A): p2 la ve entera solo el mosaico 2, y en ese mosaico el
    modelo no detectó a p1. Sin la condición de contención, el emparejamiento tomaba a p2
    por la copia de la p1 del mosaico 1 (están cerca) y p2 desaparecía."""
    p1, p2 = _p(0.20, 0.30, 0.9), _p(0.22, 0.32, 0.8)
    region1 = Caja(0.0, 0.0, 0.31, 1.0)  # contiene a p1, corta a p2
    region2 = Caja(0.1, 0.0, 0.6, 1.0)  # contiene a las dos
    resultado = sin_repetidos([(region1, [p1]), (region2, [p2])])
    assert sorted(d.confianza for d in resultado) == [0.8, 0.9]


def test_sin_repetidos_empareja_uno_a_uno() -> None:
    """Dos personas cercanas vistas por dos mosaicos: cada una se empareja con su copia, y
    ninguna se come a la otra aunque el orden de confianzas las cruce."""
    a1, b1 = _p(0.20, 0.30, 0.95), _p(0.22, 0.32, 0.60)
    a2, b2 = _p(0.20, 0.30, 0.70), _p(0.22, 0.32, 0.90)
    resultado = sin_repetidos([(TODO, [a1, b1]), (TODO, [a2, b2])])
    assert sorted(d.confianza for d in resultado) == [0.9, 0.95]


class PorCanal(Blancos):
    """Un objeto por canal de color (B, G, R): admite objetos superpuestos, como una
    persona tapada por otra."""

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        import cv2

        alto, ancho = imagen.shape[:2]
        salida = []
        for canal in range(3):
            mascara = (imagen[:, :, canal] == 255).astype(np.uint8)
            n, _, stats, _ = cv2.connectedComponentsWithStats(mascara)
            for x, y, w, h, _ in stats[1:n]:
                caja = Caja(x / ancho, y / alto, (x + w) / ancho, (y + h) / alto)
                salida.append(Deteccion(capture_ts, cuadro_idx, P, caja, 0.9 - canal / 10))
        return salida


def test_una_persona_tapada_en_el_solape_no_desaparece() -> None:
    """El escenario exacto de la revisión: recorte (0, 0, 0,3, 0,2), factor 2, lado 384,
    objeto_max 50; p1 de 50 px en x=135 y p2 de 50 px en x=155."""
    imagen = np.zeros((1080, 1920, 3), dtype=np.uint8)
    imagen[60:110, 135:185, 0] = 255
    imagen[60:110, 155:205, 1] = 255
    m = Mosaico(Caja(0.0, 0.0, 0.3, 0.2), 2.0, 384, 50)
    detecciones = DetectorMosaico(PorCanal(), m).detectar(imagen, cuadro_idx=0, capture_ts=T0)
    assert len(detecciones) == 2


def test_un_recorte_vacio_no_ve_nada() -> None:
    m = Mosaico(Caja(0.5, 0.5, 0.5001, 0.5001), 1.0, 640, 100)
    assert DetectorMosaico(Blancos(), m).detectar(_cuadro(), cuadro_idx=0, capture_ts=T0) == []


def test_validar_rechaza_la_configuracion_antes_del_primer_cuadro() -> None:
    mosaico = DetectorMosaico(Blancos(), Mosaico(Caja(0, 0, 1, 1), 4.0, 384, 50))
    with pytest.raises(ValueError, match="mosaicos"):
        mosaico.validar(1920, 1080)
    rx0, ry0, rx1, ry1 = FOSO_REAL
    foso = Caja(rx0 / 1920, ry0 / 1080, rx1 / 1920, ry1 / 1080)
    DetectorMosaico(Blancos(), Mosaico(foso, 2.0, 384, 100)).validar(1920, 1080)  # 60: pasa


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


def _px(x1: float, y1: float, x2: float, y2: float) -> Caja:
    return Caja(x1 / 1920, y1 / 1080, x2 / 1920, y2 / 1080)


def test_dos_copias_que_difieren_en_menos_de_un_pixel_se_emparejan() -> None:
    """Caso real del video de prueba (2026-10-01): la copia del mosaico A empieza en x=669,6 y
    la región del mosaico B en x=670,0. Con contención exacta, B «no podía verla» por 0,4 px,
    no se emparejaban y la misma persona salía dos veces (IoU 0,87)."""
    a = Deteccion(T0, 0, P, _px(669.6, 668.9, 702.2, 722.8), 0.8)
    b = Deteccion(T0, 0, P, _px(670.9, 665.5, 700.9, 722.9), 0.7)
    region_a, region_b = _px(600, 538, 792, 730), _px(670, 538, 862, 730)
    assert sin_repetidos([(region_a, [a]), (region_b, [b])], tolerancia=(4 / 1920, 4 / 1080)) == [a]


def test_la_tolerancia_no_alcanza_a_un_objeto_cortado_de_verdad() -> None:
    """La tolerancia es para diferencias de dibujo, no para un corte: p2 se sale ~19 px de la
    región 1, así que el mosaico 1 no podía verla y no se compara con su p1."""
    p1, p2 = _p(0.20, 0.30, 0.9), _p(0.22, 0.32, 0.8)
    region1, region2 = Caja(0.0, 0.0, 0.31, 1.0), Caja(0.1, 0.0, 0.6, 1.0)
    resultado = sin_repetidos([(region1, [p1]), (region2, [p2])], tolerancia=(4 / 1920, 4 / 1080))
    assert len(resultado) == 2


def test_detectar_empareja_con_la_tolerancia_en_px_del_cuadro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gepp_vision.detectores import mosaico as modulo

    recibida: list[tuple[float, float]] = []

    def espia(_por_mosaico, tolerancia=(0.0, 0.0)):  # type: ignore[no-untyped-def]
        recibida.append(tolerancia)
        return []

    monkeypatch.setattr(modulo, "sin_repetidos", espia)
    DetectorMosaico(Blancos(), Mosaico(Caja(0, 0, 0.2, 0.2), 1.0, 384, 50)).detectar(
        _cuadro(), cuadro_idx=0, capture_ts=T0
    )
    px = modulo.TOLERANCIA_CONTENCION_PX
    assert recibida == [(px / 1920, px / 1080)]


def test_la_tolerancia_queda_entre_la_diferencia_de_dibujo_y_un_corte() -> None:
    """Más que la diferencia de dibujo vista entre mosaicos (0,4 px) y bastante menos que lo
    que corta un borde a una persona tapada en el solape (~19 px en la revisión del #104)."""
    from gepp_vision.detectores.mosaico import TOLERANCIA_CONTENCION_PX

    assert 0.4 * 2 <= TOLERANCIA_CONTENCION_PX <= 19 / 2
