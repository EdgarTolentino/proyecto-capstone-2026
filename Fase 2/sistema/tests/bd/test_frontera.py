"""Las fronteras del monorepo se cumplen por test, no por convención (ADR-007, ADR-012).

En el espacio de trabajo todos los paquetes comparten un solo entorno virtual, así que nada
impide `import gepp_vision` desde `gepp_api`: lo único que lo detiene es este test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PAQUETES = Path(__file__).resolve().parents[2] / "packages"

#: paquete -> módulos de primer nivel que no puede importar.
PROHIBIDOS: dict[str, set[str]] = {
    # ADR-012: solo depende de `gepp-core`; ni visión, ni trabajador, ni web.
    "gepp-bd": {"gepp_vision", "gepp_worker", "gepp_api", "fastapi", "cv2", "torch"},
    # ADR-007: la API corre sin GPU y no importa visión. Se comunica con el trabajador por la
    # base de datos, no por Redis, y no procesa imágenes (hoy no usa numpy ni cv2).
    "gepp-api": {"gepp_vision", "gepp_worker", "cv2", "torch", "numpy", "redis"},
}


class SinFuentes(AssertionError):
    """La raíz no existe o no tiene `.py`: el test no estaría vigilando nada."""


def revisar(raiz: Path, prohibidos: set[str]) -> list[str]:
    """`archivo:línea importa módulo` de cada import prohibido bajo `raiz`.

    Lanza `SinFuentes` si no hay nada que revisar: un árbol vacío o movido no puede pasar.
    """
    if not raiz.is_dir():
        raise SinFuentes(f"{raiz.name}: no existe la carpeta de fuentes; el test no vigila nada")
    archivos = sorted(raiz.rglob("*.py"))
    if not archivos:
        raise SinFuentes(
            f"{raiz.parent.name}/{raiz.name}: sin archivos .py; el test no vigila nada"
        )
    infractores: list[str] = []
    for archivo in archivos:
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                nombres = [nodo.module]
            else:
                continue
            for n in nombres:
                if n.split(".")[0] in prohibidos:
                    infractores.append(f"{archivo.relative_to(raiz)}:{nodo.lineno} importa {n}")
    return infractores


@pytest.mark.parametrize("paquete", sorted(PROHIBIDOS))
def test_el_paquete_no_cruza_su_frontera(paquete: str) -> None:
    infractores = revisar(PAQUETES / paquete / "src", PROHIBIDOS[paquete])
    assert not infractores, f"{paquete} cruza su frontera (ADR-007/012): {infractores}"


# ── El propio vigilante, con árboles controlados ───────────────────────────────────────────


def test_una_carpeta_src_vacia_no_pasa(tmp_path: Path) -> None:
    with pytest.raises(SinFuentes, match="sin archivos"):
        revisar(tmp_path, {"gepp_vision"})


def test_una_carpeta_con_solo_otros_archivos_tampoco_pasa(tmp_path: Path) -> None:
    (tmp_path / "LEEME.md").write_text("x")
    with pytest.raises(SinFuentes):
        revisar(tmp_path, {"gepp_vision"})


def test_una_ruta_inexistente_falla_con_un_mensaje_claro(tmp_path: Path) -> None:
    with pytest.raises(SinFuentes, match="no existe la carpeta"):
        revisar(tmp_path / "src_movido", {"gepp_vision"})


def test_un_archivo_permitido_pasa_sin_infracciones(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("import json\nfrom pathlib import Path\n")
    assert revisar(tmp_path, {"gepp_vision"}) == []


def test_un_import_prohibido_se_nombra_con_archivo_y_linea(tmp_path: Path) -> None:
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "malo.py").write_text("import json\n\n\ndef f():\n    import gepp_vision.x\n")
    (tmp_path / "otro.py").write_text("from redis import Redis\n")
    assert revisar(tmp_path, {"gepp_vision", "redis"}) == [
        "otro.py:1 importa redis",
        "pkg/malo.py:5 importa gepp_vision.x",
    ]


def test_un_prohibido_solo_como_prefijo_de_otro_nombre_no_cuenta(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("import redisx\nimport torchvision_falso\n")
    assert revisar(tmp_path, {"redis", "torch"}) == []
