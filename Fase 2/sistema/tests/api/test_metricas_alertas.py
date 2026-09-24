"""El presupuesto de avisos queda MEDIDO en /metrics, junto con la tasa de accionables."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

from .conftest import Cliente

pytestmark = pytest.mark.integration


def _metrica(api: Cliente, nombre: str) -> list[str]:
    cuerpo = api.http.get("/metrics").text
    return [linea for linea in cuerpo.splitlines() if linea.startswith(nombre)]


def test_presupuesto_y_tasa_de_accionables(api: Cliente, datos: dict[str, Any], bd: Any) -> None:
    a, b = datos["hallazgos"]
    with bd.begin() as c:
        for i, h in enumerate((a, b)):
            c.execute(
                text(
                    "INSERT INTO notificacion (hallazgo_id, tipo, canal, destinatario, cuerpo,"
                    " estado, enviada_en, id_externo) VALUES (:h, 'inmediata', 'telegram',"
                    " 'chat-1', '{}',"
                    " 'enviada', now(), :e)"
                ),
                {"h": h, "e": str(i)},
            )
        c.execute(
            text(
                "INSERT INTO accion_correctiva (hallazgo_id, responsable_id, descripcion, plazo)"
                " VALUES (:h, 1, 'Reponer casco', '2026-09-30')"
            ),
            {"h": a},
        )
    assert _metrica(api, "gepp_presupuesto_avisos_turno ") == ["gepp_presupuesto_avisos_turno 6.0"]
    (turno,) = _metrica(api, "gepp_avisos_inmediatos_turno{")
    assert turno.endswith(" 2.0")
    assert _metrica(api, "gepp_alertas_accionables_ratio ") == [
        "gepp_alertas_accionables_ratio 0.5"
    ]
    assert any(
        'tipo="inmediata"' in m and 'estado="enviada"' in m for m in _metrica(api, "gepp_avisos{")
    )


def test_sin_avisos_no_se_inventa_una_tasa(api: Cliente) -> None:
    assert _metrica(api, "gepp_alertas_accionables_ratio ") == []
