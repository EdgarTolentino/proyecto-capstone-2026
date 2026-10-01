"""Configuración de la API: los tokens de demostración y las cuentas del equipo."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from gepp_api.app import crear_app
from gepp_api.config import Configuracion
from gepp_bd.modelos import ROLES
from gepp_bd.semilla import leer
from sqlalchemy import Engine

from .conftest import PERFIL

EQUIPO = (
    ("mortega", "Miguel Ortega", "administrador"),
    ("lgrandon", "Lian Grandón", "prevencionista"),
)


def test_sin_variable_entran_el_demo_y_las_cuentas_del_equipo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEPP_API_TOKENS", raising=False)
    tokens = Configuracion().tokens
    assert tokens["demo"] == "prevencionista@obra.invalid"
    assert tokens["mortega"] == "mortega@duocuc.cl"
    assert tokens["lgrandon"] == "lgrandon@duocuc.cl"
    assert "admin" not in tokens, "el administrador de demo solo entra si se configura"


def test_la_variable_reemplaza_el_mapa_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEPP_API_TOKENS", "x=alguien@obra.invalid")
    assert Configuracion().tokens == {"x": "alguien@obra.invalid"}


def test_cada_token_por_defecto_apunta_a_un_usuario_del_perfil(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un token sin usuario sembrado entra a la API y recibe 401: el mapa y el perfil van juntos."""
    monkeypatch.delenv("GEPP_API_TOKENS", raising=False)
    usuarios = {u["email"]: u for u in leer(PERFIL)["usuarios"]}
    for token, email in Configuracion().tokens.items():
        assert email in usuarios, f"token {token!r} apunta a {email!r}, que no está en {PERFIL}"
        assert usuarios[email]["rol"] in ROLES


@pytest.mark.integration
def test_las_cuentas_del_equipo_entran_a_la_api_sin_configurar(
    bd: Engine, datos: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """De punta a punta: token por defecto → usuario sembrado → sesión con su rol."""
    del datos
    monkeypatch.delenv("GEPP_API_TOKENS", raising=False)
    with TestClient(crear_app(motor=bd)) as c:
        for token, nombre, rol in EQUIPO:
            r = c.get("/api/v1/yo", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, f"{token}: {r.status_code} {r.text[:200]}"
            assert (r.json()["nombre"], r.json()["rol"]) == (nombre, rol)
        r = c.get("/api/v1/yo", headers={"Authorization": "Bearer admin"})
        assert r.status_code == 401
