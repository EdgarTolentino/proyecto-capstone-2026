"""`scripts/evaluar.py deteccion`: de dos COCO a un JSON y una tabla."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.evaluar import main  # type: ignore[import-not-found]


def _coco(score: float | None) -> dict[str, Any]:
    anotacion: dict[str, Any] = {
        "id": 1,
        "image_id": 1,
        "category_id": 1,
        "bbox": [700, 300, 50, 100],
        "area": 5000,
        "iscrowd": 0,
    }
    if score is not None:
        anotacion["score"] = score
    return {
        "info": {"description": "pre-etiquetas rfdetr-n-epp-v1"},
        "categories": [{"id": 1, "name": "persona"}, {"id": 2, "name": "tiene_pequenos"}],
        "images": [{"id": 1, "file_name": "a.jpg", "width": 1920, "height": 1080}],
        "annotations": [anotacion],
    }


@pytest.fixture
def archivos(tmp_path: Path) -> tuple[Path, Path]:
    verdad, predichas = tmp_path / "verdad.json", tmp_path / "pred.json"
    verdad.write_text(json.dumps(_coco(None)), encoding="utf-8")
    predichas.write_text(json.dumps(_coco(0.9)), encoding="utf-8")
    return verdad, predichas


def _args(verdad: Path, predichas: Path, salida: Path, recorte: str) -> list[str]:
    return [
        "deteccion",
        str(verdad),
        str(predichas),
        "--recorte",
        recorte,
        "--origen-verdad",
        "con-preetiquetas",
        "--salida",
        str(salida),
    ]


def test_de_punta_a_punta(
    archivos: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    salida = tmp_path / "metricas.json"
    assert main(_args(*archivos, salida, "600,220,1400,730")) == 0
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["modelo"] == "pre-etiquetas rfdetr-n-epp-v1"
    assert datos["regiones"]["dentro"]["map50"] == pytest.approx(1.0)
    assert "| dentro | persona | 1 | 1 | 1,000 |" in capsys.readouterr().out


def test_verdad_y_predicciones_al_reves_detiene(
    archivos: tuple[Path, Path], tmp_path: Path
) -> None:
    verdad, predichas = archivos
    with pytest.raises(SystemExit, match="score"):
        main(_args(predichas, verdad, tmp_path / "m.json", "600,220,1400,730"))


@pytest.mark.parametrize("recorte", ["600,220,1400", "1400,220,600,730", "a,b,c,d"])
def test_recorte_mal_escrito_detiene(
    archivos: tuple[Path, Path], tmp_path: Path, recorte: str
) -> None:
    with pytest.raises(SystemExit, match="recorte"):
        main(_args(*archivos, tmp_path / "m.json", recorte))


@pytest.mark.parametrize("quitar", ["annotations", "categories", "images"])
def test_coco_incompleto_detiene_con_el_nombre_del_archivo(
    archivos: tuple[Path, Path], tmp_path: Path, quitar: str
) -> None:
    verdad, predichas = archivos
    datos = _coco(None)
    del datos[quitar]
    verdad.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(SystemExit, match=r"verdad\.json") as e:
        main(_args(verdad, predichas, tmp_path / "m.json", "600,220,1400,730"))
    assert quitar in str(e.value)


def test_caja_con_tres_valores_detiene_con_el_nombre_del_archivo(
    archivos: tuple[Path, Path], tmp_path: Path
) -> None:
    verdad, predichas = archivos
    datos = _coco(0.9)
    datos["annotations"][0]["bbox"] = [1, 2, 3]
    predichas.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(SystemExit, match=r"pred\.json"):
        main(_args(verdad, predichas, tmp_path / "m.json", "600,220,1400,730"))
