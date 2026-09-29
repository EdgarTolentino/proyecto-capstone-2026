"""Configuración de la API: los tokens de demostración."""

import pytest
import yaml
from gepp_api.config import Configuracion
from gepp_bd.modelos import ROLES

PERFIL = "perfiles/construccion.yaml"


def test_sin_variable_entran_los_roles_de_demo_y_las_cuentas_del_equipo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEPP_API_TOKENS", raising=False)
    tokens = Configuracion().tokens
    assert tokens["demo"] == "prevencionista@obra.invalid"
    assert tokens["admin"] == "administrador@obra.invalid"
    assert tokens["mortega"] == "mortega@duocuc.cl"
    assert tokens["lgrandon"] == "lgrandon@duocuc.cl"


def test_la_variable_reemplaza_el_mapa_por_defecto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEPP_API_TOKENS", "x=alguien@obra.invalid")
    assert Configuracion().tokens == {"x": "alguien@obra.invalid"}


def test_cada_token_por_defecto_apunta_a_un_usuario_del_perfil(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un token sin usuario sembrado entra a la API y recibe 401: el mapa y el perfil van juntos."""
    monkeypatch.delenv("GEPP_API_TOKENS", raising=False)
    with open(PERFIL, encoding="utf-8") as f:
        usuarios = {u["email"]: u for u in yaml.safe_load(f)["usuarios"]}
    for token, email in Configuracion().tokens.items():
        assert email in usuarios, f"token {token!r} apunta a {email!r}, que no está en {PERFIL}"
        assert usuarios[email]["rol"] in ROLES
