"""El casco tiene que estar en la cabeza, no en cualquier parte del cuadro."""

from __future__ import annotations

from datetime import UTC, datetime

from gepp_core import Caja, ClaseDetectada, Deteccion, TipoEPP, epp_faltante, epp_puesto

from .conftest import PERSONA, caja_en_franja, cuadro

T0 = datetime(2026, 9, 2, 2, 10, 0, tzinfo=UTC)
EXIGIDO = frozenset({TipoEPP.CASCO, TipoEPP.CHALECO})


def test_persona_completa_no_tiene_faltantes() -> None:
    dets = cuadro(t=0, idx=0)
    assert epp_faltante(dets[0], dets, EXIGIDO) == set()


def test_persona_sin_casco_lo_reporta() -> None:
    dets = cuadro(t=0, idx=0, con_casco=False)
    assert epp_faltante(dets[0], dets, EXIGIDO) == {TipoEPP.CASCO}


def test_casco_a_la_altura_de_los_pies_no_cuenta_como_puesto() -> None:
    """Un casco colgando del brazo o apoyado en el suelo no es un casco puesto."""
    dets = cuadro(t=0, idx=0, con_casco=False)
    dets.append(
        Deteccion(
            capture_ts=T0,
            cuadro_idx=0,
            clase=ClaseDetectada.CASCO,
            caja=caja_en_franja(PERSONA, 0.85, 0.98),
            confianza=0.95,
        )
    )
    assert epp_faltante(dets[0], dets, EXIGIDO) == {TipoEPP.CASCO}


def test_casco_de_otra_persona_no_se_le_atribuye() -> None:
    """Con dos personas en el cuadro, cada casco va a su dueño."""
    otra = Caja(0.70, 0.20, 0.82, 0.80)
    dets = cuadro(t=0, idx=0, con_casco=False)
    dets.append(
        Deteccion(
            capture_ts=T0,
            cuadro_idx=0,
            clase=ClaseDetectada.CASCO,
            caja=caja_en_franja(otra, 0.02, 0.18),
            confianza=0.95,
        )
    )
    assert epp_faltante(dets[0], dets, EXIGIDO) == {TipoEPP.CASCO}


def test_deteccion_bajo_el_umbral_de_confianza_se_ignora() -> None:
    dets = cuadro(t=0, idx=0, confianza=0.30)
    assert epp_puesto(dets[0], dets, confianza_minima=0.45) == set()
