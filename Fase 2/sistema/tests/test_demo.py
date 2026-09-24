"""`scripts/demo.py`: qué detector recibe el trabajador según se pida guion o modelo."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.demo import entorno_del_trabajador, validar_modelo  # type: ignore[import-not-found]

COMUNES = {"url": "postgresql://x/gepp_demo", "entrada": Path("/e"), "evidencia": Path("/v")}


def test_con_modelo_el_trabajador_no_ve_el_guion_del_env(tmp_path: Path) -> None:
    """El Makefile carga el .env, que puede traer GEPP_GUION_FALSO: con modelo, se saca."""
    modelo = tmp_path / "m.onnx"
    base = {"GEPP_GUION_FALSO": "tests/fixtures/guion_sin_casco.json", "PATH": "/usr/bin"}
    entorno = entorno_del_trabajador(
        base, fuente=2, guion=Path("demo/g.json"), modelo=modelo, **COMUNES
    )
    assert "GEPP_GUION_FALSO" not in entorno
    assert entorno["GEPP_MODELO_RUTA"] == str(modelo.resolve())
    assert entorno["GEPP_FUENTE_ID"] == "2" and entorno["PATH"] == "/usr/bin"


def test_sin_modelo_usa_el_guion_aunque_el_env_traiga_un_modelo() -> None:
    base = {"GEPP_MODELO_RUTA": "/datos/modelos/otro.onnx"}
    entorno = entorno_del_trabajador(
        base, fuente=1, guion=Path("demo/g.json"), modelo=None, **COMUNES
    )
    assert entorno["GEPP_GUION_FALSO"].endswith("demo/g.json")
    assert "GEPP_MODELO_RUTA" not in entorno


def test_un_modelo_sin_su_mapa_de_clases_se_rechaza_antes_de_empezar(tmp_path: Path) -> None:
    modelo = tmp_path / "m.onnx"
    with pytest.raises(SystemExit, match="no existe el modelo"):
        validar_modelo(modelo)
    modelo.write_bytes(b"onnx")
    with pytest.raises(SystemExit, match=r"m\.clases\.json"):
        validar_modelo(modelo)
    (tmp_path / "m.clases.json").write_text("{}")
    validar_modelo(modelo)  # los dos están: sigue
