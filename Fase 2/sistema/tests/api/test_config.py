"""Configuración de la API: los tokens de demostración y las cuentas del equipo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from gepp_api.app import crear_app
from gepp_api.config import Configuracion, ConfiguracionInvalida, validar_carpeta_entrada
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


# ── GEPP_CARPETA_ENTRADA (opcional; se valida al arrancar) ─────────────────────────────────


def test_sin_variable_no_hay_carpeta_de_entrada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEPP_CARPETA_ENTRADA", raising=False)
    assert Configuracion().carpeta_entrada is None
    monkeypatch.setenv("GEPP_CARPETA_ENTRADA", "   ")
    assert Configuracion().carpeta_entrada is None


def test_la_variable_define_la_carpeta_resuelta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "pedidos").mkdir()
    monkeypatch.setenv("GEPP_CARPETA_ENTRADA", str(tmp_path / "pedidos" / ".." / "pedidos"))
    monkeypatch.setenv("GEPP_CARPETA_VIGILADA", str(tmp_path / "vigilada"))
    assert Configuracion().carpeta_entrada == (tmp_path / "pedidos").resolve()


def test_una_carpeta_inexistente_o_que_es_un_archivo_no_arranca(tmp_path: Path) -> None:
    archivo = tmp_path / "x.mp4"
    archivo.write_bytes(b"x")
    for mala in (tmp_path / "no_existe", archivo):
        with pytest.raises(ConfiguracionInvalida, match="no existe o no es una carpeta"):
            validar_carpeta_entrada(str(mala))


def test_una_carpeta_bajo_mnt_no_arranca() -> None:
    with pytest.raises(ConfiguracionInvalida, match="/mnt/"):
        validar_carpeta_entrada("/mnt/c/videos")


def test_la_entrada_no_puede_cruzarse_con_la_vigilada(tmp_path: Path) -> None:
    vigilada = tmp_path / "vigilada"
    (vigilada / "dentro").mkdir(parents=True)
    (tmp_path / "hermana").mkdir()
    for mala in (vigilada, vigilada / "dentro", tmp_path):  # igual, anidada y contenedora
        with pytest.raises(ConfiguracionInvalida, match="GEPP_CARPETA_VIGILADA"):
            validar_carpeta_entrada(str(mala), str(vigilada))
    # hermanas: sin cruce
    assert (
        validar_carpeta_entrada(str(tmp_path / "hermana"), str(vigilada))
        == (tmp_path / "hermana").resolve()
    )


def test_el_cruce_se_detecta_con_las_rutas_resueltas(tmp_path: Path) -> None:
    """Un enlace o un `..` no esconden que es la misma carpeta."""
    vigilada = tmp_path / "vigilada"
    vigilada.mkdir()
    (tmp_path / "alias").symlink_to(vigilada)
    for mala in (tmp_path / "alias", tmp_path / "otra" / ".." / "vigilada"):
        with pytest.raises(ConfiguracionInvalida, match="GEPP_CARPETA_VIGILADA"):
            validar_carpeta_entrada(str(mala), str(vigilada))


def test_un_nombre_que_solo_comparte_prefijo_no_es_anidado(tmp_path: Path) -> None:
    (tmp_path / "videos").mkdir()
    (tmp_path / "videos_pedidos").mkdir()
    validar_carpeta_entrada(str(tmp_path / "videos_pedidos"), str(tmp_path / "videos"))


def test_sin_vigilada_definida_solo_se_validan_existencia_y_mnt(tmp_path: Path) -> None:
    validar_carpeta_entrada(str(tmp_path), None)
    validar_carpeta_entrada(str(tmp_path), "")
