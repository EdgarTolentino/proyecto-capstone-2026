"""Cuadro de la vista en vivo (`gepp_vision.vivo`): imagen nítida con las cajas, sin tapar rostros.

Lo que se cuida: que la vista no dibuje nada negro sobre las personas (decisión de Edgar Tolentino
del 2026-10-09, ver ADR-006), que la cara quede tal cual y que la vista
parta de la imagen con la privacidad aplicada, la misma que vio el detector.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion, Regla
from gepp_vision import MascaraPrivacidad, PipelineEtapa1
from gepp_vision.detectores import DetectorFalso, Guion
from gepp_vision.evidencia import zona_de_rostro
from gepp_vision.seguimiento import SeguidorIoU
from gepp_vision.vivo import ETIQUETAS, componer_vista, cuadro_en_vivo

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


def cabeza_de(p: Deteccion) -> Deteccion:
    """La cabeza descubierta de `p`: la misma franja que su casco (ADR-013)."""
    return Deteccion(T0, 0, ClaseDetectada.CABEZA, casco_de(p).caja, 0.9)


def sin_chaleco_de(p: Deteccion) -> Deteccion:
    """El torso de `p` sin chaleco: del 20 al 60 % de su alto."""
    c = p.caja
    caja = Caja(c.x1, c.y1 + c.alto * 0.20, c.x2, c.y1 + c.alto * 0.60)
    return Deteccion(T0, 0, ClaseDetectada.SIN_CHALECO, caja, 0.9)


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
        "sin casco ni chaleco": [p, cabeza_de(p), sin_chaleco_de(p)],
    }


@pytest.mark.parametrize("escena", list(_escenas()))
def test_la_vista_no_dibuja_ningun_pixel_negro(escena: str) -> None:
    vista = componer_vista(fondo(), _escenas()[escena])
    assert not (vista < NEGRO).all(axis=2).any()  # solo las cajas de color sobre el fondo


@pytest.mark.parametrize("epp", ["ninguno", "casco", "falta"])
def test_la_cara_queda_tal_cual(epp: str) -> None:
    p = persona(400)
    imagen = fondo(128)
    x1, y1, x2, y2 = px(zona_de_rostro(p.caja))
    imagen[y1:y2, x1:x2] = (np.indices((y2 - y1, x2 - x1)).sum(axis=0) % 2 * 255)[..., None]
    extra = {"ninguno": [], "casco": [casco_de(p)], "falta": [cabeza_de(p), sin_chaleco_de(p)]}
    vista = componer_vista(imagen, [p, *extra[epp]])
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


# ── Cajas de falta (ADR-013): rojas y con su etiqueta ───────────────────────────────────


def _alto_rotulo(texto: str) -> int:
    (_, h), base = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    return int(h + base + 2 * 3)


def _rojo(pixel: np.ndarray) -> bool:
    return int(pixel[2]) > 180 and int(pixel[0]) < 60 and int(pixel[1]) < 60


def _blancos(region: np.ndarray) -> int:
    return int((region > 200).all(axis=2).sum())


@pytest.mark.parametrize(
    "clase,texto",
    [(ClaseDetectada.CABEZA, "SIN CASCO"), (ClaseDetectada.SIN_CHALECO, "SIN CHALECO")],
)
def test_la_caja_de_falta_es_roja_y_lleva_su_etiqueta(clase: ClaseDetectada, texto: str) -> None:
    assert ETIQUETAS[clase] == texto
    caja = Caja(0.30, 0.40, 0.60, 0.80)
    vista = componer_vista(fondo(128), [Deteccion(T0, 0, clase, caja, 0.9)])
    x1, y1, x2, y2 = px(caja)
    assert _rojo(vista[(y1 + y2) // 2, x1])  # el borde izquierdo, a media altura
    # El rótulo: fondo rojo con letras blancas, encima de la cabeza y abajo por dentro del torso.
    alto = _alto_rotulo(texto)
    franja = (
        vista[y1 - alto : y1, x1:x2]
        if clase is ClaseDetectada.CABEZA
        else vista[y2 - alto : y2, x1:x2]
    )
    assert _blancos(franja) > 20
    assert _rojo(franja[1, 1])


def test_las_cajas_de_cumplimiento_no_llevan_etiqueta() -> None:
    p = persona(300, y1_px=100)
    vista = componer_vista(fondo(128), [p, casco_de(p)])
    assert _blancos(vista) == 0


@pytest.mark.parametrize("sobra", [0, -1, "pegada"])
def test_la_etiqueta_de_cabeza_baja_si_no_cabe_arriba(sobra: int | str) -> None:
    """Justo en el límite cabe encima; un píxel menos, o la caja pegada arriba, y va debajo."""
    alto = _alto_rotulo("SIN CASCO")
    y1 = 0 if sobra == "pegada" else alto + int(sobra)
    caja = Caja(0.40, y1 / ALTO, 0.60, (y1 + 60) / ALTO)
    vista = componer_vista(fondo(128), [Deteccion(T0, 0, ClaseDetectada.CABEZA, caja, 0.9)])
    x1, _, x2, y2 = px(caja)
    arriba, abajo = vista[y1 - alto : y1, x1:x2], vista[y2 : y2 + alto, x1:x2]
    assert (_blancos(arriba) > 20, _blancos(abajo) > 20) == (
        (True, False) if sobra == 0 else (False, True)
    )


def _sin_rotulos(
    monkeypatch: pytest.MonkeyPatch, imagen: np.ndarray, dets: list[Deteccion]
) -> np.ndarray:
    with monkeypatch.context() as m:
        m.setattr("gepp_vision.vivo.ETIQUETAS", {})
        return componer_vista(imagen, dets)


def _rotulo(con: np.ndarray, sin: np.ndarray) -> tuple[slice, slice]:
    """El rectángulo que ocupan los rótulos: donde la vista con rótulos difiere de la vista sin."""
    ys, xs = np.nonzero((con != sin).any(axis=2))
    return slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1)


@pytest.mark.parametrize("clase", [ClaseDetectada.CABEZA, ClaseDetectada.SIN_CHALECO])
def test_cada_clase_escribe_su_propio_texto(
    monkeypatch: pytest.MonkeyPatch, clase: ClaseDetectada
) -> None:
    """El ancho de las letras dibujadas es el de SU texto, no el de la otra etiqueta."""
    dets = [Deteccion(T0, 0, clase, Caja(0.30, 0.40, 0.70, 0.80), 0.9)]
    con = componer_vista(fondo(128), dets)
    ys, xs = _rotulo(con, _sin_rotulos(monkeypatch, fondo(128), dets))
    blancas = np.nonzero((con[ys, xs] > 200).all(axis=2).any(axis=0))[0]
    (ancho, _), _ = cv2.getTextSize(ETIQUETAS[clase], cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    assert abs(int(blancas.max() - blancas.min() + 1) - ancho) <= 3


def test_ninguna_caja_pasa_por_encima_de_un_rotulo(monkeypatch: pytest.MonkeyPatch) -> None:
    """El borde de arriba de la persona cruza el rótulo de su cabeza: el rótulo queda encima."""
    p = persona(400, y1_px=100)
    dets = [cabeza_de(p), p]  # la persona, después: si las cajas fueran al final, la taparía
    solo = componer_vista(fondo(128), [cabeza_de(p)])
    ys, xs = _rotulo(solo, _sin_rotulos(monkeypatch, fondo(128), [cabeza_de(p)]))
    assert ys.start < 100 < ys.stop  # el escenario: el borde de la persona cruza el rótulo
    assert (componer_vista(fondo(128), dets)[ys, xs] == solo[ys, xs]).all()


def test_un_rotulo_no_borra_otro(monkeypatch: pytest.MonkeyPatch) -> None:
    """Persona chica pegada arriba (escenario de la revisión): los dos rótulos se leen enteros."""
    cabeza = Deteccion(
        T0, 0, ClaseDetectada.CABEZA, Caja(304 / ANCHO, 1 / ALTO, 312 / ANCHO, 6 / ALTO), 0.9
    )
    chaleco = Deteccion(
        T0, 0, ClaseDetectada.SIN_CHALECO, Caja(300 / ANCHO, 8 / ALTO, 316 / ANCHO, 24 / ALTO), 0.9
    )
    solo = componer_vista(fondo(128), [cabeza])
    ys, xs = _rotulo(solo, _sin_rotulos(monkeypatch, fondo(128), [cabeza]))
    juntos = componer_vista(fondo(128), [cabeza, chaleco])
    assert (juntos[ys, xs] == solo[ys, xs]).all()  # «SIN CASCO» intacto


def _escenas_de_rostro() -> dict[str, list[Deteccion]]:
    chica = Deteccion(
        T0, 0, ClaseDetectada.PERSONA, Caja(300 / ANCHO, 460 / ALTO, 312 / ANCHO, 1.0), 0.9
    )
    chaleco_chica = Deteccion(
        T0,
        0,
        ClaseDetectada.SIN_CHALECO,
        Caja(300 / ANCHO, 464 / ALTO, 312 / ANCHO, 472 / ALTO),
        0.9,
    )
    # Vecina: la cara de B queda justo donde iría, encima de su cabeza, el rótulo de A.
    a = persona(300, y1_px=150, x1=0.40)
    b = persona(300, y1_px=100, x1=0.36)
    # Revisión de Codex: la cara empieza en y = 105,25 px; redondeada a 105-115 dejaba libre la
    # fila 115, que la cara sí toca, y el rótulo de la cintura subía hasta ella.
    fraccion = Deteccion(
        T0,
        0,
        ClaseDetectada.PERSONA,
        Caja(100 / ANCHO, 100.25 / ALTO, 200 / ANCHO, 200.25 / ALTO),
        0.9,
    )
    chaleco_fraccion = Deteccion(
        T0,
        0,
        ClaseDetectada.SIN_CHALECO,
        Caja(130 / ANCHO, 120 / ALTO, 210 / ANCHO, 134 / ALTO),
        0.9,
    )
    return {
        "cara en un borde fraccionario": [fraccion, chaleco_fraccion],
        "chica en el borde de abajo": [chica, chaleco_chica],
        "cabeza bajo la cara de la vecina": [a, b, cabeza_de(a)],
        "persona con las dos faltas": [a, cabeza_de(a), sin_chaleco_de(a)],
    }


@pytest.mark.parametrize("escena", list(_escenas_de_rostro()))
def test_ningun_rotulo_toca_una_cara(monkeypatch: pytest.MonkeyPatch, escena: str) -> None:
    dets = _escenas_de_rostro()[escena]
    con, sin = componer_vista(fondo(128), dets), _sin_rotulos(monkeypatch, fondo(128), dets)
    for d in dets:
        if d.clase is ClaseDetectada.PERSONA:
            # Todo píxel que la cara toque, aunque sea en parte: hacia afuera, no redondeado.
            c = zona_de_rostro(d.caja)
            x1, y1 = math.floor(c.x1 * ANCHO), math.floor(c.y1 * ALTO)
            x2, y2 = math.ceil(c.x2 * ANCHO), math.ceil(c.y2 * ALTO)
            assert (con[y1:y2, x1:x2] == sin[y1:y2, x1:x2]).all(), escena


@pytest.mark.parametrize(
    "caja",
    [Caja(-0.2, 0.4, -0.1, 0.6), Caja(1.1, 0.4, 1.2, 0.6), Caja(0.4, -0.3, 0.6, -0.1)],
    ids=["a la izquierda", "a la derecha", "arriba"],
)
def test_una_caja_fuera_del_cuadro_no_deja_rotulo(caja: Caja) -> None:
    vista = componer_vista(fondo(128), [Deteccion(T0, 0, ClaseDetectada.CABEZA, caja, 0.9)])
    assert _blancos(vista) == 0


def test_una_caja_que_asoma_un_pixel_si_lleva_rotulo() -> None:
    """El otro lado del borde: basta un píxel dentro del cuadro para rotularla."""
    caja = Caja(-0.2, 0.4, 1 / ANCHO + 1e-9, 0.6)
    vista = componer_vista(fondo(128), [Deteccion(T0, 0, ClaseDetectada.CABEZA, caja, 0.9)])
    assert _blancos(vista) > 20


def test_una_caja_que_asoma_un_pixel_del_original_sigue_rotulada_al_reducir() -> None:
    """Revisión de Codex: 1 px de 1920 queda en ⅓ px al reducir a 640; la caja sigue dentro."""
    caja = Caja(1919 / 1920, 0.4, 1.0, 0.6)
    vista = componer_vista(
        fondo(128, (1080, 1920)), [Deteccion(T0, 0, ClaseDetectada.CABEZA, caja, 0.9)]
    )
    assert vista.shape[1] == 640
    assert _blancos(vista) > 20


@pytest.mark.parametrize("sobra", [-1, 0, 1])
def test_el_rotulo_solo_va_si_cabe_a_lo_ancho(sobra: int) -> None:
    """Cuadro un píxel más angosto que el rótulo, justo de su ancho y uno más ancho."""
    (w, _), _ = cv2.getTextSize("SIN CASCO", cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    ancho = w + 2 * 3 + sobra
    caja = Caja(0.0, 0.5, 1.0, 0.7)
    vista = componer_vista(
        fondo(128, (ALTO, ancho)), [Deteccion(T0, 0, ClaseDetectada.CABEZA, caja, 0.9)]
    )
    assert (_blancos(vista) > 20) == (sobra >= 0)


def test_la_etiqueta_no_se_sale_del_cuadro() -> None:
    """Una caja pegada a la esquina de abajo a la derecha: el rótulo entra completo."""
    caja = Caja(0.97, 0.97, 1.0, 1.0)
    vista = componer_vista(fondo(128), [Deteccion(T0, 0, ClaseDetectada.SIN_CHALECO, caja, 0.9)])
    alto = _alto_rotulo("SIN CHALECO")
    (ancho, _), _ = cv2.getTextSize("SIN CHALECO", cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    rotulo = vista[ALTO - alto :, ANCHO - ancho - 6 :]
    assert _blancos(rotulo) > 20
    # La esquina de arriba a la izquierda del rótulo es roja: entró entero, sin recortarse.
    assert _rojo(vista[ALTO - alto, ANCHO - ancho - 5])
    assert vista.shape[:2] == (ALTO, ANCHO)


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
