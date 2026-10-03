"""Exporta a ONNX el modelo que dejó `entrenar.py` y verifica que vea lo mismo (#31).

    uv run python scripts/exportar_onnx.py ~/modelos/rfdetr-n-epp-v1 ~/datos/gepp/epp-v1

Escribe `<nombre>.onnx` y `<nombre>.clases.json` en la carpeta del modelo. Antes y después,
dos comprobaciones que se detienen si fallan:

1. **Qué clase es cada id.** El mapa sale del checkpoint, pero no se le cree sin más: en
   RF-DETR, `predict` devuelve el índice de `class_names` (0 = persona) después de entrenar
   y el id de categoría COCO (1 = persona) en el modelo preentrenado. El mapa se contrasta
   con las cajas verdaderas de validación, **id por id**: cada clase necesita al menos
   `--pares-minimos` contrastes y acertar `--acuerdo-minimo`. El acuerdo global no basta: con
   una muestra casi toda de cascos, un mapa con persona y chaleco intercambiados acierta 100 %.
   La muestra de validación se estratifica para que traiga las tres clases.
2. **ONNX y PyTorch ven lo mismo** sobre las mismas imágenes: las mismas cajas (IoU >= 0,9)
   y confianzas a menos de 0,02, como `tests/test_detector_rfdetr.py`.

El resultado queda en `verificacion.json`, que es lo que se pega en el issue del modelo.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import cv2
from gepp_core import Caja, ClaseDetectada
from gepp_vision.detectores.rfdetr import VARIANTES
from gepp_vision.detectores.rfdetr_comun import UMBRAL_CONFIANZA, MapaDeClases
from gepp_vision.entrenamiento import (
    acierto_por_id,
    emparejar,
    muestra_estratificada,
    pares_con_verdad,
)

#: Umbral para contrastar ids con la verdad: solo detecciones de las que el modelo está seguro.
UMBRAL_MAPA = 0.5
#: Lejos del corte del detector, para no comparar detecciones que en un adaptador quedan
#: justo encima del umbral y en el otro justo debajo.
FIRME = UMBRAL_CONFIANZA + 0.05
INSTANTE = datetime(2000, 1, 1, tzinfo=UTC)


def imagenes_de_validacion(
    dataset: Path, n: int
) -> list[tuple[Path, list[tuple[ClaseDetectada, Caja]]]]:
    """Las primeras `n` imágenes de validación con sus cajas verdaderas, normalizadas."""
    coco = json.loads((dataset / "valid/_annotations.coco.json").read_text(encoding="utf-8"))
    nombre = {int(c["id"]): ClaseDetectada(c["name"]) for c in coco["categories"]}
    tamano = {int(i["id"]): (int(i["width"]), int(i["height"])) for i in coco["images"]}
    verdad: dict[int, list[tuple[ClaseDetectada, Caja]]] = {}
    for a in coco["annotations"]:
        ancho, alto = tamano[int(a["image_id"])]
        x, y, w, h = (float(v) for v in a["bbox"])
        if w > 0 and h > 0:
            caja = Caja(x / ancho, y / alto, (x + w) / ancho, (y + h) / alto)
            verdad.setdefault(int(a["image_id"]), []).append((nombre[int(a["category_id"])], caja))
    todas = [
        (dataset / "valid" / i["file_name"], verdad.get(int(i["id"]), [])) for i in coco["images"]
    ]
    por_ruta = dict(todas)
    claves = [(ruta, [c for c, _ in cajas]) for ruta, cajas in todas]
    return [(r, por_ruta[r]) for r in muestra_estratificada(claves, n, minimo_por_clase=15)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("modelo", type=Path, help="carpeta de salida de entrenar.py")
    p.add_argument("dataset", type=Path)
    p.add_argument("--variante", default="nano", choices=sorted(VARIANTES))
    p.add_argument("--nombre", help="por defecto, el nombre de la carpeta del modelo")
    p.add_argument("--imagenes", type=int, default=200)
    p.add_argument("--acuerdo-minimo", type=float, default=0.8, help="acierto mínimo por clase")
    p.add_argument("--pares-minimos", type=int, default=10, help="contrastes mínimos por clase")
    p.add_argument("--umbral-mapa", type=float, default=UMBRAL_MAPA)
    args = p.parse_args(argv)
    carpeta, dataset = args.modelo.expanduser(), args.dataset.expanduser()
    nombre = args.nombre or carpeta.name
    pesos = carpeta / "checkpoint_best_total.pth"
    if not pesos.exists():
        sys.exit(f"no está {pesos}: ¿terminó entrenar.py?")

    import rfdetr  # extra `gpu`
    from gepp_vision.detectores.rfdetr import usar_precision_completa
    from PIL import Image

    usar_precision_completa()  # el mapa se verifica con el mismo cálculo que se despliega (#109)

    modelo = getattr(rfdetr, VARIANTES[args.variante])(pretrain_weights=str(pesos))
    mapa = MapaDeClases(nombre, {i: ClaseDetectada(n) for i, n in enumerate(modelo.class_names)})
    muestra = imagenes_de_validacion(dataset, args.imagenes)

    # 1. Qué clase es cada id, contra la verdad.
    pares: list[tuple[int, ClaseDetectada]] = []
    for ruta, verdad in muestra:
        imagen = Image.open(ruta).convert("RGB")
        r = modelo.predict(imagen, threshold=args.umbral_mapa)
        predichas = []
        for xyxy, cid in zip(r.xyxy, r.class_id, strict=True):
            x1, y1 = max(xyxy[0] / imagen.width, 0.0), max(xyxy[1] / imagen.height, 0.0)
            x2, y2 = min(xyxy[2] / imagen.width, 1.0), min(xyxy[3] / imagen.height, 1.0)
            if x2 > x1 and y2 > y1:
                predichas.append((int(cid), Caja(x1, y1, x2, y2)))
        pares += pares_con_verdad(predichas, verdad)
    por_id = acierto_por_id(pares, mapa.clases)
    tabla = Counter(f"id {i} sobre {c}" for i, c in pares)
    fallas = []
    for i, (aciertos, total) in por_id.items():
        acierto = aciertos / total if total else 0.0
        print(f"  id {i} = {mapa.clases[i]}: acierta {aciertos} de {total} ({acierto:.0%})")
        if total < args.pares_minimos:
            fallas.append(f"{mapa.clases[i]}: solo {total} contrastes (< {args.pares_minimos})")
        elif acierto < args.acuerdo_minimo:
            fallas.append(f"{mapa.clases[i]}: acierta {acierto:.0%} (< {args.acuerdo_minimo:.0%})")
    if fallas:
        for clave, n in tabla.most_common():
            print(f"    {clave}: {n}")
        sys.exit(f"el mapa no queda verificado ({'; '.join(fallas)}): no se exporta")

    # 2. Exportar y comparar con PyTorch.
    onnx = Path(modelo.export(output_dir=str(carpeta), output_name=nombre))
    clases_json = MapaDeClases.junto_a(onnx)
    clases_json.write_text(
        json.dumps({"version": nombre, "clases": {str(i): str(c) for i, c in mapa.clases.items()}})
    )
    from gepp_vision.detectores import DetectorOnnx
    from gepp_vision.detectores.rfdetr import DetectorRFDETR

    pytorch = DetectorRFDETR(pesos, variante=args.variante, mapa=mapa)
    exportado = DetectorOnnx(onnx, mapa=mapa)
    iguales, comparadas, distintas = 0, 0, []
    for ruta, _ in muestra:
        cuadro = cv2.imread(str(ruta))
        if cuadro is None:
            sys.exit(f"no se pudo leer {ruta}")
        a = [
            d
            for d in exportado.detectar(cuadro, cuadro_idx=0, capture_ts=INSTANTE)
            if d.confianza >= FIRME
        ]
        b = [
            d
            for d in pytorch.detectar(cuadro, cuadro_idx=0, capture_ts=INSTANTE)
            if d.confianza >= FIRME
        ]
        pares_ab = emparejar(a, b)
        comparadas += len(b)
        if len(pares_ab) == len(a) == len(b) and all(
            abs(x.confianza - y.confianza) <= 0.02 for x, y in pares_ab
        ):
            iguales += 1
        else:
            distintas.append(ruta.name)
    print(
        f"ONNX y PyTorch coinciden en {iguales} de {len(muestra)} imágenes "
        f"({comparadas} detecciones de PyTorch comparadas)"
    )

    verificacion = {
        "modelo": nombre,
        "onnx": onnx.name,
        "clases": {str(i): str(c) for i, c in mapa.clases.items()},
        "mapa_verificado": {
            "por_id": {str(i): {"aciertos": a, "contrastes": t} for i, (a, t) in por_id.items()},
            "umbral": args.umbral_mapa,
            "detalle": dict(tabla),
        },
        "onnx_vs_pytorch": {
            "iguales": iguales,
            "imagenes": len(muestra),
            "detecciones_comparadas": comparadas,
            "distintas": distintas,
        },
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (carpeta / "verificacion.json").write_text(
        json.dumps(verificacion, indent=2, ensure_ascii=False)
    )
    if comparadas == 0:  # dos modelos mudos "coinciden" en todo: eso no verifica nada
        sys.exit("ninguna detección sobre el umbral: la comparación ONNX-PyTorch no probó nada")
    if distintas:
        sys.exit(f"ONNX y PyTorch difieren en {len(distintas)} imágenes: {distintas[:5]}")
    print(f"listo: {onnx} y {clases_json.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
