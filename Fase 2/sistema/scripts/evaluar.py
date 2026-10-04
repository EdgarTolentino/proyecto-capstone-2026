"""Mide el modelo contra la verdad etiquetada en CVAT (#31, nivel 1 del plan de evaluación).

    uv run python scripts/evaluar.py deteccion verdad.coco.json predicciones.coco.json \
        --recorte 600,220,1400,730 --origen-verdad con-preetiquetas --salida metricas.json

La verdad es la exportación COCO 1.0 de CVAT. Las predicciones salen de
`preetiquetar.py --umbral 0.05` en la máquina con GPU; medir no necesita GPU. Para la cifra
sin sesgo, la verdad son los 24 cuadros del doble etiquetado (`--origen-verdad
sin-preetiquetas`), y la comparación en igualdad usa `--imagenes-de` con ese mismo archivo.
Especificación: docs/arquitectura/04-evaluar-niveles-0-1.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gepp_vision.evaluacion import (
    ORIGENES,
    UMBRAL_REGLA,
    ArchivoCoco,
    EntradaInvalida,
    Recorte,
    estado_git,
    evaluar_regiones,
    imagenes_comunes,
    leer_coco,
    reporte,
    tabla_markdown,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    niveles = p.add_subparsers(dest="nivel", required=True)
    d = niveles.add_parser("deteccion", help="nivel 1: ¿el modelo ve los objetos?")
    d.add_argument("verdad", type=Path, help="exportación COCO 1.0 de CVAT")
    d.add_argument("predicciones", type=Path, help="salida de preetiquetar.py --umbral 0.05")
    d.add_argument("--recorte", required=True, help="x1,y1,x2,y2 en px del cuadro: el foso")
    d.add_argument("--origen-verdad", required=True, choices=ORIGENES)
    d.add_argument("--imagenes-de", type=Path, help="evalúa solo las imágenes de este COCO")
    d.add_argument("--umbral", type=float, default=UMBRAL_REGLA)
    d.add_argument("--salida", type=Path, required=True)
    args = p.parse_args(argv)

    try:
        recorte = _recorte(args.recorte)
        verdad = _leer(args.verdad, predicciones=False)
        predichas = _leer(args.predicciones, predicciones=True)
        solo = _leer(args.imagenes_de, predicciones=False).imagenes if args.imagenes_de else None
        imagenes = imagenes_comunes(verdad, predichas, solo)
        regiones = evaluar_regiones(verdad, predichas, imagenes, recorte, args.umbral)
    except (EntradaInvalida, ValueError) as e:
        sys.exit(f"error: {e}")

    entradas = {"verdad": args.verdad, "predicciones": args.predicciones}
    if args.imagenes_de:
        entradas["imagenes_de"] = args.imagenes_de
    datos = reporte(
        regiones,
        origen_verdad=args.origen_verdad,
        modelo=predichas.descripcion,
        imagenes=imagenes,
        recorte=recorte,
        umbral=args.umbral,
        entradas=entradas,
        git=estado_git(Path(__file__).resolve().parent),
    )
    args.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(tabla_markdown(datos))
    return 0


def _leer(ruta: Path, *, predicciones: bool) -> ArchivoCoco:
    """Lee un COCO; cualquier fallo de formato sale con el nombre del archivo."""
    try:
        return leer_coco(json.loads(ruta.read_text(encoding="utf-8")), predicciones=predicciones)
    except EntradaInvalida as e:
        sys.exit(f"error: {ruta}: {e}")
    except (KeyError, ValueError, TypeError) as e:
        sys.exit(f"error: {ruta}: formato COCO inválido ({type(e).__name__}: {e})")
    except OSError as e:
        sys.exit(f"error: {ruta}: {e}")


def _recorte(texto: str) -> Recorte:
    try:
        x1, y1, x2, y2 = (float(v) for v in texto.split(","))
    except ValueError:
        raise ValueError(f"recorte mal escrito: {texto!r}; se espera x1,y1,x2,y2") from None
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"recorte degenerado: {texto!r}")
    return (x1, y1, x2, y2)


if __name__ == "__main__":
    raise SystemExit(main())
