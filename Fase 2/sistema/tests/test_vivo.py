"""Cuadro de la vista en vivo (`gepp_vision.vivo`): imagen nítida con las cajas, sin tapar rostros.

Lo que se cuida: que la vista no dibuje nada negro sobre las personas (el punto en la cara se quitó
el 2026-10-09, decisión de Edgar Tolentino solo para el prototipo), que la cara quede tal cual y que
la vista parta de la imagen con la privacidad aplicada, la misma que vio el detector.
"""

from __future__ import annotations

from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion, Regla
from gepp_vision import MascaraPrivacidad, PipelineEtapa1
from gepp_vision.detectores import DetectorFalso, Guion
from gepp_vision.evidencia import zona_de_rostro
from gepp_vision.seguimiento import SeguidorIoU
from gepp_vision.vivo import componer_vista, cuadro_en_vivo

from .conftest import T0
from .test_pipeline import FIXTURES

ANCHO, ALTO = 640, 480
NEGRO = 40  # un píxel "negro" para estos tests: tolera el JPEG


def decodificar(datos: bytes) -> np.ndarray:
    imagen = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)
    assert imagen is not None
    return imagen


def persona(
    alto_px: int, *, confianza: float = 0.9, y1_px: int = 40, x1: float = 0.40
) -> Deteccion:
    """Una persona de `alto_px` de alto en un cuadro de 640x480."""
    caja = Caja(x1, y1_px / ALTO, x1 + 0.20, (y1_px + alto_px) / ALTO)
    return Deteccion(T0, 0, ClaseDetectada.PERSONA, caja, confianza)


def casco_de(p: Deteccion, *, confianza: float = 0.9) -> Deteccion:
    """Un casco en la coronilla de `p`: del 2 al 14 % de su alto, 40 % central de su ancho."""
    c = p.caja
    caja = Caja(
        c.x1 + c.ancho * 0.30, c.y1 + c.alto * 0.02, c.x1 + c.ancho * 0.70, c.y1 + c.alto * 0.14
    )
    return Deteccion(T0, 0, ClaseDetectada.CASCO, caja, confianza)


def fondo(valor: int = 220, forma: tuple[int, int] = (ALTO, ANCHO)) -> np.ndarray:
    return np.full((*forma, 3), valor, dtype=np.uint8)


def px(caja: Caja, forma: tuple[int, int] = (ALTO, ANCHO)) -> tuple[int, int, int, int]:
    alto, ancho = forma
    return (
        round(caja.x1 * ancho),
        round(caja.y1 * alto),
        round(caja.x2 * ancho),
        round(caja.y2 * alto),
    )


def centro_de_la_cara(p: Deteccion) -> tuple[int, int]:
    x1, y1, x2, y2 = px(zona_de_rostro(p.caja))
    return (x1 + x2) // 2, (y1 + y2) // 2


# ── La imagen es nítida ───────────────────────────────────────────────────────────────


def test_la_imagen_sale_nitida_sin_pixelar() -> None:
    imagen = fondo(128)
    imagen[200:260, 300:360] = (np.indices((60, 60)).sum(axis=0) % 2 * 255)[..., None]
    assert (componer_vista(imagen, []) == imagen).all()  # sin detecciones, es la imagen tal cual
    salida = decodificar(cuadro_en_vivo(imagen, [], calidad=95))
    assert salida[200:260, 300:360].std() > 60  # y el patrón de 1 px sigue ahí


# ── Sin punto: ninguna cara se tapa ────────────────────────────────────────────────────


def _escenas() -> dict[str, list[Deteccion]]:
    p = persona(400)
    lejana = persona(8)
    return {
        "persona de 400 px": [p],
        "persona de 40 px": [persona(40)],
        "persona de 8 px": [lejana],
        "confianza baja": [persona(400, confianza=0.25)],
        "con casco": [p, casco_de(p)],
        "lejana con casco": [
            lejana,
            Deteccion(T0, 0, ClaseDetectada.CASCO, Caja(0.46, 40 / ALTO, 0.54, 41 / ALTO), 0.9),
        ],
        "casco suelto": [Deteccion(T0, 0, ClaseDetectada.CASCO, Caja(0.4, 0.1, 0.6, 0.5), 0.9)],
    }


@pytest.mark.parametrize("escena", list(_escenas()))
def test_la_vista_no_dibuja_ningun_pixel_negro(escena: str) -> None:
    vista = componer_vista(fondo(), _escenas()[escena])
    assert not (vista < NEGRO).all(axis=2).any()  # solo las cajas de color sobre el fondo


