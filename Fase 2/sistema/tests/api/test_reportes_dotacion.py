"""KPI 7: incumplimientos por cada 100 trabajadores de la dotación, con supresión n < 5.

Dato ADMINISTRATIVO sembrado a mano; no se cruza con personas detectadas. La ventana cubre del
31-ago al 2-sep en la faena (UTC-4); T0 (02:10Z) cae en el turno B y T0 + 14 h en el A.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from gepp_api.app import crear_app
from gepp_bd import transaccion
from gepp_bd.modelos import Dotacion
from gepp_bd.repositorios import hallazgos
from gepp_bd.semilla import cargar, leer
from gepp_core import Hallazgo, Severidad, TipoEPP
from sqlalchemy import Engine

from ..conftest import T0
from .conftest import PERFIL, Cliente

pytestmark = pytest.mark.integration

SUPERVISOR = {"Authorization": "Bearer super"}
VENTANA = "desde=2026-09-01T00:00:00Z&hasta=2026-09-03T00:00:00Z"
RUTA = f"/reportes/dotacion?{VENTANA}"
ACCESO = "Acceso y patio de materiales"
OBRA_GRUESA = "Frente de obra gruesa"
DIAS = (date(2026, 8, 31), date(2026, 9, 1), date(2026, 9, 2))
TURNO_B = T0
TURNO_A = T0 + timedelta(hours=14)


@pytest.fixture(autouse=True)
def _tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GEPP_API_TOKENS", "demo=prevencionista@obra.invalid,super=supervisor.acceso@obra.invalid"
    )


@pytest.fixture
def api(bd: Engine) -> Iterator[Cliente]:
    """Solo el perfil sembrado: sin hallazgos, para contar exactamente los de cada prueba."""
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
        # La semilla trae dotación sintética de HOY: aquí se parte de cero y se siembra a mano.
        s.query(Dotacion).delete()
    with TestClient(crear_app(motor=bd)) as c:
        yield Cliente(c)


def _hallazgos(bd: Engine, area_id: int, n: int, ts: Any) -> None:
    with transaccion(bd) as s:
        for i in range(n):
            inicio = ts + timedelta(minutes=i)
            hallazgos.guardar(
                s,
                Hallazgo(
                    track_id=i + 1,
                    regla_id=area_id,
                    regla_version=1,
                    epp_faltante=frozenset({TipoEPP.CASCO}),
                    severidad=Severidad.ALTA,
                    ts_inicio=inicio,
                    ts_fin=inicio + timedelta(seconds=10),
                    cuadros_confirmados=50,
                    confianza_media=0.8,
                ),
                hallazgos.Contexto(fuente_id=area_id, area_id=area_id),
            )


def _dotacion_dias(
    bd: Engine, area_id: int, turno: str, dias: dict[date, tuple[int, int, int]]
) -> None:
    with transaccion(bd) as s:
        for fecha, (h, m, o) in dias.items():
            s.add(
                Dotacion(
                    area_id=area_id, fecha=fecha, turno=turno, n_hombres=h, n_mujeres=m, n_otro=o
                )
            )


def _dotacion(bd: Engine, area_id: int, turno: str, h: int, m: int, o: int) -> None:
    _dotacion_dias(bd, area_id, turno, dict.fromkeys(DIAS, (h, m, o)))


def _filas(api: Cliente, ruta: str = RUTA) -> dict[str, Any]:
    return {f["etiqueta"]: f for f in api.llamar("obtenerReporte", "GET", ruta)["filas"]}


def test_la_tasa_es_incumplimientos_por_cada_100_de_la_dotacion(api: Cliente, bd: Engine) -> None:
    _hallazgos(bd, 1, 10, TURNO_A)
    _dotacion(bd, 1, "A", 24, 8, 8)  # total 40
    fila = _filas(api)[f"{ACCESO} · Turno A"]
    assert fila["valor"] == 25.0  # 10 * 100 / 40, exacto en binario
    assert fila["n"] == 10 and fila["datos_insuficientes"] is False


@pytest.mark.parametrize(("hombres", "visible"), [(4, False), (5, True), (6, True)])
def test_el_total_de_la_dotacion_se_suprime_justo_bajo_cinco(
    api: Cliente, bd: Engine, hombres: int, visible: bool
) -> None:
    _hallazgos(bd, 1, 15, TURNO_A)  # 15 ya es múltiplo de 5: el n publicado es 15
    _dotacion(bd, 1, "A", hombres, 0, 0)
    fila = _filas(api)[f"{ACCESO} · Turno A"]
    assert fila["n"] == 15  # los eventos se ven; lo que se suprime son las personas
    if visible:
        assert fila["valor"] == 1500 / hombres and fila["datos_insuficientes"] is False
    else:  # sin total no hay tasa: con el n visible, el valor delataría el total
        assert fila["valor"] is None and fila["razon"] == "dotacion_insuficiente"


@pytest.mark.parametrize(("n", "valor"), [(4, None), (5, 12.5), (10, 25.0)])
def test_los_incumplimientos_se_suprimen_justo_bajo_cinco(
    api: Cliente, bd: Engine, n: int, valor: float | None
) -> None:
    _hallazgos(bd, 1, n, TURNO_A)
    _dotacion(bd, 1, "A", 20, 10, 10)  # total 40
    fila = _filas(api)[f"{ACCESO} · Turno A"]
    assert fila["valor"] == valor
    if valor is None:
        assert fila["n"] is None and fila["razon"] == "n_insuficiente"
        assert fila["datos_insuficientes"] is True
    else:
        assert fila["n"] == n and "razon" not in fila


@pytest.mark.parametrize(
    ("eventos", "publicado", "valor"), [(6, 5, 12.5), (7, 5, 12.5), (8, 10, 25.0), (9, 10, 25.0)]
)
def test_la_tasa_sale_del_n_publicado_no_del_exacto(
    api: Cliente, bd: Engine, eventos: int, publicado: int, valor: float
) -> None:
    _hallazgos(bd, 1, eventos, TURNO_A)
    _dotacion(bd, 1, "A", 20, 10, 10)  # total 40
    fila = _filas(api)[f"{ACCESO} · Turno A"]
    assert fila["n"] == publicado and fila["valor"] == valor


def test_un_area_sin_dotacion_no_inventa_una_tasa(api: Cliente, bd: Engine) -> None:
    _hallazgos(bd, 2, 10, TURNO_A)
    fila = _filas(api)[f"{OBRA_GRUESA} · Turno A"]
    assert fila["valor"] is None and fila["razon"] == "sin_dotacion"
    assert fila["n"] == 10 and fila["datos_insuficientes"] is True


def test_el_area_filtra_como_los_otros_reportes(api: Cliente, bd: Engine) -> None:
    for area, turno_dia in ((1, TURNO_A), (2, TURNO_A)):
        _hallazgos(bd, area, 10, turno_dia)
        _dotacion(bd, area, "A", 24, 8, 8)
    todas = set(_filas(api))
    assert todas == {f"{ACCESO} · Turno A", f"{OBRA_GRUESA} · Turno A"}
    assert set(_filas(api, f"{RUTA}&area_id=1")) == {f"{ACCESO} · Turno A"}
    assert set(_filas(api, f"{RUTA}&area_id=2")) == {f"{OBRA_GRUESA} · Turno A"}


def test_permisos_segmentacion_y_csv(api: Cliente, bd: Engine) -> None:
    api.llamar("obtenerReporte", "GET", RUTA, headers=SUPERVISOR, esperado=403)
    api.llamar("obtenerReporte", "GET", f"{RUTA}&segmentacion=turno")
    api.llamar("obtenerReporte", "GET", f"{RUTA}&segmentacion=zona", esperado=422)
    _hallazgos(bd, 1, 4, TURNO_A)
    _dotacion(bd, 1, "A", 20, 10, 10)
    r = api.http.get(
        f"/api/v1/reportes/dotacion?{VENTANA}&formato=csv",
        headers={"Authorization": "Bearer demo"},
    )
    assert r.status_code == 200
    assert f"{ACCESO} · Turno A,,,true" in r.text


@pytest.mark.parametrize(
    "dias",
    [
        # Totales diarios 4 y 4: promediar cada categoría redondeada daría (2, 2, 1) = 5 y tasa.
        [(1, 1, 2), (2, 2, 0)],
        # Un solo día con menos de 5 basta, aunque el promedio sea alto.
        [(20, 10, 10), (2, 1, 1)],
    ],
)
def test_un_dia_con_menos_de_cinco_personas_quita_la_tasa(
    api: Cliente, bd: Engine, dias: list[tuple[int, int, int]]
) -> None:
    _hallazgos(bd, 1, 10, TURNO_A)
    _dotacion_dias(bd, 1, "A", {date(2026, 9, 1): dias[0], date(2026, 9, 2): dias[1]})
    fila = _filas(api)[f"{ACCESO} · Turno A"]
    assert fila["valor"] is None and fila["razon"] == "dotacion_insuficiente"


def test_la_dotacion_del_periodo_es_el_promedio_de_los_totales_diarios(
    api: Cliente, bd: Engine
) -> None:
    # Dos días con 60 y 20 personas: el promedio es 40, no el del primer día.
    _hallazgos(bd, 1, 10, TURNO_A)
    dias = {date(2026, 9, 1): (30, 20, 10), date(2026, 9, 2): (10, 5, 5)}
    dias[date(2026, 8, 31)] = (50, 25, 25)  # el A del 31-ago termina justo al abrir la ventana
    _dotacion_dias(bd, 1, "A", dias)
    fila = _filas(api)[f"{ACCESO} · Turno A"]
    assert fila["valor"] == 25.0 and fila["dotacion"]["total"] == 40  # 10 * 100 / 40


def test_incumplimientos_en_un_dia_sin_dotacion_no_se_dividen_entre_otros_dias(
    api: Cliente, bd: Engine
) -> None:
    _hallazgos(bd, 1, 5, TURNO_A)  # 2-sep, con dotación
    _hallazgos(bd, 1, 5, TURNO_A - timedelta(days=1))  # 1-sep, sin registro
    _dotacion_dias(bd, 1, "A", {date(2026, 9, 2): (20, 10, 10)})
    fila = _filas(api)[f"{ACCESO} · Turno A"]
    assert fila["n"] == 10  # los eventos sí se publican
    assert fila["valor"] is None and fila["razon"] == "dotacion_incompleta"


# Ventanas en hora de la faena (UTC-4). El turno B del 1-sep va de las 20:00 a las 08:00 del 2.
def _ventana(desde: str, hasta: str) -> str:
    return f"/reportes/dotacion?desde={desde}&hasta={hasta}"


def test_la_ventana_de_un_turno_no_suma_la_dotacion_de_la_noche_siguiente(
    api: Cliente, bd: Engine
) -> None:
    _hallazgos(bd, 1, 5, TURNO_B)  # 22:10 del 1-sep
    _hallazgos(bd, 1, 5, TURNO_B + timedelta(hours=3))  # 01:10 del 2-sep
    _dotacion_dias(bd, 1, "B", {date(2026, 9, 1): (10, 5, 5), date(2026, 9, 2): (50, 25, 25)})
    # [1-sep 20:00, 2-sep 08:00): solo toca el turno B del 1-sep (20 personas).
    fila = _filas(api, _ventana("2026-09-02T00:00:00Z", "2026-09-02T12:00:00Z"))
    assert fila[f"{ACCESO} · Turno B"]["valor"] == 50.0  # no 10 * 100 / 60
    # En [31-ago 20:00, 2-sep 20:00) el turno B del 2-sep empieza justo al cierre: no entra.
    assert _filas(api)[f"{ACCESO} · Turno B"]["valor"] == 50.0


def test_una_ventana_de_madrugada_usa_la_dotacion_del_turno_que_empezo_el_dia_anterior(
    api: Cliente, bd: Engine
) -> None:
    _hallazgos(bd, 1, 5, TURNO_B + timedelta(hours=3))  # 01:10 del 2-sep
    _dotacion_dias(bd, 1, "B", {date(2026, 9, 1): (10, 5, 5)})
    # [2-sep 00:00, 08:00): el turno B del 1-sep, aunque la fecha calendario sea el 2.
    fila = _filas(api, _ventana("2026-09-02T04:00:00Z", "2026-09-02T12:00:00Z"))
    assert fila[f"{ACCESO} · Turno B"]["valor"] == 25.0  # 5 * 100 / 20


def test_un_dia_completo_toma_la_dotacion_de_sus_turnos_y_no_la_de_los_vecinos(
    api: Cliente, bd: Engine
) -> None:
    _hallazgos(bd, 1, 10, TURNO_A - timedelta(days=1))  # mediodía del 1-sep
    _dotacion_dias(bd, 1, "A", {d: (50, 25, 25) for d in (date(2026, 8, 31), date(2026, 9, 2))})
    _dotacion_dias(bd, 1, "A", {date(2026, 9, 1): (20, 10, 10)})
    fila = _filas(api, _ventana("2026-09-01T04:00:00Z", "2026-09-02T04:00:00Z"))
    assert fila[f"{ACCESO} · Turno A"]["valor"] == 25.0  # 10 * 100 / 40
