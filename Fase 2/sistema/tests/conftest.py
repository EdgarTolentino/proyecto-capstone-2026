from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion, Regla, Severidad, TipoEPP

#: Instante de referencia fijo. Nunca datetime.now() en un test: los tests deben ser
#: deterministas, y además el proyecto prohíbe fechar desde el reloj de proceso (ADR-005).
T0 = datetime(2026, 9, 2, 2, 10, 0, tzinfo=UTC)

#: Persona de pie, ocupando la mitad vertical del cuadro.
PERSONA = Caja(0.40, 0.20, 0.52, 0.80)


@pytest.fixture
def regla() -> Regla:
    return Regla(
        id=1,
        version=1,
        nombre="Casco y chaleco obligatorios en chancado",
        epp_exigido=frozenset({TipoEPP.CASCO, TipoEPP.CHALECO}),
        severidad=Severidad.ALTA,
        confirmacion_segundos=2.0,
        cierre_segundos=3.0,
    )


def en(segundos: float) -> datetime:
    return T0 + timedelta(seconds=segundos)


def caja_en_franja(persona: Caja, desde: float, hasta: float, escala: float = 0.5) -> Caja:
    """Caja pequeña centrada en una franja vertical de la persona."""
    franja = persona.franja(desde, hasta)
    cx, cy = franja.centro
    mx, my = franja.ancho * escala / 2, franja.alto * escala / 2
    return Caja(cx - mx, cy - my, cx + mx, cy + my)


def cuadro(
    *,
    t: float,
    idx: int,
    con_casco: bool = True,
    con_chaleco: bool = True,
    track_id: int = 1,
    persona: Caja = PERSONA,
    confianza: float = 0.90,
) -> list[Deteccion]:
    """Fabrica las detecciones de un cuadro para una persona."""
    dets = [
        Deteccion(
            capture_ts=en(t),
            cuadro_idx=idx,
            clase=ClaseDetectada.PERSONA,
            caja=persona,
            confianza=confianza,
            track_id=track_id,
        )
    ]
    if con_casco:
        dets.append(
            Deteccion(
                capture_ts=en(t),
                cuadro_idx=idx,
                clase=ClaseDetectada.CASCO,
                caja=caja_en_franja(persona, 0.02, 0.18),
                confianza=confianza,
            )
        )
    if con_chaleco:
        dets.append(
            Deteccion(
                capture_ts=en(t),
                cuadro_idx=idx,
                clase=ClaseDetectada.CHALECO,
                caja=caja_en_franja(persona, 0.30, 0.55),
                confianza=confianza,
            )
        )
    return dets