@pytest.mark.parametrize("con_casco", [False, True])
def test_la_cara_queda_tal_cual(con_casco: bool) -> None:
    p = persona(400)
    imagen = fondo(128)
    x1, y1, x2, y2 = px(zona_de_rostro(p.caja))
    imagen[y1:y2, x1:x2] = (np.indices((y2 - y1, x2 - x1)).sum(axis=0) % 2 * 255)[..., None]
    vista = componer_vista(imagen, [p, casco_de(p)] if con_casco else [p])
    cx, cy = centro_de_la_cara(p)
    cara = (slice(cy - 3, cy + 4), slice(cx - 3, cx + 4))
    assert (vista[cara] == imagen[cara]).all()


# ── Cajas y formato ───────────────────────────────────────────────────────────────────


def test_las_cajas_se_dibujan_nitidas() -> None:
    d = Deteccion(T0, 0, ClaseDetectada.CHALECO, Caja(0.10, 0.10, 0.30, 0.30), 0.9)
    salida = decodificar(cuadro_en_vivo(fondo(128), [d]))
    borde = salida[round(0.10 * ALTO), round(0.20 * ANCHO)]
    interior = salida[round(0.20 * ALTO), round(0.20 * ANCHO)]
    assert int(borde[0]) - int(borde[2]) > 100  # azul alto, rojo bajo (BGR 255,160,0)
    assert abs(int(interior[0]) - int(interior[2])) < 15


@pytest.mark.parametrize(
    "forma,esperado",
    [((720, 1280), (360, 640)), ((480, 640), (480, 640)), ((240, 320), (240, 320))],
)
def test_sale_de_640_de_ancho_y_no_agranda(
    forma: tuple[int, int], esperado: tuple[int, int]
) -> None:
    salida = decodificar(cuadro_en_vivo(np.full((*forma, 3), 100, dtype=np.uint8), []))
    assert salida.shape[:2] == esperado


def test_la_caja_cae_en_el_mismo_lugar_relativo_al_reducir() -> None:
    d = persona(400)
    grande = decodificar(cuadro_en_vivo(fondo(forma=(960, 1280)), [d], calidad=95))
    x1, y1, _, y2 = px(d.caja)
    borde = grande[(y1 + y2) // 2, x1]
    assert grande.shape[:2] == (480, 640)
    assert int(borde[2]) - int(borde[0]) > 150  # rojo alto, azul bajo (BGR 0,200,255)


def test_la_calidad_se_aplica() -> None:
    ruido = np.random.default_rng(2).integers(0, 256, (ALTO, ANCHO, 3), dtype=np.uint8)
    baja, alta = cuadro_en_vivo(ruido, [], calidad=20), cuadro_en_vivo(ruido, [], calidad=95)
    assert len(baja) < len(alta)


def test_es_un_jpeg() -> None:
    assert cuadro_en_vivo(fondo(), []).startswith(b"\xff\xd8")


# ── H3: la vista parte de la imagen que vio el detector, a través del pipeline ──────────


def _cuadro(imagen: np.ndarray) -> SimpleNamespace:
    return SimpleNamespace(indice=0, capture_ts=T0, imagen=imagen)


def test_un_poligono_de_privacidad_queda_negro_en_la_vista(regla: Regla) -> None:
    """Recorrido real: pipeline (máscara → detector) → `ResultadoCuadro.imagen` → vista."""
    mascara = MascaraPrivacidad([[(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]])
    pipeline = PipelineEtapa1(
        DetectorFalso(Guion.desde_json(FIXTURES / "guion_con_casco.json")),
        SeguidorIoU(),
        [regla],
        mascara=mascara,
    )
    original = fondo(230)
    vistas: list[bytes] = []

    def por_cuadro(_cuadro: SimpleNamespace, r: object) -> None:
        assert r.imagen is not None  # type: ignore[attr-defined]
        vistas.append(cuadro_en_vivo(r.imagen, r.detecciones))  # type: ignore[attr-defined]

    pipeline.procesar_todo([_cuadro(original)], por_cuadro=por_cuadro)  # type: ignore[list-item,arg-type]

    (jpeg,) = vistas
    salida = decodificar(jpeg)
    assert salida[:, :240].max() < 30  # el polígono (mitad izquierda) está negro
    assert salida[:, 360:].min() > 180  # y el resto, no
    assert (original == 230).all()  # el cuadro original no se tocó


def test_la_vista_sin_mascara_usa_el_cuadro_tal_cual(regla: Regla) -> None:
    pipeline = PipelineEtapa1(
        DetectorFalso(Guion.desde_json(FIXTURES / "guion_con_casco.json")),
        SeguidorIoU(),
        [regla],
    )
    vistas: list[object] = []
    pipeline.procesar_todo(
        [_cuadro(fondo(230))],  # type: ignore[list-item]
        por_cuadro=lambda _c, r: vistas.append(r.imagen),
    )
    assert vistas[0] is not None and (vistas[0] == 230).all()  # type: ignore[comparison-overlap]
