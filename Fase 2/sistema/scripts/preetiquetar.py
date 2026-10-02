"""Pre-etiqueta un lote para CVAT con el modelo y el detector en mosaico (#27).

    uv run python scripts/preetiquetar.py ~/datos/gepp/prueba/lote datos/lote0.csv \
        ~/modelos/rfdetr-n-epp-v1/checkpoint_best_total.pth salida.coco.json \
        --recorte 600,220,1400,730

Solo en la máquina con GPU (`make setup-gpu`). Dentro del `--recorte` (px del cuadro) corre el
mosaico; fuera, el modelo sobre el cuadro entero, para no olvidar a las personas junto a la
cámara. Escribe COCO 1.0, que se importa en la tarea de CVAT con «Upload annotations».

Una pre-etiqueta no es verdad: quien etiqueta revisa cada caja, agrega lo que falta y fija
los atributos (`docs/datos/guia-etiquetado.md`). El mapa de clases debe estar verificado con
`exportar_onnx.py`: si no, las pre-etiquetas salen con la clase cambiada.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import cv2
from gepp_core import Caja, ClaseDetectada
from gepp_vision.detectores.mosaico import DetectorMosaico, Mosaico
from gepp_vision.detectores.rfdetr import VARIANTES, DetectorRFDETR
from gepp_vision.detectores.rfdetr_comun import MapaDeClases
from gepp_vision.etiquetado import a_coco, combinar

INSTANTE = datetime(2000, 1, 1, tzinfo=UTC)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("lote", type=Path, help="carpeta con las imágenes del lote")
    p.add_argument(
        "manifiesto", type=Path, help="el CSV de lote0.py: fija qué imágenes y en qué orden"
    )
    p.add_argument("pesos", type=Path)
    p.add_argument("salida", type=Path)
    p.add_argument("--variante", default="nano", choices=sorted(VARIANTES))
    p.add_argument(
        "--clases",
        type=Path,
        help="mapa de clases verificado por exportar_onnx; por defecto, el de junto a los pesos",
    )
    p.add_argument(
        "--umbral",
        type=float,
        default=0.4,
        help="más bajo que el del sistema: es más fácil borrar que dibujar",
    )
    p.add_argument("--recorte", required=True, help="x1,y1,x2,y2 en px del cuadro")
    p.add_argument("--factor", type=float, default=2.0)
    p.add_argument("--lado", type=int, default=384)
    p.add_argument("--objeto-max-px", type=int, default=100)
    args = p.parse_args(argv)

    with args.manifiesto.open(encoding="utf-8") as f:
        archivos = [fila["archivo"] for fila in csv.DictReader(f)]
    faltan = [a for a in archivos if not (args.lote / a).exists()]
    if faltan:
        sys.exit(f"{len(faltan)} imágenes del manifiesto no están en {args.lote}: {faltan[:3]}")

    ruta_clases = args.clases or MapaDeClases.junto_a(args.pesos)
    if not ruta_clases.exists():
        sys.exit(f"falta el mapa de clases {ruta_clases}: verifícalo con exportar_onnx.py")
    mapa = MapaDeClases.desde_json(ruta_clases)
    base = DetectorRFDETR(args.pesos, variante=args.variante, mapa=mapa, umbral=args.umbral)

    x1, y1, x2, y2 = (int(v) for v in args.recorte.split(","))
    muestra = cv2.imread(str(args.lote / archivos[0]))
    if muestra is None:
        sys.exit(f"no se pudo leer {archivos[0]}")
    alto, ancho = muestra.shape[:2]
    recorte = Caja(x1 / ancho, y1 / alto, x2 / ancho, y2 / alto)
    mosaico = DetectorMosaico(base, Mosaico(recorte, args.factor, args.lado, args.objeto_max_px))
    mosaico.validar(ancho, alto)

    imagenes = []
    cuenta = dict.fromkeys(ClaseDetectada, 0)
    for n, archivo in enumerate(archivos, start=1):
        cuadro = cv2.imread(str(args.lote / archivo))
        if cuadro is None:
            sys.exit(f"no se pudo leer {archivo}")
        del_mosaico = mosaico.detectar(cuadro, cuadro_idx=n, capture_ts=INSTANTE)
        del_cuadro = base.detectar(cuadro, cuadro_idx=n, capture_ts=INSTANTE)
        detecciones = combinar(del_mosaico, del_cuadro, recorte)
        for d in detecciones:
            cuenta[d.clase] += 1
        imagenes.append((archivo, cuadro.shape[1], cuadro.shape[0], detecciones))
        if n % 20 == 0:
            print(f"  {n}/{len(archivos)}", flush=True)

    coco = a_coco(imagenes)
    coco["info"] = {"description": f"pre-etiquetas {base.version} / {mosaico.version}"}
    args.salida.write_text(json.dumps(coco), encoding="utf-8")
    previas = {str(c): v for c, v in cuenta.items() if v}
    print(
        f"{len(imagenes)} imágenes, {len(coco['annotations'])} cajas "
        f"({previas} antes del mínimo de 10 px) -> {args.salida}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
