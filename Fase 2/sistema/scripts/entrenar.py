"""Entrena RF-DETR sobre el dataset que arma `preparar_dataset.py` (PT-08, #31).

    uv run python scripts/entrenar.py ~/datos/gepp/epp-v1 ~/modelos/rfdetr-n-epp-v1

Solo en la máquina con GPU (`make setup-gpu`). Mientras entrena no se corre la demo en la
misma máquina (ADR-010): las dos cosas compiten por los 8 GB de la GPU.

Junto a los pesos deja `procedencia.json`: commit del repositorio, conteos del dataset,
parámetros y versión de rfdetr. Sin eso, una métrica no se puede reproducir (CLAUDE.md,
«Datos y modelos»). Para exportar el modelo y escribir su `.clases.json`, ver
`exportar_onnx.py`.

Los valores por defecto caben en una RTX 4070 Laptop (8 GB): lote 4 con acumulación 4 da un
lote efectivo de 16, el que usa rfdetr como referencia.

Si la corrida se corta, `--reanudar` la retoma desde `last.ckpt` (pesos, optimizador, época y
estado del early stopping) con los parámetros que guardó su `procedencia.json`:

    uv run python scripts/entrenar.py ~/datos/gepp/epp-v1 ~/modelos/rfdetr-n-epp-v1 --reanudar
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from gepp_vision.detectores.rfdetr import VARIANTES
from gepp_vision.entrenamiento import CLASES_V3

RAIZ = Path(__file__).resolve().parent


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(RAIZ), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def commit_actual(salida: Path, archivo: str = "cambios_sin_commit.diff") -> str:
    """El commit, y si hay cambios sin confirmar, su diff junto a los pesos: sin él la corrida
    no se puede reproducir."""
    commit = _git("rev-parse", "HEAD")
    if not _git("status", "--porcelain"):
        return commit
    (salida / archivo).write_text(_git("diff", "HEAD"), encoding="utf-8")
    return f"{commit}-con-cambios (ver {archivo})"


def escribir_procedencia(salida: Path, procedencia: dict[str, Any]) -> None:
    """Escribe a un temporal y lo reemplaza: un corte a mitad de escritura no deja la
    procedencia truncada, y una reanudación posterior sigue pudiendo leerla."""
    temporal = salida / "procedencia.json.tmp"
    temporal.write_text(json.dumps(procedencia, indent=2, ensure_ascii=False), encoding="utf-8")
    temporal.replace(salida / "procedencia.json")


def huella_anotaciones(dataset: Path) -> dict[str, str]:
    """sha256 de cada `_annotations.coco.json`: si se regenera el dataset en la misma ruta,
    la procedencia lo delata."""
    return {
        carpeta: hashlib.sha256(
            (dataset / carpeta / "_annotations.coco.json").read_bytes()
        ).hexdigest()
        for carpeta in ("train", "valid", "test")
        if (dataset / carpeta / "_annotations.coco.json").exists()
    }


def verificar_dataset(dataset: Path) -> dict[str, object]:
    """Falla antes de reservar la GPU si el dataset no es el que espera la v3."""
    for carpeta in ("train", "valid"):
        if not (dataset / carpeta / "_annotations.coco.json").exists():
            sys.exit(
                f"{dataset}/{carpeta} no tiene _annotations.coco.json (corre preparar_dataset)"
            )
    esperadas = {i: str(c) for c, i in CLASES_V3.items()}
    for carpeta in ("train", "valid"):
        anotaciones = json.loads((dataset / carpeta / "_annotations.coco.json").read_text("utf-8"))
        categorias = {int(c["id"]): str(c["name"]) for c in anotaciones["categories"]}
        if categorias != esperadas:
            sys.exit(f"{carpeta}: categorías {categorias} distintas de las de la v3 {esperadas}")
    coco = json.loads((dataset / "train/_annotations.coco.json").read_text(encoding="utf-8"))
    usadas = {int(a["category_id"]) for a in coco["annotations"]}
    sin_cajas = [esperadas[i] for i in esperadas if i not in usadas]
    if sin_cajas:
        sys.exit(f"train no tiene cajas de {sin_cajas}: el modelo saldría sin esa clase")
    resumen = dataset / "resumen.json"
    datos: dict[str, object] = json.loads(resumen.read_text()) if resumen.exists() else {}
    return datos


# Ni la ruta del dataset ni la de salida se comparan: el dataset se compara por su huella y la
# salida es de donde se leyó la procedencia.
_NO_SE_COMPARAN = frozenset({"dataset", "salida", "reanudar"})


def corrida_a_reanudar(salida: Path, dataset: Path) -> dict[str, Any]:
    """La procedencia de la corrida cortada en `salida`. Falla si no hay qué retomar, si ya
    terminó o si el dataset cambió desde que empezó: eso sería mezclar corridas."""
    if not (salida / "last.ckpt").exists():
        sys.exit(f"{salida} no tiene last.ckpt: no hay corrida que reanudar")
    archivo = salida / "procedencia.json"
    if not archivo.exists():
        sys.exit(f"{salida} no tiene procedencia.json: no se sabe con qué se entrenó")
    procedencia: dict[str, Any] = json.loads(archivo.read_text(encoding="utf-8"))
    if "fin" in procedencia:
        sys.exit(f"{salida} es una corrida terminada ({procedencia['fin']}): no se reanuda")
    if procedencia["dataset_sha256"] != huella_anotaciones(dataset):
        sys.exit(f"las anotaciones de {dataset} cambiaron desde que empezó la corrida")
    return procedencia


def parametros_distintos(
    guardados: dict[str, Any], actuales: dict[str, Any]
) -> dict[str, tuple[Any, Any]]:
    """Los parámetros que cambiarían al reanudar, como `{nombre: (guardado, pedido)}`."""
    return {
        k: (guardados.get(k), v)
        for k, v in actuales.items()
        if k not in _NO_SE_COMPARAN and guardados.get(k) != v
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("dataset", type=Path)
    p.add_argument("salida", type=Path)
    p.add_argument("--variante", default="nano", choices=sorted(VARIANTES))
    p.add_argument("--epocas", type=int, default=50)
    p.add_argument("--lote", type=int, default=4)
    p.add_argument("--acumulacion", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--paciencia", type=int, default=10, help="épocas sin mejora antes de parar")
    p.add_argument("--trabajadores", type=int, default=2, help="procesos que cargan imágenes")
    p.add_argument(
        "--reanudar", action="store_true", help="retoma la corrida cortada en SALIDA (last.ckpt)"
    )
    args = p.parse_args(argv)
    dataset, salida = args.dataset.expanduser(), args.salida.expanduser()

    resumen = verificar_dataset(dataset)
    if args.reanudar:
        procedencia = corrida_a_reanudar(salida, dataset)
        guardados = procedencia["parametros"]
        # Lo guardado pasa a ser el valor por defecto: basta con `--reanudar`. Un parámetro
        # pedido explícitamente que difiera detiene todo.
        p.set_defaults(**{k: v for k, v in guardados.items() if k not in _NO_SE_COMPARAN})
        args = p.parse_args(argv)
        distintos = parametros_distintos(guardados, vars(args))
        if distintos:
            sys.exit(f"reanudar no cambia parámetros (guardado, pedido): {distintos}")
    elif salida.exists() and any(salida.iterdir()):
        sys.exit(f"{salida} no está vacía: no se mezclan corridas (¿--reanudar?)")

    import rfdetr  # extra `gpu`
    import torch

    if not torch.cuda.is_available():
        sys.exit("no hay GPU CUDA: este script es para la máquina con GPU (ADR-010)")

    notas: dict[str, str] = {"dataset": str(dataset)}
    if args.reanudar:
        reanudaciones = procedencia.setdefault("reanudaciones", [])
        n = len(reanudaciones) + 1
        commit = commit_actual(salida, f"cambios_sin_commit-reanudacion-{n}.diff")
        reanudaciones.append(
            {
                "commit": commit,
                "inicio": datetime.now(UTC).isoformat(timespec="seconds"),
                "desde": "last.ckpt",
                "rfdetr": version("rfdetr"),
                "torch": torch.__version__,
                "gpu": torch.cuda.get_device_name(0),
            }
        )
        # Los pesos que salgan de aquí los produjo este commit, no el del inicio.
        notas |= {"commit": commit, "commit_inicio": procedencia["commit"]}
    else:
        salida.mkdir(parents=True)
        procedencia = {
            "commit": commit_actual(salida),
            "inicio": datetime.now(UTC).isoformat(timespec="seconds"),
            "dataset": str(dataset),
            "dataset_resumen": resumen,
            "dataset_sha256": huella_anotaciones(dataset),
            "parametros": {
                k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()
            },
            "rfdetr": version("rfdetr"),
            "torch": torch.__version__,
            "gpu": torch.cuda.get_device_name(0),
        }
        notas["commit"] = procedencia["commit"]
    escribir_procedencia(salida, procedencia)

    modelo = getattr(rfdetr, VARIANTES[args.variante])()
    modelo.train(
        dataset_dir=str(dataset),
        output_dir=str(salida),
        epochs=args.epocas,
        batch_size=args.lote,
        grad_accum_steps=args.acumulacion,
        lr=args.lr,
        early_stopping=True,
        early_stopping_patience=args.paciencia,
        num_workers=args.trabajadores,
        tensorboard=False,
        progress_bar="tqdm",
        notes=notas,
        resume=str(salida / "last.ckpt") if args.reanudar else None,
    )

    procedencia["fin"] = datetime.now(UTC).isoformat(timespec="seconds")
    escribir_procedencia(salida, procedencia)
    print(f"listo: {salida}. Siguiente paso: scripts/exportar_onnx.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
