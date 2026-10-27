"""Une los datasets descargados en uno solo, en el formato COCO que lee `rfdetr` (#31).

    uv run python scripts/preparar_dataset.py ~/datos/gepp/crudos ~/datos/gepp/epp-v2 \
        --pesos-coco ~/modelos/rf-detr-medium.pth --variante medium \
        --pesos-epp ~/modelos/rfdetr-n-epp-v1/checkpoint_best_total.pth \
        --clases-epp ~/modelos/rfdetr-n-epp-v1/rfdetr-n-epp-v1.clases.json

1. Lee cada fuente de `fuentes.yaml` (COCO de Roboflow o VOC de Kaggle) y traduce sus
   categorías a persona / casco / chaleco. Una categoría no declarada detiene todo.
2. Si la fuente no marca todas las personas, el detector COCO propone las que faltan; si no
   marca todos los cascos o chalecos, los propone el modelo EPP (`--pesos-epp`). Las dos
   con umbral alto, y se agregan como `automatica`. `--sin-completar` omite los dos;
   `--sin-epp` solo el EPP, para la primera ronda, cuando todavía no hay modelo.
3. Respeta la partición de la fuente (train/valid/test), salvo para las imágenes que vienen
   de un video (`grupos` en fuentes.yaml): ese video entero va a una sola partición. Si la
   fuente no trae partición, reparte 80/10/10 por hash del nombre. Quita de entrenamiento lo
   que se parezca a validación o prueba, y al final lo comprueba con `verificar_particion`.
4. Escribe `SALIDA/{train,valid,test}/` en el formato que lee `rfdetr` y `resumen.json` con
   los conteos que van al manifiesto y al issue del experimento.

Lote 5 (epp-v4): fuente `lote5-cctv-cc`, `origen.tipo: cvat`. Es corrección humana en CVAT de
cuadros de video CC BY, y entra a entrenar y validar, nunca a probar. En `CRUDOS/lote5-cctv-cc/`:

    exportes/   los export «COCO 1.0» de CVAT: `.zip` (uno por tarea o por proyecto) o `.json`
                suelto. Un zip se lee sin extraerlo; solo cuenta `annotations/*.json`.
    cuadros/    los cuadros originales, `cuadros/<id de video>/<id>_00001.jpg` (en la máquina:
                `ln -s ~/datos/gepp/cctv-cc/cuadros CRUDOS/lote5-cctv-cc/cuadros`). El export
                no se usa para las imágenes: se leen de aquí, a resolución original.

El video sale del nombre del cuadro (`<id>_NNNNN.jpg`). Cada video va entero a una partición:
`particion` en fuentes.yaml dice cuáles van a `valid`; el resto, a `train`. Sin completar: la
fuente declara las cinco clases exhaustivas, así que ni COCO ni el modelo EPP proponen nada
(y no hace falta `--pesos-epp` por ella). Las etiquetas de imagen de CVAT (`tiene_pequenos`,
`negativo_duro`, `grupo_denso`) no son cajas: el COCO no las trae y, si una categoría sin cajas
llegara, no se cuenta. Los atributos (`origen`, `puesto`, `ocluida`) no se usan. Un archivo del
video de prueba (`GPCHfE_-XQE`) en cualquier fuente detiene la preparación.

Todo queda fuera del repositorio. Necesita el extra `gpu` solo para completar.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
from gepp_core import Caja, ClaseDetectada
from gepp_vision.dataset import Imagen, Particion, dhash, verificar_particion
from gepp_vision.detectores.rfdetr_comun import MapaDeClases
from gepp_vision.entrenamiento import (
    Anotada,
    Fuente,
    a_coco,
    cargar_fuentes,
    completar_clases,
    desde_coco,
    desde_voc,
    es_del_video_de_prueba,
    grupo,
    particion_de_video,
    particion_estable,
    quitar_fugas,
)

if TYPE_CHECKING:
    from gepp_vision.detectores.rfdetr import DetectorRFDETR

RAIZ = Path(__file__).resolve().parent
PERSONA, CASCO, CHALECO = ClaseDetectada.PERSONA, ClaseDetectada.CASCO, ClaseDetectada.CHALECO
VALIDACION = Particion.VALIDACION
CARPETA = {
    Particion.ENTRENAMIENTO: "train",
    Particion.VALIDACION: "valid",
    Particion.PRUEBA: "test",
}
#: Umbral de los detectores al completar: una caja inventada enseña mal.
UMBRAL_COMPLETAR = 0.6
#: `Deteccion` exige un instante con zona; aquí no hay video, así que es fijo.
INSTANTE = datetime(2000, 1, 1, tzinfo=UTC)

#: (fuente, imagen, ruta, partición, video de origen o None)
Registro = tuple[Fuente, Anotada, Path, Particion, str | None]


def _exportes_cvat(carpeta: Path) -> Iterator[dict]:
    """Cada COCO de CVAT de `carpeta/exportes`: `.json` suelto o `annotations/*.json` de un zip."""
    exportes = sorted((carpeta / "exportes").glob("*"))
    if not exportes:
        sys.exit(f"{carpeta}/exportes está vacía: deja ahí los export COCO 1.0 de CVAT")
    for ruta in exportes:
        if ruta.suffix == ".json":
            yield json.loads(ruta.read_text(encoding="utf-8"))
        elif ruta.suffix == ".zip":
            with zipfile.ZipFile(ruta) as z:
                nombres = [n for n in z.namelist() if re.fullmatch(r"annotations/[^/]+\.json", n)]
                if not nombres:
                    sys.exit(f"{ruta}: no trae annotations/*.json (¿es un export COCO 1.0?)")
                for n in nombres:
                    yield json.loads(z.read(n))


def _crudos_cvat(fuente: Fuente, carpeta: Path) -> Iterator[tuple[Anotada, Path, Particion]]:
    vistos: set[str] = set()
    for coco in _exportes_cvat(carpeta):
        for img in desde_coco(coco, fuente):
            img.archivo = Path(img.archivo).name
            m = re.search(fuente.grupos[0], img.archivo)  # el mismo patrón que `grupo`
            if m is None:
                sys.exit(f"{fuente.nombre}: {img.archivo} no es `<id de video>_NNNNN.jpg`")
            if img.archivo in vistos:
                sys.exit(
                    f"{fuente.nombre}: {img.archivo} está en dos export (¿una tarea repetida?)"
                )
            vistos.add(img.archivo)
            ruta = carpeta / "cuadros" / m.group(1) / img.archivo
            if not ruta.exists():
                sys.exit(f"{fuente.nombre}: falta el cuadro {ruta}")
            # La partición real la fija `leer_fuente` por video; este valor no se usa.
            yield img, ruta, Particion.ENTRENAMIENTO


def _crudos(fuente: Fuente, carpeta: Path) -> Iterator[tuple[Anotada, Path, Particion]]:
    if fuente.origen.get("tipo") == "cvat":
        yield from _crudos_cvat(fuente, carpeta)
        return
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
        if es_del_video_de_prueba(img.archivo):
            sys.exit(
                f"{fuente.nombre}: {img.archivo} es del video de prueba: no entra a ningún lado"
            )
        video = grupo(img.archivo, fuente)
        if video is None and fuente.por_defecto is not None:
            sys.exit(
                f"{fuente.nombre}: {img.archivo} no dice de qué video es: no se parte por cuadro"
            )
        if video is not None and fuente.videos and video not in fuente.videos:
            sys.exit(f"{fuente.nombre}: el video {video!r} no está en `videos` de fuentes.yaml")
        if video is not None:
            particion = particion_de_video(video, fuente)
        yield fuente, img, ruta, particion, video


def detector_coco(pesos: Path, variante: str) -> DetectorRFDETR:
    from gepp_vision.detectores.rfdetr import DetectorRFDETR

    mapa = MapaDeClases("coco", {1: ClaseDetectada.PERSONA})  # id 1 = person en COCO
    return DetectorRFDETR(pesos, variante=variante, mapa=mapa, umbral=UMBRAL_COMPLETAR)


def detector_epp(pesos: Path, clases: Path, variante: str) -> DetectorRFDETR:
    from gepp_vision.detectores.rfdetr import DetectorRFDETR

    if not clases.exists():
        sys.exit(f"falta el mapa de clases {clases}: verifícalo con exportar_onnx.py")
    mapa = MapaDeClases.desde_json(clases)
    return DetectorRFDETR(pesos, variante=variante, mapa=mapa, umbral=UMBRAL_COMPLETAR)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("crudos", type=Path)
    p.add_argument("salida", type=Path)
    p.add_argument("--fuentes", type=Path, default=RAIZ / "fuentes.yaml")
    p.add_argument("--pesos-coco", type=Path)
    p.add_argument("--variante", default="medium")
    p.add_argument("--pesos-epp", type=Path, help="modelo EPP que completa casco y chaleco")
    p.add_argument("--clases-epp", type=Path, help="por defecto, el de junto a los pesos")
    p.add_argument("--variante-epp", default="nano")
    p.add_argument("--sin-epp", action="store_true", help="primera ronda: no hay modelo EPP")
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
    epp = None
    sin_epp = [f.nombre for f in fuentes if not {CASCO, CHALECO} <= f.exhaustivas]
    if not (args.sin_completar or args.sin_epp) and sin_epp:
        if args.pesos_epp is None:
            sys.exit(
                f"falta --pesos-epp: {sin_epp} no marcan todos los cascos o chalecos "
                "(o --sin-epp en la primera ronda, cuando todavía no hay modelo)"
            )
        pesos_epp = args.pesos_epp.expanduser()
        clases_epp = (args.clases_epp or MapaDeClases.junto_a(pesos_epp)).expanduser()
        epp = detector_epp(pesos_epp, clases_epp, args.variante_epp)

    registros: list[tuple[Registro, int, list[tuple[ClaseDetectada, Caja]]]] = []
    ilegibles: Counter[str] = Counter()
    for fuente in fuentes:
        for n, registro in enumerate(leer_fuente(fuente, crudos / fuente.nombre)):
            if args.limite is not None and n >= args.limite:
                break
            _, img, ruta, _, _ = registro
            imagen = cv2.imread(str(ruta))
            if imagen is None:
                ilegibles[fuente.nombre] += 1
                continue
            propuestas: list[tuple[ClaseDetectada, Caja]] = []
            if detector is not None and PERSONA not in fuente.exhaustivas:
                detectadas = detector.detectar(imagen, cuadro_idx=0, capture_ts=INSTANTE)
                propuestas += [(PERSONA, d.caja) for d in detectadas]
            if epp is not None and not {CASCO, CHALECO} <= fuente.exhaustivas:
                detectadas = epp.detectar(imagen, cuadro_idx=0, capture_ts=INSTANTE)
                propuestas += [(d.clase, d.caja) for d in detectadas if d.clase is not PERSONA]
            automaticas = completar_clases(img, propuestas, fuente.exhaustivas)
            registros.append((registro, dhash(imagen), automaticas))
        print(
            f"  {fuente.nombre}: {sum(r[0][0] is fuente for r in registros)} imágenes leídas",
            flush=True,
        )

    fugas = quitar_fugas([h for _, h, _ in registros], [r[3] for r, _, _ in registros])
    if args.limite is not None:
        print(f"  AVISO: --limite {args.limite}: preparación incompleta, no sirve para entrenar")
    for fuente in fuentes:  # sobre lo que sobrevive a las fugas, no sobre lo leído
        en_valid = {
            r[4]
            for i, (r, _, _) in enumerate(registros)
            if i not in fugas and r[0] is fuente and r[3] is VALIDACION
        }
        if args.limite is None and fuente.validacion and en_valid != fuente.validacion:
            sys.exit(
                f"{fuente.nombre}: `valid` pide {sorted(fuente.validacion)} y quedaron "
                f"{sorted(en_valid)} (¿fugas contra otra partición?): sin ellos no hay validación"
            )
    conteo: Counter[str] = Counter()
    por_particion: dict[Particion, list[tuple[Anotada, str, list[tuple[ClaseDetectada, Caja]]]]] = {
        p: [] for p in CARPETA
    }
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
        for clase, _ in automaticas:
            conteo[f"{fuente.nombre}/{particion}/{clase}_automatica"] += 1

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
        else {
            "modelo": detector.version,
            "modelo_epp": None if epp is None else epp.version,
            "umbral": UMBRAL_COMPLETAR,
        },
        "limite": args.limite,  # no nulo = preparación incompleta
        "ilegibles": dict(ilegibles),
        "conteo": dict(sorted(conteo.items())),
    }
    (salida / "resumen.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False))
    for clave, valor in sorted(conteo.items()):
        print(f"  {clave:55s} {valor:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
