"""Mide el modelo contra la verdad etiquetada en CVAT (#31, nivel 1 del plan de evaluación).

    uv run python scripts/evaluar.py deteccion verdad.coco.json predicciones.coco.json \
        --recorte 600,220,1400,730 --origen-verdad con-preetiquetas --salida metricas.json

Recall de `cabeza` (ADR-013) con la cabeza esperada DERIVADA de la verdad (persona sin casco).
Las predicciones de un modelo v3 salen de `preetiquetar.py --con-evidencia`:

    uv run python scripts/evaluar.py cabeza verdad.coco.json predicciones.coco.json \
        --clases modelo.clases.json --recorte 600,220,1400,730 --salida cabeza.json

Nivel 0, el acuerdo entre las dos personas que etiquetaron los mismos cuadros:

    uv run python scripts/evaluar.py acuerdo primera.json segunda.json --salida metricas.json

La verdad es la exportación COCO 1.0 de CVAT. Las predicciones salen de
`preetiquetar.py --umbral 0.05` en la máquina con GPU; medir no necesita GPU. Para la cifra
sin sesgo, la verdad son los 24 cuadros del doble etiquetado (`--origen-verdad
sin-preetiquetas`), y la comparación en igualdad usa `--imagenes-de` con ese mismo archivo.
Especificación: docs/arquitectura/04-evaluar-niveles-0-1.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path

from gepp_core import ClaseDetectada
from gepp_vision.detectores.rfdetr_comun import MapaDeClases
from gepp_vision.evaluacion import (
    ORIGENES,
    UMBRAL_REGLA,
    ArchivoCoco,
    EntradaInvalida,
    Recorte,
    acuerdo,
    estado_git,
    evaluar_cabeza,
    evaluar_regiones,
    imagenes_comunes,
    leer_coco,
    reporte,
    reporte_acuerdo,
    reporte_cabeza,
    tabla_acuerdo,
    tabla_cabeza,
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
    d.add_argument(
        "--umbral",
        type=float,
        default=UMBRAL_REGLA,
        help=f"confianza mínima, la misma para las tres clases (la de la regla: {UMBRAL_REGLA})",
    )
    d.add_argument("--salida", type=Path, required=True)
    c = niveles.add_parser("cabeza", help="recall de `cabeza`, con la verdad derivada (ADR-013)")
    c.add_argument("verdad", type=Path, help="exportación COCO 1.0 de CVAT (sin cabeza)")
    c.add_argument("predicciones", type=Path, help="salida de preetiquetar.py --umbral 0.05")
    c.add_argument(
        "--clases",
        type=Path,
        required=True,
        help="mapa de clases del modelo que predijo (el .clases.json de sus pesos): sin la clase "
        "`cabeza` no hay nada que medir y el script se detiene en vez de dar 0",
    )
    c.add_argument("--recorte", required=True, help="x1,y1,x2,y2 en px del cuadro: el foso")
    c.add_argument("--imagenes-de", type=Path, help="evalúa solo las imágenes de este COCO")
    c.add_argument(
        "--umbral",
        type=float,
        default=UMBRAL_REGLA,
        help=f"confianza mínima de la predicción (la de la regla: {UMBRAL_REGLA})",
    )
    c.add_argument("--salida", type=Path, required=True)
    k = niveles.add_parser("acuerdo", help="nivel 0: ¿coinciden los dos etiquetadores?")
    k.add_argument("primera", type=Path, help="exportación COCO 1.0 de la tarea completa")
    k.add_argument("segunda", type=Path, help="exportación de doble-etiquetado-24")
    k.add_argument("--salida", type=Path, required=True)
    args = p.parse_args(argv)
    if args.nivel == "acuerdo":
        return _acuerdo(args)
    if args.nivel == "cabeza":
        return _cabeza(args)

    try:
        recorte = _recorte(args.recorte)
        verdad = _leer(args.verdad, predicciones=False)
        predichas = _leer(args.predicciones, predicciones=True)
        solo = _leer(args.imagenes_de, predicciones=False).imagenes if args.imagenes_de else None
        imagenes = imagenes_comunes(verdad, predichas, solo)
        regiones = evaluar_regiones(verdad, predichas, imagenes, recorte, args.umbral)
    except (EntradaInvalida, ValueError) as e:
        sys.exit(f"error: {e}")

    aviso = _aviso_recorte(predichas.descripcion, recorte, {verdad.imagenes[a] for a in imagenes})
    if aviso:
        print(aviso, file=sys.stderr)
    evaluadas = set(imagenes)
    scores = [c.score for c in predichas.cajas if c.archivo in evaluadas and c.score is not None]

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
        score_minimo=min(scores, default=None),
        entradas=entradas,
        git=estado_git(Path(__file__).resolve().parent),
    )
    args.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(tabla_markdown(datos))
    return 0


def _cabeza(args: argparse.Namespace) -> int:
    try:
        mapa = MapaDeClases.desde_json(args.clases)
    except (OSError, ValueError, KeyError) as e:
        sys.exit(f"error: {args.clases}: {e}")
    if ClaseDetectada.CABEZA not in mapa.clases.values():
        sys.exit(
            f"error: el modelo {mapa.version} ({args.clases}) no tiene la clase `cabeza`: el "
            "recall no se puede medir (no es 0, no hay nada que acertar). Usa un modelo v3."
        )
    try:
        recorte = _recorte(args.recorte)
        verdad = _leer(args.verdad, predicciones=False)
        predichas = _leer(args.predicciones, predicciones=True)
        solo = _leer(args.imagenes_de, predicciones=False).imagenes if args.imagenes_de else None
        if "cabeza" not in predichas.categorias:
            # Sin `--con-evidencia`, `preetiquetar.py` escribe solo las clases de CVAT y no declara
            # la categoría: sin ella, «0 cabezas» sería un artefacto del archivo.
            sys.exit(
                f"error: {args.predicciones} no declara la categoría `cabeza`: quien lo escribió "
                "la descartó (¿falta `preetiquetar.py --con-evidencia`?). El recall saldría 0 sin "
                "que el modelo tenga la culpa."
            )
        if "cabeza" in verdad.categorias:  # aunque no traiga anotaciones (revisión de Codex)
            sys.exit(
                f"error: {args.verdad} ya trae la categoría `cabeza`: la verdad no se deriva, "
                "se usa la etiquetada. Este comando no lo cubre."
            )
        imagenes = imagenes_comunes(verdad, predichas, solo)
        tamanos = {a: verdad.imagenes[a] for a in imagenes}
        regiones = evaluar_cabeza(
            [c for c in verdad.cajas if c.archivo in tamanos],
            [c for c in predichas.evidencia if c.archivo in tamanos],
            tamanos,
            recorte,
            args.umbral,
        )
    except (EntradaInvalida, ValueError) as e:
        sys.exit(f"error: {e}")

    aviso = _aviso_recorte(predichas.descripcion, recorte, set(tamanos.values()))
    if aviso:
        print(aviso, file=sys.stderr)
    entradas = {"verdad": args.verdad, "predicciones": args.predicciones, "clases": args.clases}
    if args.imagenes_de:
        entradas["imagenes_de"] = args.imagenes_de
    datos = reporte_cabeza(
        regiones,
        modelo=predichas.descripcion,
        clases=args.clases,
        imagenes=imagenes,
        recorte=recorte,
        umbral=args.umbral,
        entradas=entradas,
        git=estado_git(Path(__file__).resolve().parent),
    )
    args.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(tabla_cabeza(datos))
    return 0


def _acuerdo(args: argparse.Namespace) -> int:
    primera = _leer(args.primera, predicciones=False)
    segunda = _leer(args.segunda, predicciones=False)
    try:
        resultado = acuerdo(primera, segunda)
    except EntradaInvalida as e:
        sys.exit(f"error: {e}")
    datos = reporte_acuerdo(
        resultado,
        entradas={"primera": args.primera, "segunda": args.segunda},
        git=estado_git(Path(__file__).resolve().parent),
    )
    args.salida.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(tabla_acuerdo(datos))
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


#: El recorte del mosaico como lo escribe `DetectorMosaico.version`, normalizado al cuadro:
#: `mosaico[0.3125,0.2037,0.7292,0.6759x2/384/100px]:...`.
_MOSAICO = re.compile(r"mosaico\[([^,\]]+),([^,\]]+),([^,\]]+),([^,\]x]+)x")


def _aviso_recorte(
    descripcion: str, recorte: Recorte, tamanos: Iterable[tuple[int, int]]
) -> str | None:
    """Aviso si el recorte con que se predijo (en `info.description`) no es `--recorte`.

    Con otro recorte, «dentro» y «fuera» no corresponden a lo que vio el mosaico y la
    comparación por región engaña. Tolerancia de 1 px: la descripción trae 4 decimales. Si la
    descripción no trae el recorte en ese formato, no avisa.
    """
    m = _MOSAICO.search(descripcion)
    if m is None:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in m.groups())
    except ValueError:
        return None
    for ancho, alto in sorted(set(tamanos)):
        px = (x1 * ancho, y1 * alto, x2 * ancho, y2 * alto)
        if any(abs(a - b) > 1 for a, b in zip(px, recorte, strict=True)):
            usado = ",".join(f"{v:.0f}" for v in px)
            pedido = ",".join(f"{v:g}" for v in recorte)
            return (
                f"aviso: las predicciones se hicieron con el mosaico en {usado} px "
                f"(cuadro de {ancho}x{alto}) y --recorte es {pedido}: las regiones dentro y "
                "fuera no son las del mosaico"
            )
    return None


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
