"""Nivel 1 del plan de evaluación (#31): ¿el modelo ve los objetos?

mAP50 y mAP50-95 con pycocotools, por clase, en total y por tamaño, más precisión y recall al
umbral de la regla. Especificación: `docs/arquitectura/04-evaluar-niveles-0-1.md`.
"""

from __future__ import annotations

import contextlib
import io
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval, Params

from gepp_vision.entrenamiento import _asignar
from gepp_vision.evaluacion.coco import CLASES, ArchivoCoco, CajaPx, Recorte, en_region

#: Una predicción acierta si su IoU con una caja verdadera de la misma clase llega a esto.
UMBRAL_IOU = 0.5
#: La confianza con la que la regla abre un hallazgo (`gepp_core.asociacion`).
UMBRAL_REGLA = 0.45
#: COCO evalúa 100 predicciones por imagen y clase; con umbral 0,05 y mosaico se pasa.
MAX_DETS = 300
#: Rangos de área de COCO, en el orden de `Params.areaRng`. Un borde (32², 96²) cuenta en los
#: dos rangos vecinos: es la regla de pycocotools y se respeta también sin predicciones.
TAMANOS: tuple[str, ...] = ("todos", "chico", "mediano", "grande")
_RANGOS: list[list[float]] = Params(iouType="bbox").areaRng


@dataclass(frozen=True, slots=True)
class MetricasClase:
    clase: str
    n_verdad: int
    n_predichas: int  # sobre el umbral de confianza
    map50: float | None  # None: la clase no tiene cajas verdaderas en la región
    map50_95: float | None
    map50_95_por_tamano: dict[str, float | None]
    precision: float | None  # None: ninguna predicción sobre el umbral
    recall: float | None  # None: ninguna caja verdadera


@dataclass(frozen=True, slots=True)
class MetricasRegion:
    map50: float | None
    map50_95: float | None
    map50_95_por_tamano: dict[str, float | None]
    max_predicciones: int  # en una imagen y una clase: si pasa de MAX_DETS, se perdieron
    clases: tuple[MetricasClase, ...]


def evaluar(
    verdad: Sequence[CajaPx],
    predichas: Sequence[CajaPx],
    tamanos_imagen: Mapping[str, tuple[int, int]],
    umbral: float = UMBRAL_REGLA,
) -> MetricasRegion:
    """Métricas de una región. `tamanos_imagen` fija qué imágenes se evalúan: todas, aunque
    alguna no tenga cajas, porque una predicción en un cuadro vacío es un falso positivo."""
    if not 0 < umbral <= 1:
        raise ValueError(f"umbral fuera de (0, 1]: {umbral}")
    p = _precision_coco(verdad, predichas, tamanos_imagen)

    clases = []
    for k, clase in enumerate(CLASES):
        v = [c for c in verdad if c.clase == clase]
        aciertos, n_predichas = _aciertos(v, [c for c in predichas if c.clase == clase], umbral)
        if p is None:
            por_tamano = {t: _sin_predicciones(v, a) for a, t in enumerate(TAMANOS)}
            map50 = por_tamano["todos"]
        else:
            por_tamano = {t: _promedio(p[:, :, k, a]) for a, t in enumerate(TAMANOS)}
            map50 = _promedio(p[0, :, k, 0])
        clases.append(
            MetricasClase(
                clase=clase,
                n_verdad=len(v),
                n_predichas=n_predichas,
                map50=map50,
                map50_95=por_tamano["todos"],
                map50_95_por_tamano=por_tamano,
                precision=aciertos / n_predichas if n_predichas else None,
                recall=aciertos / len(v) if v else None,
            )
        )

    if p is None:
        total = {t: _sin_predicciones(verdad, a) for a, t in enumerate(TAMANOS)}
        total50 = total["todos"]
    else:
        total = {t: _promedio(p[:, :, :, a]) for a, t in enumerate(TAMANOS)}
        total50 = _promedio(p[0, :, :, 0])
    por_imagen = Counter((c.archivo, c.clase) for c in predichas)
    return MetricasRegion(
        map50=total50,
        map50_95=total["todos"],
        map50_95_por_tamano=total,
        max_predicciones=max(por_imagen.values(), default=0),
        clases=tuple(clases),
    )


