"""Seguidores: identidad solo para personas, buffer en segundos.

La batería común la pasan los dos (`SeguidorIoU` y `SeguidorByteTrack`): cambiar de
seguidor no cambia lo que ven el agregador y la base. Al final, lo propio de ByteTrack.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_vision import Seguidor
from gepp_vision.seguimiento import SeguidorByteTrack, SeguidorIoU

from .conftest import PERSONA, T0

SEGUIDORES = {"iou": SeguidorIoU, "bytetrack": SeguidorByteTrack}


@pytest.fixture(params=sorted(SEGUIDORES))
def fabrica(request: pytest.FixtureRequest) -> Callable[..., Seguidor]:
    return SEGUIDORES[request.param]


def _det(
    t: float,
    caja: Caja = PERSONA,
    clase: ClaseDetectada = ClaseDetectada.PERSONA,
    confianza: float = 0.9,
) -> Deteccion:
    return Deteccion(
        capture_ts=T0 + timedelta(seconds=t),
        cuadro_idx=round(t * 5),
        clase=clase,
        caja=caja,
        confianza=confianza,
    )


def _mover(caja: Caja, dx: float) -> Caja:
    return Caja(caja.x1 + dx, caja.y1, caja.x2 + dx, caja.y2)


def test_cumple_el_protocolo(fabrica: Callable[..., Seguidor]) -> None:
    assert isinstance(fabrica(), Seguidor)


def test_una_persona_que_camina_a_5_fps_conserva_su_identidad(
    fabrica: Callable[..., Seguidor],
) -> None:
    """Se desplaza un tercio de su ancho por cuadro: IoU ~0,5, bajo el 0,7 de los
    seguidores de 30 fps y sobre el 0,15 que usa este."""
    seguidor = fabrica()
    ids = set()
    for n in range(10):
        (d,) = seguidor.actualizar([_det(n * 0.2, _mover(PERSONA, n * 0.04))])
        ids.add(d.track_id)
    assert ids == {1}


def test_dos_personas_separadas_reciben_identidades_distintas(
    fabrica: Callable[..., Seguidor],
) -> None:
    seguidor = fabrica()
    otra = _mover(PERSONA, 0.3)
    for n in range(3):
        a, b = seguidor.actualizar([_det(n * 0.2), _det(n * 0.2, otra)])
        assert (a.track_id, b.track_id) == (1, 2)


def test_los_epp_salen_sin_identidad(fabrica: Callable[..., Seguidor]) -> None:
    """El agregador asocia el EPP a la persona por geometría; si el seguidor le pusiera
    identidad, el EPP pasaría por persona en la tabla cruda."""
    seguidor = fabrica()
    casco = Caja(0.44, 0.21, 0.48, 0.27)
    salida = seguidor.actualizar([_det(0), _det(0, casco, ClaseDetectada.CASCO)])
    assert [d.track_id for d in salida] == [1, None]


def test_un_epp_que_llega_con_identidad_sale_sin_ella(fabrica: Callable[..., Seguidor]) -> None:
    """Un detector que por error numere los cascos no puede colar esa identidad."""
    casco = replace(_det(0, Caja(0.44, 0.21, 0.48, 0.27), ClaseDetectada.CASCO), track_id=7)
    salida = fabrica().actualizar([_det(0), casco])
    assert [d.track_id for d in salida] == [1, None]


def test_el_buffer_se_mide_en_segundos(fabrica: Callable[..., Seguidor]) -> None:
    seguidor = fabrica(track_buffer_segundos=1.0)
    seguidor.actualizar([_det(0.0)])
    # Oclusión de 0,8 s: la persona recupera su identidad.
    assert seguidor.actualizar([_det(0.8)])[0].track_id == 1
    # Ausencia de 1,2 s desde la última vez: es otra persona para el sistema.
    assert seguidor.actualizar([_det(2.0)])[0].track_id == 2


def test_reiniciar_vuelve_a_contar_desde_uno(fabrica: Callable[..., Seguidor]) -> None:
    """Identificadores efímeros: no se arrastran entre videos (ADR-006)."""
    seguidor = fabrica()
    seguidor.actualizar([_det(0), _det(0, _mover(PERSONA, 0.3))])
    seguidor.reiniciar()
    assert seguidor.actualizar([_det(10)])[0].track_id == 1


def test_el_iou_valida_sus_parametros() -> None:
    with pytest.raises(ValueError):
        SeguidorIoU(iou_minimo=0)
    with pytest.raises(ValueError):
        SeguidorIoU(track_buffer_segundos=-1)
    assert SeguidorIoU().actualizar([]) == []


# ── Lo propio de ByteTrack ────────────────────────────────────────────────────────────


def test_bytetrack_valida_sus_parametros() -> None:
    with pytest.raises(ValueError):
        SeguidorByteTrack(iou_minimo=0)
    with pytest.raises(ValueError):
        SeguidorByteTrack(umbral_bajo=0.6, umbral_alto=0.5)
    with pytest.raises(ValueError):
        SeguidorByteTrack(track_buffer_segundos=-1)
    assert SeguidorByteTrack().actualizar([]) == []


@pytest.mark.parametrize("fps", [5, 10])
def test_quien_pasa_detras_de_una_columna_conserva_su_identidad(fps: int) -> None:
    """Camina 0,2 del ancho del cuadro por segundo y desaparece 0,6 s. Al volver está 0,12
    más allá: sin solape con la última caja vista. El IoU la da por otra persona; ByteTrack
    la encuentra donde el filtro de Kalman la predijo. A 5 y a 10 fps, igual (ADR-005)."""
    paso = 1 / fps
    visibles = [n * paso for n in range(round(1.0 * fps))]  # 1 s a la vista
    ocultos = round(0.6 * fps)
    despues = [(len(visibles) + ocultos + n) * paso for n in range(round(0.6 * fps))]
    ids: dict[str, set[int | None]] = {}
    for nombre, fabrica_ in SEGUIDORES.items():
        seguidor = fabrica_()
        vistos = set()
        for t in visibles + despues:
            (d,) = seguidor.actualizar([_det(t, _mover(PERSONA, 0.2 * t))])
            vistos.add(d.track_id)
        ids[nombre] = vistos
    assert ids["bytetrack"] == {1}
    assert len(ids["iou"]) > 1  # el caso que justifica ByteTrack


def test_una_deteccion_de_confianza_baja_mantiene_viva_la_identidad() -> None:
    """Parcialmente tapada, la persona baja a 0,3: sigue siendo la misma."""
    seguidor = SeguidorByteTrack()
    seguidor.actualizar([_det(0.0)])
    (d,) = seguidor.actualizar([_det(0.2, _mover(PERSONA, 0.01), confianza=0.3)])
    assert d.track_id == 1


def test_una_deteccion_de_confianza_baja_no_crea_identidades() -> None:
    seguidor = SeguidorByteTrack()
    (d,) = seguidor.actualizar([_det(0.0, confianza=0.3)])
    assert d.track_id is None
    assert seguidor.actualizar([_det(0.2)])[0].track_id == 1  # el primero real es el 1


def test_dos_personas_que_se_cruzan_no_intercambian_identidad() -> None:
    """Una va a la derecha y otra a la izquierda; se cruzan a mitad de camino. El filtro de
    Kalman sabe hacia dónde iba cada una."""
    seguidor = SeguidorByteTrack()
    izquierda = Caja(0.10, 0.2, 0.22, 0.8)
    derecha = Caja(0.70, 0.2, 0.82, 0.8)
    for n in range(16):
        t = n * 0.2
        a, b = seguidor.actualizar(
            [_det(t, _mover(izquierda, 0.12 * t)), _det(t, _mover(derecha, -0.12 * t))]
        )
        assert (a.track_id, b.track_id) == (1, 2), f"intercambio en t={t:.1f}"
