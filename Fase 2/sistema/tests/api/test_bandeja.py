"""La bandeja y el visor contra la base real, validados contra el contrato."""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import Cliente

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


def test_yo_catalogos_y_estado(api: Cliente) -> None:
    yo = api.llamar("obtenerSesion", "GET", "/yo")
    assert "ver_evidencia" in yo["permisos"]
    admin = api.llamar("obtenerSesion", "GET", "/yo", headers=ADMIN)
    assert "ver_evidencia" not in admin["permisos"]  # quien configura no observa
    cat = api.llamar("obtenerCatalogos", "GET", "/catalogos")
    assert [t["codigo"] for t in cat["turnos"]] == ["A", "B"]
    assert len(cat["fuentes"]) == 2
    estado = api.llamar("obtenerEstado", "GET", "/estado")
    assert estado["pendientes_por_revisar"] == 2
    # La cámara 02 nunca entregó video: el hueco tiene que verse.
    assert [c["fuente"]["id"] for c in estado["cobertura"]["sin_cobertura"]] == [2]
