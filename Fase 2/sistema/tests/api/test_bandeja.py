"""La bandeja y el visor contra la base real, validados contra el contrato."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from gepp_bd import transaccion
from sqlalchemy import Engine

from .conftest import Cliente, _sembrar_video

pytestmark = pytest.mark.integration

ADMIN = {"Authorization": "Bearer admin"}
SUPERVISOR = {"Authorization": "Bearer super"}


@pytest.fixture(autouse=True)
def _tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GEPP_API_TOKENS",
        "demo=prevencionista@obra.invalid,admin=administrador@obra.invalid,"
        "super=supervisor.acceso@obra.invalid",
    )


def test_sin_cabecera_es_401_con_la_forma_del_contrato(api: Cliente) -> None:
    cuerpo = api.llamar("listarHallazgos", "GET", "/hallazgos", esperado=401, headers={})
    assert cuerpo["codigo"] == "no_autenticado"


def test_la_bandeja_lista_con_contadores_y_aviso_legal(api: Cliente, datos: dict[str, Any]) -> None:
    pagina = api.llamar("listarHallazgos", "GET", "/hallazgos")
    assert [h["id"] for h in pagina["items"]] == sorted(datos["hallazgos"], reverse=True)
    assert pagina["contadores"] == {
        "por_revisar": 2,
        "confirmado": 0,
        "descartado": 0,
        "reincidente": 2,
        "todos": 2,
    }
    h = pagina["items"][0]
    assert h["aviso_legal"] == "Indicio automatizado. Requiere validación humana."
    assert h["miniatura_url"].startswith("/api/v1/evidencias/")
    assert h["epp_faltante"] == ["casco"]
    # coherencia del contrato: cuadros_confirmados ~ duracion_s * 5
    assert abs(h["cuadros_confirmados"] - h["duracion_s"] * 5) <= 5
    assert h["ts_inicio"].endswith("-03:00") or h["ts_inicio"].endswith("-04:00")


def test_los_contadores_ignoran_el_filtro_de_estado(api: Cliente, datos: dict[str, Any]) -> None:
    api.llamar(
        "triarHallazgo",
        "POST",
        f"/hallazgos/{datos['hallazgos'][0]}/triage",
        json={"estado": "confirmado"},
    )
    pagina = api.llamar("listarHallazgos", "GET", "/hallazgos?estado=por_revisar")
    assert len(pagina["items"]) == 1
    assert pagina["contadores"]["confirmado"] == 1
    assert pagina["contadores"]["todos"] == 2


# T0 = 02:10 UTC = 22:10 en Santiago: los hallazgos caen en el turno B, no en el A.
@pytest.mark.parametrize(
    ("consulta", "esperados"),
    [
        ("epp=chaleco", 0),
        ("epp=casco,arnes", 2),
        ("severidad=4", 0),
        ("severidad=3,4", 2),
        ("fuente_id=2", 0),
        ("reincidente=false", 0),
        ("turno=A", 0),
        ("turno=B", 2),
        ("limite=1", 1),
    ],
)
def test_filtros(api: Cliente, consulta: str, esperados: int) -> None:
    pagina = api.llamar("listarHallazgos", "GET", f"/hallazgos?{consulta}")
    assert len(pagina["items"]) == esperados


UN_US = timedelta(microseconds=1)


def _ts_mas_antiguo(api: Cliente) -> datetime:
    pagina = api.llamar("listarHallazgos", "GET", "/hallazgos?limite=200")
    # Sin página siguiente, el último de la lista es de verdad el más antiguo.
    assert pagina["siguiente_cursor"] is None
    return datetime.fromisoformat(pagina["items"][-1]["ts_inicio"])


def _con_hasta(api: Cliente, hasta: datetime) -> list[int]:
    pagina = api.llamar(
        "listarHallazgos",
        "GET",
        "/hallazgos",
        params={"hasta": hasta.isoformat()},
    )
    return [h["id"] for h in pagina["items"]]


def test_hasta_es_semiabierto_y_excluye_el_hallazgo_justo_en_el_limite(api: Cliente) -> None:
    # La web manda `hasta` como el inicio del día siguiente: ese instante es del día siguiente.
    limite = _ts_mas_antiguo(api)
    assert _con_hasta(api, limite) == []


def test_hasta_un_microsegundo_despues_incluye_el_hallazgo(api: Cliente) -> None:
    limite = _ts_mas_antiguo(api)
    assert len(_con_hasta(api, limite + UN_US)) == 1


def test_hasta_un_microsegundo_antes_lo_deja_fuera(api: Cliente) -> None:
    limite = _ts_mas_antiguo(api)
    assert _con_hasta(api, limite - UN_US) == []


def test_desde_mayor_que_hasta_no_devuelve_nada(api: Cliente) -> None:
    limite = _ts_mas_antiguo(api)
    hasta = limite + UN_US
    # Con solo `hasta` el hallazgo sí entra: lo que vacía el resultado de abajo es `desde`.
    assert len(_con_hasta(api, hasta)) == 1
    pagina = api.llamar(
        "listarHallazgos",
        "GET",
        "/hallazgos",
        params={"desde": (limite + 2 * UN_US).isoformat(), "hasta": hasta.isoformat()},
    )
    assert pagina["items"] == []


#: Todo endpoint que recibe `desde`/`hasta`: el contrato pide `date-time`, que exige zona.
CON_FECHAS = [
    ("listarHallazgos", "/hallazgos"),
    ("obtenerPanel", "/panel"),
    ("obtenerReporte", "/reportes/ranking-epp"),
]


@pytest.mark.parametrize("parametro", ["desde", "hasta"])
@pytest.mark.parametrize(("operacion", "ruta"), CON_FECHAS)
def test_una_fecha_sin_zona_horaria_es_422(
    api: Cliente, operacion: str, ruta: str, parametro: str
) -> None:
    sin_zona = _ts_mas_antiguo(api).replace(tzinfo=None).isoformat()
    cuerpo = api.llamar(operacion, "GET", ruta, esperado=422, params={parametro: sin_zona})
    assert cuerpo["codigo"] == "peticion_invalida"


def _visible(operacion: str, respuesta: dict[str, Any]) -> Any:
    """Lo que cada endpoint muestra del conjunto de hallazgos de la ventana."""
    if operacion == "listarHallazgos":
        return sorted(h["id"] for h in respuesta["items"])
    if operacion == "obtenerPanel":
        return {i["clave"]: i["valor"] for i in respuesta["indicadores"]}["hallazgos_abiertos"]
    # Reporte: la celda de `casco` solo muestra `n` si no está suprimida (n >= 5).
    return {f["etiqueta"]: f["n"] for f in respuesta["filas"]}["casco"]


@pytest.mark.parametrize(("operacion", "ruta"), CON_FECHAS)
def test_el_mismo_instante_en_z_y_en_otro_desfase_da_lo_mismo(
    api: Cliente, bd: Engine, tmp_path: Path, operacion: str, ruta: str
) -> None:
    # 6 hallazgos más, uno por hora, a partir de las 3 h (los dos de `datos` quedan antes).
    with transaccion(bd) as s:
        nuevos = [
            _sembrar_video(
                s, tmp_path, hash_=f"{i + 1:x}" * 64, t0_s=10800 + 3600 * i, sin_casco=True
            )[0]
            for i in range(6)
        ]
    ts = {
        h["id"]: datetime.fromisoformat(h["ts_inicio"])
        for h in api.llamar("listarHallazgos", "GET", "/hallazgos?limite=200")["items"]
    }
    media_hora = timedelta(minutes=30)
    # El límite cae ENTRE el 5.º y el 6.º: correr `desde` o `hasta` una hora cambia el conjunto.
    desde, hasta = ts[nuevos[0]] - media_hora, ts[nuevos[5]] - media_hora
    en_utc = {"desde": desde.astimezone(UTC), "hasta": hasta.astimezone(UTC)}
    en_santiago = {k: v.astimezone(timezone(timedelta(hours=-3))) for k, v in en_utc.items()}
    assert en_utc["desde"].isoformat().endswith("+00:00")
    assert en_santiago["desde"].isoformat().endswith("-03:00")
    respuestas = [
        api.llamar(operacion, "GET", ruta, params={k: v.isoformat() for k, v in fechas.items()})
        for fechas in (en_utc, en_santiago)
    ]
    # No trivial: los 5 primeros nuevos, ni uno más ni uno menos, y a la vista.
    esperado = {"listarHallazgos": sorted(nuevos[:5]), "obtenerPanel": 5, "obtenerReporte": 5}
    assert [_visible(operacion, r) for r in respuestas] == [esperado[operacion]] * 2
    assert respuestas[0] == respuestas[1]


def test_posponer_hasta_sin_zona_horaria_es_422(api: Cliente, datos: dict[str, Any]) -> None:
    cuerpo = {"estado": "pospuesto", "posponer_hasta": "2026-10-20T10:00:00"}
    api.llamar(
        "triarHallazgo",
        "POST",
        f"/hallazgos/{datos['hallazgos'][0]}/triage",
        esperado=422,
        json=cuerpo,
    )


def test_la_paginacion_recorre_todo_sin_repetir(api: Cliente, datos: dict[str, Any]) -> None:
    primera = api.llamar("listarHallazgos", "GET", "/hallazgos?limite=1")
    segunda = api.llamar(
        "listarHallazgos", "GET", f"/hallazgos?limite=1&cursor={primera['siguiente_cursor']}"
    )
    assert segunda["siguiente_cursor"] is None
    assert {primera["items"][0]["id"], segunda["items"][0]["id"]} == set(datos["hallazgos"])


def test_el_visor_explica_por_que_se_disparo(api: Cliente, datos: dict[str, Any]) -> None:
    d = api.llamar("obtenerHallazgo", "GET", f"/hallazgos/{datos['hallazgos'][0]}")
    porque = d["por_que_se_disparo"]
    assert porque["regla_version"] == 1
    assert porque["norma_fundante"] == "DS 594 art. 53"
    assert "cuadro" not in porque["umbral_configurado"]  # segundos, nunca cuadros (ADR-005)
    assert d["tecnicos"]["modelo_version"] == "falso-0"
    assert len(d["evidencias"]) == 1 and d["evidencias"][0]["anonimizado"] is True


def test_la_evidencia_se_sirve_y_el_administrador_no_la_ve(
    api: Cliente, datos: dict[str, Any]
) -> None:
    d = api.llamar("obtenerHallazgo", "GET", f"/hallazgos/{datos['hallazgos'][0]}")
    url = d["evidencias"][0]["url"]
    r = api.http.get(url, headers={"Authorization": "Bearer demo"})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    r = api.http.get(url, headers=ADMIN)
    assert r.status_code == 403
    admin = api.llamar(
        "obtenerHallazgo", "GET", f"/hallazgos/{datos['hallazgos'][0]}", headers=ADMIN
    )
    assert admin["evidencias"] == []


def test_un_hallazgo_inexistente_es_404(api: Cliente) -> None:
    api.llamar("obtenerHallazgo", "GET", "/hallazgos/999999", esperado=404)


def test_el_triage_queda_auditado_y_no_se_pisa(api: Cliente, datos: dict[str, Any]) -> None:
    hid = datos["hallazgos"][0]
    h = api.llamar(
        "triarHallazgo", "POST", f"/hallazgos/{hid}/triage", json={"estado": "confirmado"}
    )
    assert h["estado"] == "confirmado" and h["asignado_a"]["nombre"] == "Prevencionista de turno"
    api.llamar(
        "triarHallazgo",
        "POST",
        f"/hallazgos/{hid}/triage",
        json={"estado": "duplicado"},
        esperado=409,
    )


def test_un_falso_positivo_exige_motivo(api: Cliente, datos: dict[str, Any]) -> None:
    hid = datos["hallazgos"][0]
    api.llamar(
        "triarHallazgo",
        "POST",
        f"/hallazgos/{hid}/triage",
        json={"estado": "falso_positivo"},
        esperado=422,
    )
    api.llamar(
        "triarHallazgo",
        "POST",
        f"/hallazgos/{hid}/triage",
        json={"estado": "falso_positivo", "motivo": "casco tapado por el andamio"},
    )


def test_el_administrador_no_puede_triar(api: Cliente, datos: dict[str, Any]) -> None:
    api.llamar(
        "triarHallazgo",
        "POST",
        f"/hallazgos/{datos['hallazgos'][0]}/triage",
        json={"estado": "confirmado"},
        headers=ADMIN,
        esperado=403,
    )


def test_el_triage_en_lote_informa_lo_omitido(api: Cliente, datos: dict[str, Any]) -> None:
    a, b = datos["hallazgos"]
    api.llamar("triarHallazgo", "POST", f"/hallazgos/{a}/triage", json={"estado": "confirmado"})
    r = api.llamar(
        "triarLote",
        "POST",
        "/hallazgos/triage-lote",
        json={"ids": [a, b, 999999], "decision": {"estado": "pospuesto"}},
    )
    assert r["aplicados"] == 1
    assert {o["id"] for o in r["omitidos"]} == {a, 999999}


def test_accion_correctiva(api: Cliente, datos: dict[str, Any]) -> None:
    yo = api.llamar("obtenerSesion", "GET", "/yo")
    accion = api.llamar(
        "crearAccionCorrectiva",
        "POST",
        f"/hallazgos/{datos['hallazgos'][0]}/acciones",
        json={"responsable_id": yo["id"], "descripcion": "Reponer casco", "plazo": "2026-09-30"},
        esperado=201,
    )
    assert accion["estado"] == "abierta"
    d = api.llamar("obtenerHallazgo", "GET", f"/hallazgos/{datos['hallazgos'][0]}")
    assert [x["id"] for x in d["acciones"]] == [accion["id"]]


def test_el_supervisor_solo_ve_su_area(api: Cliente) -> None:
    # Los hallazgos sembrados son del área 1, que es la del supervisor de acceso.
    assert len(api.llamar("listarHallazgos", "GET", "/hallazgos", headers=SUPERVISOR)["items"]) == 2
    yo = api.llamar("obtenerSesion", "GET", "/yo", headers=SUPERVISOR)
    assert yo["area_id"] == 1 and "editar_reglas" not in yo["permisos"]
    assert "procesar_videos" not in yo["permisos"]


def test_yo_catalogos_y_estado(api: Cliente) -> None:
    yo = api.llamar("obtenerSesion", "GET", "/yo")
    assert "ver_evidencia" in yo["permisos"]
    assert "procesar_videos" in yo["permisos"]  # el prevencionista procesa y mira en una web
    admin = api.llamar("obtenerSesion", "GET", "/yo", headers=ADMIN)
    assert "ver_evidencia" not in admin["permisos"]  # quien configura no observa
    assert "procesar_videos" in admin["permisos"]
    cat = api.llamar("obtenerCatalogos", "GET", "/catalogos")
    assert [t["codigo"] for t in cat["turnos"]] == ["A", "B"]
    assert len(cat["fuentes"]) == 2
    estado = api.llamar("obtenerEstado", "GET", "/estado")
    assert estado["pendientes_por_revisar"] == 2
    # La cámara 02 nunca entregó video: el hueco tiene que verse.
    assert [c["fuente"]["id"] for c in estado["cobertura"]["sin_cobertura"]] == [2]


def test_un_hallazgo_sin_video_sigue_cumpliendo_el_contrato(
    api: Cliente, datos: dict[str, Any], bd: Any
) -> None:
    """`video_id` es ON DELETE SET NULL: el visor no manda nulos que el contrato no admite."""
    from sqlalchemy import text

    with bd.begin() as c:
        c.execute(
            text("UPDATE hallazgo SET video_id = NULL WHERE id = :id"),
            {"id": datos["hallazgos"][0]},
        )
    d = api.llamar("obtenerHallazgo", "GET", f"/hallazgos/{datos['hallazgos'][0]}")
    assert "video_archivo" not in d["tecnicos"] and d["tecnicos"]["track_id"] == 1
