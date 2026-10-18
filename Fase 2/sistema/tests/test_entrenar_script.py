"""`scripts/entrenar.py --reanudar`: retomar una corrida cortada sin mezclar corridas."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from gepp_vision.detectores.rfdetr import VARIANTES
from gepp_vision.entrenamiento import CLASES_V1

import scripts.entrenar as entrenar  # type: ignore[import-not-found]
from scripts.entrenar import (  # type: ignore[import-not-found]
    corrida_a_reanudar,
    escribir_procedencia,
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


@pytest.fixture
def gpu_falsa(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """rfdetr, torch, git y la versión instalada, falsos: `main` corre entero sin GPU.
    Devuelve lo que recibió `train` y con qué archivo se pidió el diff."""
    llamado: dict[str, Any] = {}

    class Modelo:
        def train(self, **kwargs: Any) -> None:
            llamado["train"] = kwargs

    rfdetr = SimpleNamespace(**{nombre: Modelo for nombre in VARIANTES.values()})
    cuda = SimpleNamespace(is_available=lambda: True, get_device_name=lambda _: "GPU-B")
    monkeypatch.setitem(sys.modules, "rfdetr", rfdetr)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=cuda, __version__="t"))
    monkeypatch.setattr(entrenar, "version", lambda _: "r")

    def commit_actual(_salida: Path, archivo: str = "cambios_sin_commit.diff") -> str:
        llamado["diff"] = archivo
        return "B"

    monkeypatch.setattr(entrenar, "commit_actual", commit_actual)
    return llamado


def test_reanudar_retoma_desde_last_ckpt_con_lo_guardado(
    tmp_path: Path, gpu_falsa: dict[str, Any]
) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = _corrida(tmp_path / "modelo", dataset, gpu="GPU-A")
    assert main([str(dataset), str(salida), "--reanudar"]) == 0

    train = gpu_falsa["train"]
    assert train["resume"] == str(salida / "last.ckpt")
    # Lote y acumulación salen de la procedencia, no de los valores por defecto (4 y 4).
    assert (train["batch_size"], train["grad_accum_steps"]) == (2, 8)
    assert train["notes"] == {"dataset": str(dataset), "commit": "B", "commit_inicio": "abc"}
    assert gpu_falsa["diff"] == "cambios_sin_commit-reanudacion-1.diff"

    procedencia = json.loads((salida / "procedencia.json").read_text())
    assert (procedencia["commit"], procedencia["gpu"]) == ("abc", "GPU-A")
    [reanudacion] = procedencia["reanudaciones"]
    assert (reanudacion["commit"], reanudacion["gpu"]) == ("B", "GPU-B")
    assert "fin" in procedencia
    assert not (salida / "procedencia.json.tmp").exists()


def test_una_corrida_nueva_no_reanuda(tmp_path: Path, gpu_falsa: dict[str, Any]) -> None:
    dataset = _dataset(tmp_path / "ds")
    salida = tmp_path / "modelo"
    assert main([str(dataset), str(salida)]) == 0
    assert gpu_falsa["train"]["resume"] is None
    assert gpu_falsa["train"]["notes"] == {"dataset": str(dataset), "commit": "B"}
    assert "reanudaciones" not in json.loads((salida / "procedencia.json").read_text())


def test_un_corte_al_escribir_no_trunca_la_procedencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    salida = tmp_path
    escribir_procedencia(salida, {"commit": "abc"})
    escribir = Path.write_text

    def cortada(self: Path, datos: str, *args: Any, **kwargs: Any) -> int:
        escribir(self, datos[:5], *args, **kwargs)
        raise OSError("SIGTERM a mitad de escritura")

    monkeypatch.setattr(Path, "write_text", cortada)
    with pytest.raises(OSError):
        escribir_procedencia(salida, {"commit": "abc", "fin": "x"})
    monkeypatch.undo()
    assert json.loads((salida / "procedencia.json").read_text()) == {"commit": "abc"}
