"""La dotación SINTÉTICA que siembra el perfil de construcción (KPI 7, demostración)."""

from __future__ import annotations

from pathlib import Path

import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Dotacion
from gepp_bd.semilla import PerfilInvalido, cargar, leer
from sqlalchemy import Engine, func, select

pytestmark = pytest.mark.integration

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"


def test_la_semilla_trae_dotacion_sintetica_con_conteos_bajo_cinco_y_es_idempotente(
    bd: Engine,
) -> None:
    perfil = leer(PERFIL)
    assert perfil["dotacion"]["origen"] == "sintetica"
    with transaccion(bd) as s:
        cargar(s, perfil)
        filas = s.scalars(select(Dotacion)).all()
        assert len(filas) == len(perfil["dotacion"]["filas"]) * perfil["dotacion"]["dias"]
        assert any(f.n_mujeres < 5 for f in filas)  # para que se vea la supresión
        hoy = s.scalar(select(func.current_date()))
        assert max(f.fecha for f in filas) == hoy
    with transaccion(bd) as s:
        cargar(s, perfil)  # faena ya sembrada: no duplica
        assert s.scalar(select(func.count()).select_from(Dotacion)) == len(filas)


def test_la_semilla_rechaza_dotacion_que_no_declara_ser_sintetica(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["dotacion"]["origen"] = "nomina"
    with transaccion(bd) as s, pytest.raises(PerfilInvalido, match="sintetica"):
        cargar(s, perfil)
