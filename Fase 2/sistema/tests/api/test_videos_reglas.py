"""Cola de ingesta, reprocesamiento sin GPU y reglas versionadas, contra el contrato."""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import Cliente

pytestmark = pytest.mark.integration

ADMIN = {"Authorization": "Bearer admin"}


@pytest.fixture(autouse=True)
def _tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GEPP_API_TOKENS", "demo=prevencionista@obra.invalid,admin=administrador@obra.invalid"
    )


def _regla(**cambios: Any) -> dict[str, Any]:
    base = {
        "nombre": "Casco y chaleco en acceso",
        "area_id": 1,
        "epp_exigido": ["casco", "chaleco"],
        "confirmacion_segundos": 2.0,
        "severidad": 3,
        "finalidad_declarada": "Verificar el uso del EPP obligatorio al ingresar a la obra",
        "norma_fundante": "DS 594 art. 53",
    }
    return base | cambios


def _ids(api: Cliente) -> set[int]:
    return {h["id"] for h in api.llamar("listarHallazgos", "GET", "/hallazgos")["items"]}


def test_la_cola_de_ingesta(api: Cliente) -> None:
    pagina = api.llamar("listarVideos", "GET", "/videos")
    assert len(pagina["items"]) == 3
    v = pagina["items"][0]
    assert v["estado"] == "listo" and v["origen_capture_ts"] == "metadatos"
    assert v["fps_efectivo"] == 5.0 and len(v["hash_abreviado"]) == 8
    assert sorted(x["hallazgos_generados"] for x in pagina["items"]) == [0, 1, 1]
    assert api.llamar("listarVideos", "GET", "/videos?estado=error")["items"] == []
    assert all(x["intentos"] == 0 for x in pagina["items"])


def test_un_video_que_fallo_se_ve_con_su_motivo_y_sus_intentos(api: Cliente, bd: Any) -> None:
    from sqlalchemy import text

    with bd.begin() as c:
        c.execute(
            text(
                "UPDATE video SET estado = 'reintentando', intentos = 2,"
                " error_motivo = 'No se pudo leer el video: moov atom not found' WHERE id = 2"
            )
        )
    (v,) = api.llamar("listarVideos", "GET", "/videos?estado=reintentando")["items"]
    assert (v["id"], v["intentos"]) == (2, 2)
    assert v["error_motivo"].startswith("No se pudo leer el video")
    # Volvió a la cola: la cabecera no puede decir "Ingesta detenida".
    with bd.begin() as c:
        c.execute(text("UPDATE video SET estado = 'listo' WHERE id <> 2"))
    ingesta = api.llamar("obtenerEstado", "GET", "/estado")["ingesta"]
    assert ingesta["activa"] and ingesta["en_cola"] == 1


def test_reprocesar_exige_permiso_y_video_listo(api: Cliente) -> None:
    api.llamar("reprocesarVideo", "POST", "/videos/1/reprocesar", esperado=403)
    api.llamar("reprocesarVideo", "POST", "/videos/99/reprocesar", headers=ADMIN, esperado=404)


@pytest.mark.parametrize("estado", ["error", "reintentando"])
def test_reprocesar_un_video_que_fallo_lo_devuelve_a_la_cola(
    api: Cliente, bd: Any, estado: str
) -> None:
    from sqlalchemy import text

    with bd.begin() as c:
        c.execute(
            text(
                "UPDATE video SET estado = :e, intentos = 3,"
                " error_motivo = 'LookupError: el área 1 no tiene reglas activas' WHERE id = 2"
            ),
            {"e": estado},
        )
    v = api.llamar("reprocesarVideo", "POST", "/videos/2/reprocesar", headers=ADMIN, esperado=202)
    assert (v["estado"], v["intentos"], v["error_motivo"]) == ("en_cola", 0, None)
    with bd.begin() as c:
        accion = c.execute(
            text("SELECT accion FROM auditoria WHERE entidad = 'video' AND entidad_id = 2")
        ).scalar_one()
    assert accion == "video:reintentar"
    # Ya está en la cola: pedirlo otra vez no tiene sentido.
    api.llamar("reprocesarVideo", "POST", "/videos/2/reprocesar", headers=ADMIN, esperado=409)


def test_reprocesar_dos_veces_no_duplica_ni_cambia_nada(api: Cliente) -> None:
    antes = _ids(api)
    for _ in range(2):
        v = api.llamar(
            "reprocesarVideo", "POST", "/videos/1/reprocesar", headers=ADMIN, esperado=202
        )
        assert v["hallazgos_generados"] == 1
    assert _ids(api) == antes


def test_reprocesar_con_regla_nueva_reemplaza_sin_pisar_lo_triado(
    api: Cliente, datos: dict[str, Any]
) -> None:
    confirmado, por_revisar = datos["hallazgos"]
    api.llamar(
        "triarHallazgo", "POST", f"/hallazgos/{confirmado}/triage", json={"estado": "confirmado"}
    )
    # 10 s de confirmación: más que los 8 s del video, así que la regla nueva no dispara nada.
    api.llamar(
        "actualizarRegla", "PUT", "/reglas/1", headers=ADMIN, json=_regla(confirmacion_segundos=10)
    )
    for video in (1, 2):
        api.llamar(
            "reprocesarVideo", "POST", f"/videos/{video}/reprocesar", headers=ADMIN, esperado=202
        )
    quedan = _ids(api)
    assert confirmado in quedan  # la decisión humana sobrevive
    assert por_revisar not in quedan  # lo que la regla vigente ya no produce, se va


