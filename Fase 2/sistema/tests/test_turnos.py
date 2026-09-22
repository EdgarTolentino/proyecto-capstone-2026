"""El turno en curso, en hora local de la faena, en sus bordes (regla 7)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from gepp_bd.turnos import turno_en_curso

TZ = ZoneInfo("America/Santiago")


@pytest.mark.parametrize(
    ("hora", "codigo", "inicio"),
    [
        (datetime(2026, 9, 22, 8, 0, tzinfo=TZ), "A", datetime(2026, 9, 22, 8, 0, tzinfo=TZ)),
        (datetime(2026, 9, 22, 19, 59, tzinfo=TZ), "A", datetime(2026, 9, 22, 8, 0, tzinfo=TZ)),
        (datetime(2026, 9, 22, 20, 0, tzinfo=TZ), "B", datetime(2026, 9, 22, 20, 0, tzinfo=TZ)),
        # Pasada la medianoche el turno B empezó AYER.
        (datetime(2026, 9, 23, 3, 0, tzinfo=TZ), "B", datetime(2026, 9, 22, 20, 0, tzinfo=TZ)),
        (datetime(2026, 9, 23, 7, 59, tzinfo=TZ), "B", datetime(2026, 9, 22, 20, 0, tzinfo=TZ)),
    ],
)
def test_turno_en_curso(hora: datetime, codigo: str, inicio: datetime) -> None:
    t, desde = turno_en_curso(hora.astimezone(ZoneInfo("UTC")), "America/Santiago")
    assert (t.codigo, desde) == (codigo, inicio)
