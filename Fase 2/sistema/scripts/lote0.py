"""Arma un lote de imágenes para etiquetar desde videos propios (PT-03, lote 0).

    uv run python scripts/lote0.py VIDEOS_DIR SALIDA_DIR --particion particion.yaml \
        [--cada-s 2.0] [--manifiesto datos/lote0.csv]

1. Toma un cuadro cada `--cada-s` segundos con `FuenteArchivo` + `Muestreador` (el mismo
   reloj que el sistema).
2. Descarta los casi duplicados por dHash (`gepp_vision.dataset`).
3. Escribe los JPG en SALIDA_DIR — fuera del repositorio — y el manifiesto CSV
   (archivo, video, partición, hash, doble etiquetado) que SÍ se versiona. El 10 % para
   doble etiquetado sale con semilla fija: la misma corrida elige las mismas imágenes.
4. Verifica la partición: ningún video ni escena en dos particiones.

`particion.yaml` lo escribe una persona, no el script: la regla de dejar cámaras completas y
un día completo en prueba necesita saber qué cámara y qué día es cada video. Formato:

    prueba:        [camara_02_2026-09-24.mp4]
    validacion:    [camara_01_2026-09-25.mp4]
    entrenamiento: [camara_01_2026-09-24.mp4]
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from pathlib import Path

import cv2
import yaml
from gepp_vision.dataset import Imagen, Particion, deduplicar, dhash, verificar_particion
from gepp_worker.fuente_archivo import FuenteArchivo
from gepp_worker.muestreo import Muestreador

EXTENSIONES = {".mp4", ".mov", ".mkv", ".avi"}
#: Fracción del lote que etiquetan dos personas para medir el acuerdo (guía, sección 6).
FRACCION_DOBLE = 0.10
#: Semilla fija: volver a correr el script elige las mismas imágenes para el doble etiquetado.
SEMILLA = 2026


def elegir_doble(n: int, fraccion: float = FRACCION_DOBLE) -> set[int]:
    """Índices del doble etiquetado: al menos una imagen si el lote no está vacío."""
    if n == 0:
        return set()
    return set(random.Random(SEMILLA).sample(range(n), max(1, math.ceil(n * fraccion))))


def leer_particion(ruta: Path) -> dict[str, Particion]:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    asignacion: dict[str, Particion] = {}
    for nombre, videos in datos.items():
        particion = Particion(nombre)
        for video in videos or []:
            if video in asignacion:
                sys.exit(f"{video} aparece en {asignacion[video]} y en {particion}")
            asignacion[video] = particion
    return asignacion


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("videos", type=Path)
    p.add_argument("salida", type=Path)
    p.add_argument("--particion", type=Path, required=True)
    p.add_argument("--cada-s", type=float, default=2.0)
    p.add_argument("--manifiesto", type=Path, default=Path("lote0.csv"))
    args = p.parse_args(argv)

    asignacion = leer_particion(args.particion)
    videos = sorted(v for v in args.videos.iterdir() if v.suffix.lower() in EXTENSIONES)
    sin_particion = [v.name for v in videos if v.name not in asignacion]
    if sin_particion:
        sys.exit(f"videos sin partición en {args.particion}: {sin_particion}")

    args.salida.mkdir(parents=True, exist_ok=True)
    candidatos: list[tuple[str, int, object]] = []
    for video in videos:
        fuente = Muestreador(FuenteArchivo(video), fps_objetivo=1.0 / args.cada_s)
        fuente.abrir()
        try:
            while fuente.tomar():
                cuadro = fuente.recuperar()
                if cuadro is not None:
                    candidatos.append((video.name, cuadro.indice, cuadro.imagen))
        finally:
            fuente.cerrar()

    hashes = [dhash(img) for _, _, img in candidatos]  # type: ignore[arg-type]
    conservados = deduplicar(hashes)
    imagenes: list[Imagen] = []
    for i in conservados:
        video, indice, img = candidatos[i]
        archivo = f"{Path(video).stem}_{indice:06d}.jpg"
        cv2.imwrite(str(args.salida / archivo), img)  # type: ignore[arg-type]
        imagenes.append(Imagen(archivo, video, asignacion[video], hashes[i]))

    verificar_particion(imagenes)
    args.manifiesto.parent.mkdir(parents=True, exist_ok=True)
    with args.manifiesto.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["archivo", "video", "particion", "dhash", "doble_etiquetado"])
        dobles = elegir_doble(len(imagenes))
        for i, img in enumerate(imagenes):
            escritor.writerow(
                [img.archivo, img.video, img.particion.value, f"{img.hash:016x}", int(i in dobles)]
            )

    por_particion = {p.value: sum(1 for i in imagenes if i.particion == p) for p in Particion}
    print(
        f"{len(candidatos)} cuadros muestreados, {len(imagenes)} tras deduplicar "
        f"→ {por_particion}. Manifiesto: {args.manifiesto}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