def test_crear_versionar_y_no_pisar_una_regla(api: Cliente) -> None:
    lista = api.llamar("listarReglas", "GET", "/reglas")
    assert [r["version"] for r in lista] == [1, 1]
    assert lista[0]["hallazgos_30d"] >= 0 and lista[0]["evaluable"] is True

    nueva = api.llamar(
        "crearRegla",
        "POST",
        "/reglas",
        headers=ADMIN,
        esperado=201,
        json=_regla(nombre="Casco en patio", epp_exigido=["casco"], severidad=2),
    )
    assert nueva["version"] == 1
    api.llamar(
        "crearRegla",
        "POST",
        "/reglas",
        headers=ADMIN,
        esperado=409,
        json=_regla(nombre="Casco en patio"),
    )

    v2 = api.llamar(
        "actualizarRegla",
        "PUT",
        f"/reglas/{nueva['id']}",
        headers=ADMIN,
        json=_regla(
            nombre="Casco en patio", epp_exigido=["casco"], severidad=2, confirmacion_segundos=3.5
        ),
    )
    assert (v2["version"], v2["confirmacion_segundos"]) == (2, 3.5)
    v1 = api.llamar("obtenerRegla", "GET", f"/reglas/{nueva['id']}")
    assert v1["activa"] is False
    api.llamar(
        "actualizarRegla",
        "PUT",
        f"/reglas/{nueva['id']}",
        headers=ADMIN,
        esperado=409,
        json=_regla(nombre="Casco en patio"),
    )
    api.llamar(
        "actualizarRegla",
        "PUT",
        f"/reglas/{v2['id']}",
        headers=ADMIN,
        esperado=422,
        json=_regla(nombre="Otro nombre"),
    )
    assert len(api.llamar("listarReglas", "GET", "/reglas?activa=true")) == 3


@pytest.mark.parametrize(
    ("cuerpo", "estado"),
    [
        ({"zona_ids": [1, 2]}, 422),
        ({"confirmacion_segundos": 0.1}, 422),
        ({"epp_exigido": []}, 422),
        ({"hora_desde": "25:00"}, 422),
    ],
)
def test_reglas_invalidas(api: Cliente, cuerpo: dict[str, Any], estado: int) -> None:
    api.llamar(
        "crearRegla",
        "POST",
        "/reglas",
        headers=ADMIN,
        esperado=estado,
        json=_regla(nombre="Inválida") | cuerpo,
    )


def test_solo_quien_configura_edita_reglas(api: Cliente) -> None:
    api.llamar("crearRegla", "POST", "/reglas", esperado=403, json=_regla(nombre="X"))
    api.llamar("obtenerRegla", "GET", "/reglas/999", esperado=404)


# T0 = 2026-09-02 02:10 UTC = 2026-09-01 22:10 en Santiago: el día LOCAL es el 1.
@pytest.mark.parametrize(("confirmacion", "esperados"), [(2.0, 2), (7.9, 0), (10.0, 0)])
def test_simular_sobre_lo_guardado(api: Cliente, confirmacion: float, esperados: int) -> None:
    r = api.llamar(
        "simularRegla",
        "POST",
        "/reglas/1/simular",
        headers=ADMIN,
        json={
            "desde": "2026-09-01",
            "hasta": "2026-09-01",
            "regla": _regla(confirmacion_segundos=confirmacion),
        },
    )
    assert r["hallazgos_estimados"] == esperados
    assert r["contra_version_vigente"] == {"actuales": 2, "variacion": esperados - 2}
    assert r["alertas_por_turno_estimadas"] == esperados / 2


def test_simular_fuera_del_rango_no_ve_nada(api: Cliente) -> None:
    r = api.llamar(
        "simularRegla",
        "POST",
        "/reglas/1/simular",
        headers=ADMIN,
        json={
            "desde": "2026-09-02",
            "hasta": "2026-09-03",
            "regla": _regla(),
        },
    )
    assert r["hallazgos_estimados"] == 0 and r["contra_version_vigente"]["actuales"] == 0


def test_simular_por_turno_usa_la_hora_local(api: Cliente) -> None:
    """Los hallazgos sembrados son de las 22:10 en Santiago: turno B, no A."""
    cuerpo = {"desde": "2026-09-01", "hasta": "2026-09-01"}
    a = api.llamar(
        "simularRegla",
        "POST",
        "/reglas/1/simular",
        headers=ADMIN,
        json=cuerpo | {"regla": _regla(turno="A")},
    )
    b = api.llamar(
        "simularRegla",
        "POST",
        "/reglas/1/simular",
        headers=ADMIN,
        json=cuerpo | {"regla": _regla(turno="B")},
    )
    assert (a["hallazgos_estimados"], b["hallazgos_estimados"]) == (0, 2)


def test_una_regla_que_la_camara_no_puede_ver_no_es_evaluable_ni_dispara(
    api: Cliente, bd: Any
) -> None:
    from sqlalchemy import text

    with bd.begin() as c:
        c.execute(text("UPDATE zona SET evaluable = '{arnes}'"))
    (r, *_) = api.llamar("listarReglas", "GET", "/reglas?area_id=1")
    assert r["evaluable"] is False
    # Reprocesar con la regla inaplicable borra lo que estaba por revisar en ese video.
    v = api.llamar("reprocesarVideo", "POST", "/videos/1/reprocesar", headers=ADMIN, esperado=202)
    assert v["hallazgos_generados"] == 0
    sim = api.llamar(
        "simularRegla",
        "POST",
        "/reglas/1/simular",
        headers=ADMIN,
        json={"desde": "2026-09-01", "hasta": "2026-09-01", "regla": _regla()},
    )
    assert sim["hallazgos_estimados"] == 0
