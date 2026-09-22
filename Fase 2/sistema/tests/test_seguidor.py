"""Seguidor por IoU: identidad solo para personas, buffer en segundos."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_vision import Seguidor
from gepp_vision.seguimiento import SeguidorIoU

from .conftest import PERSONA, T0


def _det(
    t: float, caja: Caja = PERSONA, clase: ClaseDetectada = ClaseDetectada.PERSONA
) -> Deteccion:
    return Deteccion(
        capture_ts=T0 + timedelta(seconds=t),
        cuadro_idx=round(t * 5),
        clase=clase,
        caja=caja,
        confianza=0.9,
    )


def _mover(caja: Caja, dx: float) -> Caja:
    return Caja(caja.x1 + dx, caja.y1, caja.x2 + dx, caja.y2)


def test_cumple_el_protocolo() -> None:
    assert isinstance(SeguidorIoU(), Seguidor)


def test_una_persona_que_camina_a_5_fps_conserva_su_identidad() -> None:
    """Se desplaza un tercio de su ancho por cuadro: IoU ~0,5, bajo el 0,7 de los
    seguidores de 30 fps y sobre el 0,15 que usa este."""
    seguidor = SeguidorIoU()
    ids = set()
    for n in range(10):
        (d,) = seguidor.actualizar([_det(n * 0.2, _mover(PERSONA, n * 0.04))])
        ids.add(d.track_id)
    assert ids == {1}


def test_dos_personas_separadas_reciben_identidades_distintas() -> None:
    seguidor = SeguidorIoU()
    otra = _mover(PERSONA, 0.3)
    for n in range(3):
        a, b = seguidor.actualizar([_det(n * 0.2), _det(n * 0.2, otra)])
        assert (a.track_id, b.track_id) == (1, 2)


def test_los_epp_salen_sin_identidad() -> None:
    """El agregador asocia el EPP a la persona por geometría; si el seguidor le pusiera
    identidad, el EPP pasaría por persona en la tabla cruda."""
    seguidor = SeguidorIoU()
    casco = Caja(0.44, 0.21, 0.48, 0.27)
    salida = seguidor.actualizar([_det(0), _det(0, casco, ClaseDetectada.CASCO)])
    assert [d.track_id for d in salida] == [1, None]


def test_un_epp_que_llega_con_identidad_sale_sin_ella() -> None:
    """Un detector que por error numere los cascos no puede colar esa identidad."""
    casco = replace(_det(0, Caja(0.44, 0.21, 0.48, 0.27), ClaseDetectada.CASCO), track_id=7)
    salida = SeguidorIoU().actualizar([_det(0), casco])
    assert [d.track_id for d in salida] == [1, None]


def test_el_buffer_se_mide_en_segundos() -> None:
    seguidor = SeguidorIoU(track_buffer_segundos=1.0)
    seguidor.actualizar([_det(0.0)])
    # Oclusión de 0,8 s: la persona recupera su identidad.
    assert seguidor.actualizar([_det(0.8)])[0].track_id == 1
    # Ausencia de 1,2 s desde la última vez: es otra persona para el sistema.
    assert seguidor.actualizar([_det(2.0)])[0].track_id == 2


def test_reiniciar_vuelve_a_contar_desde_uno() -> None:
    """Identificadores efímeros: no se arrastran entre videos (ADR-006)."""
    seguidor = SeguidorIoU()
    seguidor.actualizar([_det(0), _det(0, _mover(PERSONA, 0.3))])
    seguidor.reiniciar()
    assert seguidor.actualizar([_det(10)])[0].track_id == 1


def test_valida_sus_parametros() -> None:
    with pytest.raises(ValueError):
        SeguidorIoU(iou_minimo=0)
    with pytest.raises(ValueError):
        SeguidorIoU(track_buffer_segundos=-1)
    assert SeguidorIoU().actualizar([]) == []
