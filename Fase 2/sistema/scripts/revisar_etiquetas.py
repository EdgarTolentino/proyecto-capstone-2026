"""Revisa una exportación «CVAT for images 1.1» contra la guía de etiquetado.

    uv run python scripts/revisar_etiquetas.py annotations.xml \
        [--iou 0.8] [--margen-cabeza 0.15] [--json]

Reporta pares repetidos, cajas bajo el mínimo, cuadros con cascos bajo el mínimo sin la etiqueta
`tiene_pequenos` y cascos o chalecos sin una persona que los contenga. Solo cuadro, clase y
coordenadas: nunca imágenes. No modifica el XML. Reglas en `gepp_vision.revision_etiquetas`.

Código de salida: 0 si leyó la exportación (haya o no hallazgos: son para que una persona
decida), 2 si el archivo no existe o no es una exportación válida.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from gepp_vision.revision_etiquetas import (
    MARGEN_CABEZA,
    UMBRAL_IOU,
    ErrorExportacion,
    Hallazgo,
    leer_cvat_xml_archivo,
    resumen,
    revisar,
)


def _coords(h: Hallazgo) -> list[list[float]]:
    return [[round(c.x1, 2), round(c.y1, 2), round(c.x2, 2), round(c.y2, 2)] for c in h.cajas]


def _a_dict(h: Hallazgo) -> dict[str, Any]:
    d: dict[str, Any] = {
        "regla": h.regla.value,
        "cuadro": h.cuadro,
        "nombre": h.nombre,
        "clase": h.clase,
        "cajas": _coords(h),
    }
    if h.iou is not None:
        d["iou"] = round(h.iou, 4)
    return d


def _tabla(hallazgos: list[Hallazgo]) -> str:
    filas = [("regla", "cuadro", "clase", "coordenadas x1,y1,x2,y2")]
    for h in hallazgos:
        coords = " | ".join(",".join(f"{v:g}" for v in c) for c in _coords(h))
        if h.iou is not None:
            coords += f"  (IoU {h.iou:.2f})"
        filas.append((h.regla.value, str(h.cuadro), h.clase, coords))
    ancho = [max(len(f[i]) for f in filas) for i in range(3)]
    return "\n".join(
        f"{f[0]:<{ancho[0]}}  {f[1]:>{ancho[1]}}  {f[2]:<{ancho[2]}}  {f[3]}" for f in filas
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("xml", type=Path, help="annotations.xml de «CVAT for images 1.1»")
    p.add_argument("--iou", type=float, default=UMBRAL_IOU, help="IoU mínimo de un par repetido")
    p.add_argument(
        "--margen-cabeza",
        type=float,
        default=MARGEN_CABEZA,
        help="fracción del alto de la persona que se amplía hacia arriba",
    )
    p.add_argument("--json", action="store_true", help="salida JSON en vez de tabla")
    args = p.parse_args(argv)

    try:
        cuadros = leer_cvat_xml_archivo(args.xml)
        hallazgos = revisar(cuadros, args.iou, args.margen_cabeza)
    except (ErrorExportacion, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    cifras = resumen(hallazgos)
    if args.json:
        salida = {
            "cuadros": len(cuadros),
            "umbral_iou": args.iou,
            "margen_cabeza": args.margen_cabeza,
            "resumen": cifras,
            "hallazgos": [_a_dict(h) for h in hallazgos],
        }
        print(json.dumps(salida, ensure_ascii=False, indent=2))
        return 0

    if hallazgos:
        print(_tabla(hallazgos))
        print()
    print(f"{len(cuadros)} cuadros, IoU >= {args.iou:g}, margen de cabeza {args.margen_cabeza:g}")
    for regla, c in cifras.items():
        print(f"  {regla:<22} {c['hallazgos']:>4} hallazgos en {c['cuadros']:>3} cuadros")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
