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
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from gepp_vision.detectores.rfdetr import VARIANTES
from gepp_vision.entrenamiento import CLASES_V1

RAIZ = Path(__file__).resolve().parent


def commit_actual() -> str:
    salida = subprocess.run(
        ["git", "-C", str(RAIZ), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    sucio = subprocess.run(
        ["git", "-C", str(RAIZ), "status", "--porcelain"], capture_output=True, text=True
    ).stdout.strip()
    return salida.stdout.strip() + ("-con-cambios" if sucio else "")


def verificar_dataset(dataset: Path) -> dict[str, object]:
    """Falla antes de reservar la GPU si el dataset no es el que espera la v1."""
    for carpeta in ("train", "valid"):
        if not (dataset / carpeta / "_annotations.coco.json").exists():
            sys.exit(
                f"{dataset}/{carpeta} no tiene _annotations.coco.json (corre preparar_dataset)"
            )
    coco = json.loads((dataset / "train/_annotations.coco.json").read_text(encoding="utf-8"))
    categorias = {int(c["id"]): str(c["name"]) for c in coco["categories"]}
    esperadas = {i: str(c) for c, i in CLASES_V1.items()}
    if categorias != esperadas:
        sys.exit(f"categorías {categorias} distintas de las de la v1 {esperadas}")
    usadas = {int(a["category_id"]) for a in coco["annotations"]}
    sin_cajas = [esperadas[i] for i in esperadas if i not in usadas]
    if sin_cajas:
        sys.exit(f"train no tiene cajas de {sin_cajas}: el modelo saldría sin esa clase")
    resumen = dataset / "resumen.json"
    datos: dict[str, object] = json.loads(resumen.read_text()) if resumen.exists() else {}
    return datos


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
    args = p.parse_args(argv)
    dataset, salida = args.dataset.expanduser(), args.salida.expanduser()

    resumen = verificar_dataset(dataset)
    if salida.exists() and any(salida.iterdir()):
        sys.exit(f"{salida} no está vacía: no se mezclan corridas")

    import rfdetr  # extra `gpu`
    import torch

    if not torch.cuda.is_available():
        sys.exit("no hay GPU CUDA: este script es para la máquina con GPU (ADR-010)")

    salida.mkdir(parents=True)
    procedencia = {
        "commit": commit_actual(),
        "inicio": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": str(dataset),
        "dataset_resumen": resumen,
        "parametros": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "rfdetr": version("rfdetr"),
        "torch": torch.__version__,
        "gpu": torch.cuda.get_device_name(0),
    }
    (salida / "procedencia.json").write_text(json.dumps(procedencia, indent=2, ensure_ascii=False))

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
        notes={"commit": procedencia["commit"], "dataset": str(dataset)},
    )

    procedencia["fin"] = datetime.now(UTC).isoformat(timespec="seconds")
    (salida / "procedencia.json").write_text(json.dumps(procedencia, indent=2, ensure_ascii=False))
    print(f"listo: {salida}. Siguiente paso: scripts/exportar_onnx.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
