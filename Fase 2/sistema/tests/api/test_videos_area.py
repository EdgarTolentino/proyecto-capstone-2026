"""El supervisor solo ve los videos y los conteos de las cámaras de su área (H5)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, text

from .conftest import Cliente

pytestmark = pytest.mark.integration

DEMO = {"Authorization": "Bearer demo"}  # prevencionista
SUPER = {"Authorization": "Bearer super"}  # supervisor del área 1
ADMIN = {"Authorization": "Bearer admin"}
AUDITOR = {"Authorization": "Bearer auditor"}


@pytest.fixture(autouse=True)
def _tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GEPP_API_TOKENS",
        "demo=prevencionista@obra.invalid,super=supervisor.acceso@obra.invalid,"
        "admin=administrador@obra.invalid,auditor=auditor@obra.invalid",
    )


@pytest.fixture(autouse=True)
def _dos_areas(bd: Engine, datos: dict[str, Any]) -> None:
    """Video 1 (cámara 1, área 1) `listo`; video 3 (cámara nueva, también área 1) `en_cola`;
    video 2 (cámara 2, área 2) `procesando`."""
    del datos
    with bd.begin() as c:
        area = c.execute(text("SELECT area_id FROM fuente WHERE id = 2")).scalar_one()
        assert area != 1, "la prueba necesita una cámara de otra área"
        c.execute(text("UPDATE video SET fuente_id = 2, estado = 'procesando' WHERE id = 2"))
        # El video 3 (área 1) vive en una cámara cuyo id NO es el del área: si el filtro
        # comparara el id de la cámara con el del área, el supervisor no lo vería.
        nueva = c.execute(
            text(
                "INSERT INTO fuente (area_id, nombre, tipo, uri)"
                " SELECT 1, 'Cámara extra del área 1', tipo, uri FROM fuente WHERE id = 1"
                " RETURNING id"
            )
        ).scalar_one()
        assert nueva not in (1, 2)
        c.execute(
            text("UPDATE video SET estado = 'en_cola', fuente_id = :f WHERE id = 3"), {"f": nueva}
        )


def _ids(api: Cliente, headers: dict[str, str], consulta: str = "") -> list[int]:
    items = api.llamar("listarVideos", "GET", f"/videos{consulta}", headers=headers)["items"]
    return [v["id"] for v in items]


def _ingesta(api: Cliente, headers: dict[str, str]) -> dict[str, Any]:
    return api.llamar("obtenerEstado", "GET", "/estado", headers=headers)["ingesta"]


def test_el_supervisor_no_ve_los_videos_de_otra_area(api: Cliente) -> None:
    assert _ids(api, SUPER) == [3, 1]


@pytest.mark.parametrize(
    "headers", [DEMO, ADMIN, AUDITOR], ids=["prevencionista", "admin", "auditor"]
)
def test_los_demas_roles_ven_todos_los_videos(api: Cliente, headers: dict[str, str]) -> None:
    assert _ids(api, headers) == [3, 2, 1]


def test_los_filtros_no_dejan_al_supervisor_ver_la_otra_area(api: Cliente) -> None:
    assert _ids(api, SUPER, "?fuente_id=2") == []
    assert _ids(api, SUPER, "?estado=procesando") == []
    assert _ids(api, DEMO, "?fuente_id=2") == [2]
    assert _ids(api, DEMO, "?estado=procesando") == [2]


def test_la_paginacion_del_supervisor_solo_recorre_su_area(api: Cliente) -> None:
    pagina = api.llamar("listarVideos", "GET", "/videos?limite=1", headers=SUPER)
    assert [v["id"] for v in pagina["items"]] == [3]
    siguiente = api.llamar(
        "listarVideos",
        "GET",
        f"/videos?limite=1&cursor={pagina['siguiente_cursor']}",
        headers=SUPER,
    )
    assert [v["id"] for v in siguiente["items"]] == [1]
    assert siguiente["siguiente_cursor"] is None


def test_los_conteos_de_estado_del_supervisor_son_solo_de_su_area(api: Cliente) -> None:
    # El video que se procesa es del área 2: el supervisor del área 1 no lo cuenta.
    assert _ingesta(api, SUPER) == {"activa": True, "en_proceso": 0, "en_cola": 1}


@pytest.mark.parametrize(
    "headers", [DEMO, ADMIN, AUDITOR], ids=["prevencionista", "admin", "auditor"]
)
def test_los_demas_roles_cuentan_todos_los_videos(api: Cliente, headers: dict[str, str]) -> None:
    assert _ingesta(api, headers) == {"activa": True, "en_proceso": 1, "en_cola": 1}


def test_si_en_su_area_no_hay_nada_en_marcha_la_ingesta_figura_inactiva(
    api: Cliente, bd: Engine
) -> None:
    with bd.begin() as c:
        c.execute(text("UPDATE video SET estado = 'listo' WHERE id = 3"))
    assert _ingesta(api, SUPER) == {"activa": False, "en_proceso": 0, "en_cola": 0}
    assert _ingesta(api, DEMO)["en_proceso"] == 1


def _supervisor_con_area(bd: Engine, area: int | None) -> None:
    with bd.begin() as c:
        c.execute(
            text("UPDATE usuario SET area_id = :a WHERE email = :e"),
            {"a": area, "e": "supervisor.acceso@obra.invalid"},
        )


def test_un_supervisor_sin_area_no_ve_ningun_video(api: Cliente, bd: Engine) -> None:
    _supervisor_con_area(bd, None)
    pagina = api.llamar("listarVideos", "GET", "/videos", headers=SUPER)
    assert pagina == {"items": [], "siguiente_cursor": None}
    assert _ingesta(api, SUPER) == {"activa": False, "en_proceso": 0, "en_cola": 0}
    assert _ids(api, DEMO) == [3, 2, 1]  # y los demás roles siguen viendo todo


def test_un_supervisor_de_un_area_sin_videos_no_ve_ninguno(api: Cliente, bd: Engine) -> None:
    with bd.begin() as c:  # el área 2 tiene la cámara 2, pero sin videos
        c.execute(text("UPDATE video SET fuente_id = 1 WHERE id = 2"))
    _supervisor_con_area(bd, 2)
    pagina = api.llamar("listarVideos", "GET", "/videos", headers=SUPER)
    assert pagina == {"items": [], "siguiente_cursor": None}
    assert _ingesta(api, SUPER) == {"activa": False, "en_proceso": 0, "en_cola": 0}
    assert _ids(api, DEMO) == [3, 2, 1]
