"""Panel, reportes con supresión n < 5 y /metrics, contra la base real y el contrato."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

import pytest
from gepp_bd import transaccion
from gepp_bd.repositorios import hallazgos
from gepp_core import Hallazgo, Severidad, TipoEPP
from sqlalchemy import Engine

from ..conftest import T0
from .conftest import Cliente

pytestmark = pytest.mark.integration

ADMIN = {"Authorization": "Bearer admin"}
SUPERVISOR = {"Authorization": "Bearer super"}
AUDITOR = {"Authorization": "Bearer auditor"}
#: Ventana que contiene todo lo sembrado (T0 = 2026-09-02 02:10 UTC).
VENTANA = "desde=2026-09-01T00:00:00Z&hasta=2026-09-03T00:00:00Z"


@pytest.fixture(autouse=True)
def _tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GEPP_API_TOKENS",
        "demo=prevencionista@obra.invalid,admin=administrador@obra.invalid,"
        "super=supervisor.acceso@obra.invalid,auditor=auditor@obra.invalid",
    )


@pytest.fixture
def extra(bd: Engine, datos: dict[str, Any]) -> None:
    """Área 2 · Cámara 02: 5 hallazgos sin chaleco (críticos) y 2 sin casco.

    Con los 2 sin casco del área 1 quedan casco = 4 y chaleco = 5: los dos lados del
    umbral de supresión N_MINIMO = 5.
    """
    del datos
    with transaccion(bd) as s:
        for i, epp in enumerate([TipoEPP.CHALECO] * 5 + [TipoEPP.CASCO] * 2):
            inicio = T0 + timedelta(hours=3, minutes=i)
            hallazgos.guardar(
                s,
                Hallazgo(
                    track_id=i + 1,
                    regla_id=2,
                    regla_version=1,
                    epp_faltante=frozenset({epp}),
                    severidad=Severidad.CRITICA if epp is TipoEPP.CHALECO else Severidad.ALTA,
                    ts_inicio=inicio,
                    ts_fin=inicio + timedelta(seconds=10),
                    cuadros_confirmados=50,
                    confianza_media=0.8,
                ),
                hallazgos.Contexto(fuente_id=2, area_id=2),
            )


def _indicadores(panel: dict[str, Any]) -> dict[str, Any]:
    return {i["clave"]: i for i in panel["indicadores"]}


def test_el_panel_cumple_el_contrato_y_cuadra_con_los_datos(api: Cliente, extra: None) -> None:
    del extra
    panel = api.llamar("obtenerPanel", "GET", f"/panel?{VENTANA}")
    ind = _indicadores(panel)
    assert [i["clave"] for i in panel["indicadores"]] == [
        "hallazgos_abiertos",
        "criticos_sin_revisar",
        "cumplimiento_epp",
        "zona_mas_incumplimientos",
        "videos_procesados_hoy",
    ]
    assert ind["hallazgos_abiertos"]["valor"] == 9
    assert ind["criticos_sin_revisar"]["valor"] == 5
    # 3 personas observadas (una por video), 2 con hallazgo.
    assert ind["cumplimiento_epp"] == {**ind["cumplimiento_epp"], "valor": 33.3, "unidad": "%"}
    assert ind["zona_mas_incumplimientos"]["valor"] == "Cámara 02 · obra gruesa"
    assert ind["videos_procesados_hoy"]["valor"] == 3
    assert ind["hallazgos_abiertos"]["variacion"] is None  # período anterior vacío
    assert len(ind["hallazgos_abiertos"]["serie"]) == 7
    assert sum(ind["hallazgos_abiertos"]["serie"]) == 9
    assert len(panel["tendencia"]["etiquetas"]) == 7
    # hasta = 3-sep 00:00 UTC = miércoles 2-sep 20:00 en Santiago: el día se corta en hora local.
    assert panel["tendencia"]["etiquetas"][-1] == "M"
    assert panel["ranking_epp"] == [{"epp": "chaleco", "total": 5}, {"epp": "casco", "total": 4}]
    assert len(panel["criticos_recientes"]) == 5
    assert all(h["severidad"] == 4 for h in panel["criticos_recientes"])


def test_el_panel_del_supervisor_solo_cuenta_su_area(api: Cliente, extra: None) -> None:
    del extra
    ind = _indicadores(api.llamar("obtenerPanel", "GET", f"/panel?{VENTANA}", headers=SUPERVISOR))
    assert ind["hallazgos_abiertos"]["valor"] == 2
    assert ind["criticos_sin_revisar"]["valor"] == 0
    assert ind["zona_mas_incumplimientos"]["valor"] == "Cámara 01 · acceso"


def test_sin_personas_el_cumplimiento_dice_sin_datos(api: Cliente) -> None:
    fuera = "desde=2020-01-01T00:00:00Z&hasta=2020-01-08T00:00:00Z"
    ind = _indicadores(api.llamar("obtenerPanel", "GET", f"/panel?{fuera}"))
    assert ind["cumplimiento_epp"]["valor"] == "sin datos"
    assert ind["hallazgos_abiertos"]["valor"] == 0


@pytest.mark.parametrize("tipo", ["ranking-epp", "zonas", "mapa-calor", "tendencia"])
@pytest.mark.parametrize("segmentacion", [None, "zona", "turno", "camara", "epp"])
def test_los_cuatro_reportes_cumplen_el_contrato(
    api: Cliente, extra: None, tipo: str, segmentacion: str | None
) -> None:
    del extra
    consulta = VENTANA + (f"&segmentacion={segmentacion}" if segmentacion else "")
    r = api.llamar("obtenerReporte", "GET", f"/reportes/{tipo}?{consulta}")
    assert r["tipo"] == tipo
    for fila in r["filas"]:
        # Ninguna celda visible con menos de 5: la supresión es del servidor.
        assert fila["datos_insuficientes"] or fila["n"] >= 5


def test_la_supresion_corta_exactamente_en_cinco(api: Cliente, extra: None) -> None:
    del extra
    r = api.llamar("obtenerReporte", "GET", f"/reportes/ranking-epp?{VENTANA}")
    filas = {f["etiqueta"]: f for f in r["filas"]}
    # n = 4: suprimida, sin valor y sin n (el n también reidentifica).
    assert filas["casco"] == {
        "etiqueta": "casco",
        "valor": None,
        "n": None,
        "datos_insuficientes": True,
    }
    # n = 5: visible.
    assert filas["chaleco"]["valor"] == 5 and filas["chaleco"]["n"] == 5
    assert filas["chaleco"]["datos_insuficientes"] is False


def test_el_reporte_de_zonas_trae_serie_de_ocho_semanas(api: Cliente, extra: None) -> None:
    del extra
    r = api.llamar("obtenerReporte", "GET", f"/reportes/zonas?{VENTANA}&segmentacion=camara")
    filas = {f["etiqueta"]: f for f in r["filas"]}
    assert filas["Cámara 01 · acceso"]["datos_insuficientes"] is True  # n = 2
    visible = filas["Cámara 02 · obra gruesa"]
    assert visible["n"] == 7
    assert len(visible["serie"]) == 8 and sum(visible["serie"]) == 7


def test_el_csv_aplica_la_misma_supresion(api: Cliente, extra: None) -> None:
    del extra
    r = api.http.get(
        f"/api/v1/reportes/ranking-epp?{VENTANA}&formato=csv",
        headers={"Authorization": "Bearer demo"},
    )
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    filas = {f["etiqueta"]: f for f in csv.DictReader(io.StringIO(r.text))}
    assert filas["casco"]["valor"] == "" and filas["casco"]["n"] == ""
    assert filas["casco"]["datos_insuficientes"] == "true"
    assert filas["chaleco"]["n"] == "5"


def test_permisos_de_los_reportes(api: Cliente) -> None:
    api.llamar("obtenerReporte", "GET", "/reportes/tendencia", headers=SUPERVISOR, esperado=403)
    api.llamar("obtenerReporte", "GET", "/reportes/tendencia", headers=ADMIN)
    api.llamar("obtenerReporte", "GET", "/reportes/tendencia", headers=AUDITOR)
    api.llamar("obtenerReporte", "GET", "/reportes/tendencia", headers={}, esperado=401)


def test_metrics_expone_cinco_familias_por_fuente(api: Cliente, extra: None) -> None:
    del extra
    r = api.http.get("/metrics")
    assert r.status_code == 200
    texto = r.text
    for familia in (
        "gepp_videos",
        "gepp_cuadros_analizados_total",
        "gepp_proceso_segundos_total",
        "gepp_hallazgos",
        "gepp_ultima_captura_timestamp_segundos",
    ):
        assert f"# TYPE {familia.removesuffix('_total')}" in texto, familia
    assert 'gepp_cuadros_analizados_total{fuente="Cámara 01 · acceso"} 120.0' in texto
    assert 'gepp_proceso_segundos_total{fuente="Cámara 01 · acceso"} 2.7' in texto
    assert 'gepp_hallazgos{fuente="Cámara 02 · obra gruesa",severidad="4"} 5.0' in texto
    assert 'gepp_videos{estado="listo",fuente="Cámara 01 · acceso"} 3.0' in texto or (
        'gepp_videos{fuente="Cámara 01 · acceso",estado="listo"} 3.0' in texto
    )