def evaluar_regiones(
    verdad: ArchivoCoco,
    predichas: ArchivoCoco,
    imagenes: Sequence[str],
    recorte: Recorte,
    umbral: float = UMBRAL_REGLA,
) -> dict[str, MetricasRegion]:
    """Dentro y fuera del foso, por separado, sobre las mismas imágenes (las de
    `coco.imagenes_comunes`)."""
    tamanos = {a: verdad.imagenes[a] for a in imagenes}
    v = [c for c in verdad.cajas if c.archivo in tamanos]
    p = [c for c in predichas.cajas if c.archivo in tamanos]
    return {
        region: evaluar(
            en_region(v, recorte, dentro=adentro),
            en_region(p, recorte, dentro=adentro),
            tamanos,
            umbral,
        )
        for region, adentro in (("dentro", True), ("fuera", False))
    }


def _precision_coco(
    verdad: Sequence[CajaPx],
    predichas: Sequence[CajaPx],
    tamanos_imagen: Mapping[str, tuple[int, int]],
) -> np.ndarray | None:
    """`COCOeval.eval["precision"]` con `maxDets` en 300: [umbral IoU, recall, clase, área].

    Se lee el arreglo y no `summarize()`, que para los tamaños vuelve a usar 100. None si no hay
    predicciones: `loadRes([])` de pycocotools se cae con IndexError.
    """
    if not predichas:
        return None
    ids = {archivo: i for i, archivo in enumerate(sorted(tamanos_imagen), start=1)}
    categoria = {clase: k for k, clase in enumerate(CLASES, start=1)}
    gt = COCO()
    gt.dataset = {
        "images": [
            {"id": i, "width": tamanos_imagen[a][0], "height": tamanos_imagen[a][1]}
            for a, i in ids.items()
        ],
        "categories": [{"id": k, "name": c} for c, k in categoria.items()],
        "annotations": [
            {
                "id": n,
                "image_id": ids[c.archivo],
                "category_id": categoria[c.clase],
                "bbox": [c.x, c.y, c.ancho, c.alto],
                "area": c.area,
                "iscrowd": 0,
            }
            for n, c in enumerate(verdad, start=1)
        ],
    }
    detecciones = [
        {
            "image_id": ids[c.archivo],
            "category_id": categoria[c.clase],
            "bbox": [c.x, c.y, c.ancho, c.alto],
            "score": c.score,
        }
        for c in predichas
    ]
    with contextlib.redirect_stdout(io.StringIO()):  # pycocotools imprime su avance
        gt.createIndex()
        e = COCOeval(gt, gt.loadRes(detecciones), "bbox")
        e.params.maxDets = [1, 10, MAX_DETS]
        e.evaluate()
        e.accumulate()
    precision: np.ndarray = e.eval["precision"][..., -1]
    return precision


def _promedio(valores: np.ndarray) -> float | None:
    """Promedio de COCO: -1 marca «sin cajas verdaderas» y no entra."""
    validos = valores[valores > -1]
    return float(validos.mean()) if validos.size else None


def _sin_predicciones(verdad: Sequence[CajaPx], a: int) -> float | None:
    """Sin predicciones no hay curva: 0 si hay verdad en ese rango de área, None si no."""
    desde, hasta = _RANGOS[a]
    return 0.0 if any(desde <= c.area <= hasta for c in verdad) else None


def _aciertos(
    verdad: Sequence[CajaPx], predichas: Sequence[CajaPx], umbral: float
) -> tuple[int, int]:
    """(aciertos, predicciones sobre el umbral) de una clase, imagen por imagen, con el
    emparejamiento óptimo: una caja verdadera por predicción."""
    sobre = [c for c in predichas if c.score is not None and c.score >= umbral]
    aciertos = 0
    for archivo in {c.archivo for c in sobre}:
        p = [c for c in sobre if c.archivo == archivo]
        v = [c for c in verdad if c.archivo == archivo]
        iou = np.array([[a.iou(b) for b in v] for a in p])
        aciertos += len(_asignar(iou, UMBRAL_IOU))
    return aciertos, len(sobre)
