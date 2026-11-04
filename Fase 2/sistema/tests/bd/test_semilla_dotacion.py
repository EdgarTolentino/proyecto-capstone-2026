"""La dotación SINTÉTICA que siembra el perfil de construcción (KPI 7, demostración)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Area, Dotacion
from gepp_bd.semilla import PerfilInvalido, cargar, leer
from sqlalchemy import Engine, func, select

pytestmark = pytest.mark.integration

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"


def _hoy(zona: str) -> Any:
    return datetime.now(ZoneInfo(zona)).date()


def test_cada_fila_trae_sus_conteos_y_los_dias_consecutivos_hasta_hoy_en_la_faena(
    bd: Engine,
) -> None:
    perfil = leer(PERFIL)
    assert perfil["dotacion"]["origen"] == "sintetica"
    hoy = _hoy(perfil["faena"]["zona_horaria"])
    dias = perfil["dotacion"]["dias"]
    with transaccion(bd) as s:
        cargar(s, perfil)
        areas = dict(s.execute(select(Area.nombre, Area.id)).tuples().all())
        todas = s.scalars(select(Dotacion)).all()
        assert len(todas) == len(perfil["dotacion"]["filas"]) * dias
        for f in perfil["dotacion"]["filas"]:
            filas = [d for d in todas if d.area_id == areas[f["area"]] and d.turno == f["turno"]]
            # Treinta fechas seguidas, la última es el «hoy» de la faena: ni saltos ni huecos.
            assert {d.fecha for d in filas} == {hoy - timedelta(days=k) for k in range(dias)}
            assert {(d.n_hombres, d.n_mujeres, d.n_otro) for d in filas} == {
                (f["hombres"], f["mujeres"], f.get("otro", 0))
            }
        assert any(d.n_mujeres < 5 for d in todas)  # para que se vea la supresión
    with transaccion(bd) as s:
        cargar(s, perfil)  # faena ya sembrada: no duplica
        assert s.scalar(select(func.count()).select_from(Dotacion)) == len(todas)


@pytest.mark.parametrize("zona", ["Pacific/Kiritimati", "Pacific/Pago_Pago"])
def test_hoy_es_el_de_la_zona_horaria_de_la_faena_no_el_del_servidor(bd: Engine, zona: str) -> None:
    # +14 h y -11 h: a cualquier hora los dos «hoy» difieren; el del servidor no acierta ambos.
    perfil = leer(PERFIL)
    perfil["faena"]["zona_horaria"] = zona
    with transaccion(bd) as s:
        cargar(s, perfil)
        assert s.scalar(select(func.max(Dotacion.fecha))) == _hoy(zona)


def test_la_semilla_rechaza_dotacion_que_no_declara_ser_sintetica(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["dotacion"]["origen"] = "nomina"
    with transaccion(bd) as s, pytest.raises(PerfilInvalido, match="sintetica"):
        cargar(s, perfil)


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("turno", "C"),
        ("hombres", -1),
        ("mujeres", 1.5),
        ("otro", -1),
        ("hombres", True),  # bool es int en Python: no vale como conteo
        ("mujeres", "4"),
    ],
)
def test_la_semilla_rechaza_turnos_y_conteos_invalidos(bd: Engine, clave: str, valor: Any) -> None:
    perfil = leer(PERFIL)
    perfil["dotacion"]["filas"][0][clave] = valor
    with transaccion(bd) as s, pytest.raises(PerfilInvalido, match=clave):
        cargar(s, perfil)


def test_el_cero_y_el_turno_b_son_validos(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["dotacion"]["filas"][0].update(turno="B", hombres=0, mujeres=0, otro=0)
    with transaccion(bd) as s:
        cargar(s, perfil)


@pytest.mark.parametrize("dias", [1.9, -1, 0, True, "30"])
def test_la_semilla_rechaza_dias_que_no_son_un_entero_positivo(bd: Engine, dias: Any) -> None:
    perfil = leer(PERFIL)
    perfil["dotacion"]["dias"] = dias
    with transaccion(bd) as s, pytest.raises(PerfilInvalido, match="dias"):
        cargar(s, perfil)


def test_un_solo_dia_es_valido_y_siembra_solo_hoy(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["dotacion"]["dias"] = 1
    with transaccion(bd) as s:
        cargar(s, perfil)
        assert s.scalar(select(func.count(func.distinct(Dotacion.fecha)))) == 1
