"""`scripts/entrenar.py --reanudar`: retomar una corrida cortada sin mezclar corridas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from gepp_vision.entrenamiento import CLASES_V1

from scripts.entrenar import (  # type: ignore[import-not-found]
    corrida_a_reanudar,
    huella_anotaciones,
    main,
    parametros_distintos,
)

PARAMETROS = {
    "variante": "small",
    "epocas": 50,
    "lote": 2,
    "acumulacion": 8,
    "lr": 0.0001,
    "paciencia": 10,
    "trabajadores": 2,
}


def _dataset(raiz: Path) -> Path:
    """Un COCO mínimo con las tres clases v1 en train y en valid."""
    coco = {
        "categories": [{"id": i, "name": str(c)} for c, i in CLASES_V1.items()],
        "images": [{"id": 1, "file_name": "a.jpg", "width": 10, "height": 10}],
        "annotations": [
            {"id": i, "image_id": 1, "category_id": i, "bbox": [0, 0, 5, 5]}
            for i in CLASES_V1.values()
        ],
    }
    for carpeta in ("train", "valid"):
        (raiz / carpeta).mkdir(parents=True)
        (raiz / carpeta / "_annotations.coco.json").write_text(json.dumps(coco))
    return raiz


def _corrida(salida: Path, dataset: Path, **extra: Any) -> Path:
    """Una corrida cortada: `last.ckpt` y una procedencia sin `fin`."""
    salida.mkdir()
    (salida / "last.ckpt").write_bytes(b"")
    procedencia = {
        "commit": "abc",
        "dataset_sha256": huella_anotaciones(dataset),
        "parametros": {"dataset": str(dataset), "salida": str(salida), **PARAMETROS},
        **extra,
    }
    (salida / "procedencia.json").write_text(json.dumps(procedencia))
    return salida


def test_una_corrida_cortada_se_puede_reanudar(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = _corrida(tmp_path / "modelo", dataset)
    assert corrida_a_reanudar(salida, dataset)["parametros"]["variante"] == "small"


def test_sin_last_ckpt_no_hay_que_reanudar(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = _corrida(tmp_path / "modelo", dataset)
    (salida / "last.ckpt").unlink()
    with pytest.raises(SystemExit, match=r"no tiene last\.ckpt"):
        corrida_a_reanudar(salida, dataset)


def test_sin_procedencia_no_se_reanuda(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = _corrida(tmp_path / "modelo", dataset)
    (salida / "procedencia.json").unlink()
    with pytest.raises(SystemExit, match=r"no tiene procedencia\.json"):
        corrida_a_reanudar(salida, dataset)


def test_una_corrida_terminada_no_se_reanuda(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = _corrida(tmp_path / "modelo", dataset, fin="2026-10-15T16:21:00+00:00")
    with pytest.raises(SystemExit, match="corrida terminada"):
        corrida_a_reanudar(salida, dataset)


def test_si_el_dataset_cambio_no_se_reanuda(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = _corrida(tmp_path / "modelo", dataset)
    valid = dataset / "valid" / "_annotations.coco.json"
    valid.write_text(valid.read_text() + " ")
    with pytest.raises(SystemExit, match="cambiaron desde que empezó"):
        corrida_a_reanudar(salida, dataset)


def test_los_mismos_parametros_no_difieren() -> None:
    assert parametros_distintos(PARAMETROS, {**PARAMETROS, "reanudar": True}) == {}


def test_las_rutas_no_se_comparan() -> None:
    guardados = {**PARAMETROS, "dataset": "/a", "salida": "/b"}
    assert parametros_distintos(guardados, {**PARAMETROS, "dataset": "~/a", "salida": "b"}) == {}


def test_un_parametro_distinto_se_reporta() -> None:
    assert parametros_distintos(PARAMETROS, {**PARAMETROS, "lote": 4}) == {"lote": (2, 4)}


def test_reanudar_con_otro_parametro_se_detiene_antes_de_la_gpu(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = _corrida(tmp_path / "modelo", dataset)
    with pytest.raises(SystemExit, match=r"'lote': \(2, 4\)"):
        main([str(dataset), str(salida), "--reanudar", "--lote", "4"])


def test_sin_reanudar_una_salida_con_algo_se_rechaza(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = _corrida(tmp_path / "modelo", dataset)
    with pytest.raises(SystemExit, match="no se mezclan corridas"):
        main([str(dataset), str(salida)])
