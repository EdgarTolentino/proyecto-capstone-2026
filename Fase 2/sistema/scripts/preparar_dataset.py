"""Une los datasets descargados en uno solo, en el formato COCO que lee `rfdetr` (#31).

    uv run python scripts/preparar_dataset.py ~/datos/gepp/crudos ~/datos/gepp/epp-v1 \
        --pesos-coco ~/modelos/rf-detr-medium.pth --variante medium

1. Lee cada fuente de `fuentes.yaml` (COCO de Roboflow o VOC de Kaggle) y traduce sus
   categorías a persona / casco / chaleco. Una categoría no declarada detiene todo.
2. Si la fuente no marca a todas las personas, el detector COCO propone las que faltan
   (con umbral alto) y se agregan como `automatica`. `--sin-completar` lo omite.
3. Respeta la partición de la fuente (train/valid/test), salvo para las imágenes que vienen
   de un video (`grupos` en fuentes.yaml): ese video entero va a una sola partición. Si la
   fuente no trae partición, reparte 80/10/10 por hash del nombre. Quita de entrenamiento lo
   que se parezca a validación o prueba, y al final lo comprueba con `verificar_particion`.
4. Escribe `SALIDA/{train,valid,test}/` en el formato que lee `rfdetr` y `resumen.json` con
   los conteos que van al manifiesto y al issue del experimento.

Todo queda fuera del repositorio. Necesita el extra `gpu` solo para completar personas.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
from gepp_core import Caja, ClaseDetectada
from gepp_vision.dataset import Imagen, Particion, dhash, verificar_particion
from gepp_vision.entrenamiento import (
    Anotada,
    Fuente,
    a_coco,
    cargar_fuentes,
    completar,
    desde_coco,
    desde_voc,
    grupo,
    particion_estable,
    quitar_fugas,
)

if TYPE_CHECKING:
    from gepp_vision.detectores.rfdetr import DetectorRFDETR

RAIZ = Path(__file__).resolve().parent
CARPETA = {
    Particion.ENTRENAMIENTO: "train",
    Particion.VALIDACION: "valid",
    Particion.PRUEBA: "test",
}
#: Umbral del detector COCO al completar personas: una persona inventada enseña mal.
UMBRAL_COMPLETAR = 0.6
#: `Deteccion` exige un instante con zona; aquí no hay video, así que es fijo.
INSTANTE = datetime(2000, 1, 1, tzinfo=UTC)

#: (fuente, imagen, ruta, partición, video de origen o None)
Registro = tuple[Fuente, Anotada, Path, Particion, str | None]


def _crudos(fuente: Fuente, carpeta: Path) -> Iterator[tuple[Anotada, Path, Particion]]:
    if fuente.origen.get("formato") == "voc":
        for xml in sorted((carpeta / "annotations").glob("*.xml")):
            img = desde_voc(xml.read_text(encoding="utf-8"), fuente)
            yield img, carpeta / "images" / img.archivo, particion_estable(img.archivo)
        return
    for particion, nombre in CARPETA.items():
        anotaciones = carpeta / nombre / "_annotations.coco.json"
        if anotaciones.exists():
            coco = json.loads(anotaciones.read_text(encoding="utf-8"))
            for img in desde_coco(coco, fuente):
                yield img, carpeta / nombre / img.archivo, particion


def leer_fuente(fuente: Fuente, carpeta: Path) -> Iterator[Registro]:
    """Como viene en la fuente, salvo que un video entero va a una sola partición."""
    for img, ruta, particion in _crudos(fuente, carpeta):
        video = grupo(img.archivo, fuente)
        if video is not None:
            particion = particion_estable(f"{fuente.nombre}/{video}")
        yield fuente, img, ruta, particion, video


def detector_coco(pesos: Path, variante: str) -> DetectorRFDETR:
    from gepp_vision.detectores.rfdetr import DetectorRFDETR
    from gepp_vision.detectores.rfdetr_comun import MapaDeClases

    mapa = MapaDeClases("coco", {1: ClaseDetectada.PERSONA})  # id 1 = person en COCO
    return DetectorRFDETR(pesos, variante=variante, mapa=mapa, umbral=UMBRAL_COMPLETAR)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("crudos", type=Path)
    p.add_argument("salida", type=Path)
    p.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes.yaml")
    p.add_argument("--pesos-coco", type=Path)
    p.add_argument("--variante", default="medium")
    p.add_argument("--sin-completar", action="store_true")
    p.add_argument("--limite", type=int, help="máximo de imágenes por fuente (pruebas rápidas)")
    args = p.parse_args(argv)
    crudos, salida = args.crudos.expanduser(), args.salida.expanduser()

    if salida.exists() and any(salida.iterdir()):
        sys.exit(f"{salida} no está vacía: bórrala o elige otra (no se mezclan corridas)")
    if not args.sin_completar and args.pesos_coco is None:
        sys.exit("falta --pesos-coco (o --sin-completar, que deja personas sin etiquetar)")
    detector = (
        None if args.sin_completar else detector_coco(args.pesos_coco.expanduser(), args.variante)
    )

    fuentes = cargar_fuentes(args.fuentes)
    faltan = [f.nombre for f in fuentes if not (crudos / f.nombre).is_dir()]
    if faltan:
        sys.exit(f"faltan fuentes en {crudos}: {faltan} (corre descargar_datasets.py)")

    registros: list[tuple[Registro, int, list[Caja]]] = []
    ilegibles: Counter[str] = Counter()
    for fuente in fuentes:
        completa = ClaseDetectada.PERSONA in fuente.exhaustivas
        for n, registro in enumerate(leer_fuente(fuente, crudos / fuente.nombre)):
            if args.limite is not None and n >= args.limite:
                break
            _, img, ruta, _, _ = registro
            imagen = cv2.imread(str(ruta))
            if imagen is None:
                ilegibles[fuente.nombre] += 1
                continue
            automaticas: list[Caja] = []
            if detector is not None and not completa:
                propuestas = [
                    d.caja for d in detector.detectar(imagen, cuadro_idx=0, capture_ts=INSTANTE)
                ]
                personas = [c for k, c in img.cajas if k is ClaseDetectada.PERSONA]
                automaticas = completar(personas, propuestas)
            registros.append((registro, dhash(imagen), automaticas))
        print(
            f"  {fuente.nombre}: {sum(r[0][0] is fuente for r in registros)} imágenes leídas",
            flush=True,
        )

    fugas = quitar_fugas([h for _, h, _ in registros], [r[3] for r, _, _ in registros])
    conteo: Counter[str] = Counter()
    por_particion: dict[Particion, list[tuple[Anotada, str, list[Caja]]]] = {p: [] for p in CARPETA}
    escritas: list[Imagen] = []
    for i, ((fuente, img, ruta, particion, video), hash_, automaticas) in enumerate(registros):
        if i in fugas:
            conteo[f"{fuente.nombre}/descartada_por_fuga"] += 1
            continue
        nombre = f"{fuente.nombre}__{Path(img.archivo).name}"
        destino = salida / CARPETA[particion] / nombre
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists():  # dos imágenes con el mismo nombre base: una pisaría a la otra
            sys.exit(f"nombre repetido en la salida: {nombre} (de {ruta})")
        try:
            os.link(ruta, destino)  # mismo disco: no duplica gigas
        except OSError:
            shutil.copy2(ruta, destino)
        escritas.append(Imagen(nombre, f"{fuente.nombre}/{video or nombre}", particion, hash_))
        por_particion[particion].append((img, nombre, automaticas))
        conteo[f"{fuente.nombre}/{particion}/imagenes"] += 1
        if video is not None:
            conteo[f"{fuente.nombre}/{particion}/de_video"] += 1
        for clase, _ in img.cajas:
            conteo[f"{fuente.nombre}/{particion}/{clase}"] += 1
        conteo[f"{fuente.nombre}/{particion}/persona_automatica"] += len(automaticas)

    # La misma guarda que el lote 0: ningún video ni escena en dos particiones.
    verificar_particion(escritas)

    for particion, imagenes in por_particion.items():
        (salida / CARPETA[particion]).mkdir(parents=True, exist_ok=True)
        coco = a_coco(imagenes)
        (salida / CARPETA[particion] / "_annotations.coco.json").write_text(json.dumps(coco))

    resumen = {
        "fuentes": {f.nombre: {"licencia": f.licencia, "origen": f.origen} for f in fuentes},
        "completar": None
        if detector is None
        else {"modelo": detector.version, "umbral": UMBRAL_COMPLETAR},
        "ilegibles": dict(ilegibles),
        "conteo": dict(sorted(conteo.items())),
    }
    (salida / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False))
    for clave, valor in sorted(conteo.items()):
        print(f"  {clave:55s} {valor:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
