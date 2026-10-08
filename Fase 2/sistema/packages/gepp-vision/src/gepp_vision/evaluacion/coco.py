"""Lectura de COCO 1.0 para evaluar (#31): la verdad de CVAT y las predicciones de `a_coco`.

Las imágenes se emparejan por `file_name` y las categorías por nombre: los `id` dependen de
quién escribió el archivo. CVAT numera según el orden de las etiquetas del proyecto; `a_coco`,
según `CLASES_V1`. Especificación: `docs/arquitectura/04-evaluar-niveles-0-1.md`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from gepp_vision.entrenamiento import CLASES_V1
from gepp_vision.etiquetado import ETIQUETAS_IMAGEN

#: Clases que se evalúan, en el orden de `CLASES_V1`.
CLASES: tuple[str, ...] = tuple(str(c) for c in CLASES_V1)

#: Etiquetas de imagen (tags) de CVAT: la exportación COCO 1.0 las trae en `categories`, sin
#: cajas (comprobado el 4-oct con la tarea `prueba-youtube-lote0` y `tiene_pequenos`). Salen de
#: `etiquetado.ETIQUETAS_IMAGEN`, la misma lista que valida la revisión de etiquetas.
IGNORADAS = ETIQUETAS_IMAGEN

#: x1, y1, x2, y2 en px del cuadro.
Recorte = tuple[float, float, float, float]


class EntradaInvalida(ValueError):
    """El archivo COCO no se puede evaluar tal como está."""


@dataclass(frozen=True, slots=True)
class CajaPx:
    """Una caja de COCO en px, con el formato de COCO: esquina superior izquierda y tamaño."""

    archivo: str
    clase: str
    x: float
    y: float
    ancho: float
    alto: float
    score: float | None = None

    @property
    def area(self) -> float:
        return self.ancho * self.alto

    @property
    def centro(self) -> tuple[float, float]:
        return (self.x + self.ancho / 2, self.y + self.alto / 2)

    def iou(self, otra: CajaPx) -> float:
        ix = min(self.x + self.ancho, otra.x + otra.ancho) - max(self.x, otra.x)
        iy = min(self.y + self.alto, otra.y + otra.alto) - max(self.y, otra.y)
        interseccion = max(0.0, ix) * max(0.0, iy)
        return interseccion / (self.area + otra.area - interseccion)


@dataclass(frozen=True, slots=True)
class ArchivoCoco:
    imagenes: dict[str, tuple[int, int]]  # file_name -> (ancho, alto)
    cajas: tuple[CajaPx, ...]
    descripcion: str  # `info.description`: en las predicciones, la versión del modelo


def leer_coco(datos: Mapping[str, Any], *, predicciones: bool) -> ArchivoCoco:
    """Normaliza un COCO 1.0. Con `predicciones`, cada caja tiene que traer `score`; en la
    verdad el `score` se descarta."""
    nombres: dict[int, str] = {}
    for categoria in datos["categories"]:
        nombre = str(categoria["name"])
        if nombre not in CLASES and nombre not in IGNORADAS:
            raise EntradaInvalida(f"categoría desconocida: {nombre!r}")
        nombres[categoria["id"]] = nombre

    imagenes: dict[str, tuple[int, int]] = {}
    archivo_de: dict[int, str] = {}
    for imagen in datos["images"]:
        archivo = str(imagen["file_name"])
        if archivo in imagenes:
            raise EntradaInvalida(f"imagen repetida: {archivo}")
        imagenes[archivo] = (int(imagen["width"]), int(imagen["height"]))
        archivo_de[imagen["id"]] = archivo

    cajas: list[CajaPx] = []
    for anotacion in datos["annotations"]:
        if anotacion["category_id"] not in nombres:
            raise EntradaInvalida(f"anotación {anotacion['id']}: categoría inexistente")
        if anotacion["image_id"] not in archivo_de:
            raise EntradaInvalida(f"anotación {anotacion['id']}: imagen inexistente")
        clase = nombres[anotacion["category_id"]]
        if clase in IGNORADAS:
            continue
        archivo = archivo_de[anotacion["image_id"]]
        x, y, ancho, alto = (float(v) for v in anotacion["bbox"])
        if ancho <= 0 or alto <= 0:
            raise EntradaInvalida(f"{archivo}: caja sin área, anotación {anotacion['id']}")
        score = anotacion.get("score")
        if predicciones and score is None:
            raise EntradaInvalida(
                f"{archivo}: predicción sin score. ¿Pasaste la verdad como predicciones?"
            )
        cajas.append(
            CajaPx(archivo, clase, x, y, ancho, alto, float(score) if predicciones else None)
        )

    info = datos.get("info") or {}
    return ArchivoCoco(imagenes, tuple(cajas), str(info.get("description", "")))


def imagenes_comunes(
    verdad: ArchivoCoco, predichas: ArchivoCoco, solo: Iterable[str] | None = None
) -> list[str]:
    """Imágenes a evaluar, en orden: las de la verdad, o las de `solo`. Cada una tiene que
    estar en las predicciones con el mismo tamaño; las predicciones que sobran se ignoran."""
    nombres = sorted(verdad.imagenes if solo is None else set(solo))
    if not nombres:
        raise EntradaInvalida("no queda ninguna imagen que evaluar")
    for nombre in nombres:
        if nombre not in verdad.imagenes:
            raise EntradaInvalida(f"{nombre} no está en la verdad")
        if nombre not in predichas.imagenes:
            raise EntradaInvalida(f"{nombre} no está en las predicciones")
        if verdad.imagenes[nombre] != predichas.imagenes[nombre]:
            raise EntradaInvalida(
                f"{nombre}: tamaño distinto en la verdad {verdad.imagenes[nombre]} "
                f"y en las predicciones {predichas.imagenes[nombre]}"
            )
    return nombres


def en_region(cajas: Iterable[CajaPx], recorte: Recorte, *, dentro: bool) -> list[CajaPx]:
    """Las cajas cuyo centro cae dentro (o fuera) del recorte, borde incluido: la misma regla
    que `etiquetado.combinar` y `Caja.contiene`."""
    x1, y1, x2, y2 = recorte

    def adentro(caja: CajaPx) -> bool:
        cx, cy = caja.centro
        return x1 <= cx <= x2 and y1 <= cy <= y2

    return [c for c in cajas if adentro(c) is dentro]
