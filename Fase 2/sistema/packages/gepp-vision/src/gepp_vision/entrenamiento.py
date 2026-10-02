"""Unión de datasets públicos de EPP en uno solo para entrenar RF-DETR (PT-08, #31).

Cada dataset nombra y etiqueta distinto. Tres cosas se cuidan aquí, porque si fallan el
entrenamiento corre igual y nadie se entera:

1. **Toda categoría de origen se traduce explícitamente.** Una categoría que el archivo de
   fuentes no declara detiene todo (`CategoriaDesconocida`); para descartarla se declara
   como `null`. Así un "person" que en SHWD significa *cabeza sin casco* no entra callado
   como persona.
2. **Una clase que la fuente no etiqueta en todas sus imágenes deja falsos negativos:** una
   persona sin caja es, para el modelo, fondo. `completar` agrega las personas que propone
   un detector COCO, marcadas como `automatica` para poder auditarlas.
3. **Los cuadros de un mismo video no se reparten entre particiones.** Roboflow parte por
   cuadro; `grupo` reconoce el video en el nombre del archivo (patrones de `fuentes.yaml`) y
   todo el grupo va a una sola partición. Las casi copias que quedan sin grupo las saca
   `quitar_fugas` por dHash. El dHash solo no basta: cuadros del mismo video quedan a más de
   14 bits.

Las imágenes no se tocan aquí: este módulo solo traduce anotaciones. Leer, copiar y correr
el detector es trabajo de `scripts/preparar_dataset.py`.
"""

from __future__ import annotations

import hashlib
import random
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from gepp_core import Caja, ClaseDetectada, Deteccion
from scipy.optimize import linear_sum_assignment

from gepp_vision.dataset import UMBRAL_DUPLICADO, Particion

#: Las clases de la v1 y su `category_id` en el COCO de salida (#26).
CLASES_V1: dict[ClaseDetectada, int] = {
    ClaseDetectada.PERSONA: 1,
    ClaseDetectada.CASCO: 2,
    ClaseDetectada.CHALECO: 3,
}

#: Una propuesta del detector que se solapa así con una caja existente ya está etiquetada.
UMBRAL_IOU_EXISTENTE = 0.5


class CategoriaDesconocida(ValueError):
    pass


@dataclass(frozen=True)
class Fuente:
    """Un dataset de origen, tal como lo declara `scripts/fuentes.yaml`."""

    nombre: str
    licencia: str
    #: Categoría de origen -> clase propia. `None` = se descarta a propósito.
    clases: dict[str, ClaseDetectada | None]
    #: Clases que la fuente marca en TODAS sus imágenes. Las demás se completan.
    exhaustivas: frozenset[ClaseDetectada]
    origen: dict[str, Any] = field(default_factory=dict)
    #: Expresiones regulares cuyo primer grupo de captura identifica el video de origen.
    grupos: tuple[str, ...] = ()

    def traducir(self, nombres: Iterable[str]) -> dict[str, ClaseDetectada | None]:
        nombres = set(nombres)
        faltan = sorted(nombres - self.clases.keys())
        if faltan:
            raise CategoriaDesconocida(
                f"{self.nombre}: categorías sin declarar en fuentes.yaml: {faltan}. "
                "Tradúcelas a una clase propia o decláralas como null para descartarlas."
            )
        return {n: self.clases[n] for n in nombres}


def cargar_fuentes(ruta: Path) -> list[Fuente]:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    fuentes = []
    for f in datos["fuentes"]:
        try:
            clases = {
                str(k): ClaseDetectada(v) if v is not None else None for k, v in f["clases"].items()
            }
            exhaustivas = frozenset(ClaseDetectada(c) for c in f["exhaustivas"])
        except ValueError as e:
            raise ValueError(f"{f['nombre']}: {e}") from e
        fuera = {c for c in clases.values() if c is not None} | exhaustivas
        if not fuera <= CLASES_V1.keys():
            raise ValueError(f"{f['nombre']}: clases fuera de la v1: {sorted(fuera)}")
        grupos = tuple(f.get("grupos", []))
        for patron in grupos:
            try:
                compilado = re.compile(patron)
            except re.error as e:
                raise ValueError(f"{f['nombre']}: patrón de grupo inválido {patron!r}: {e}") from e
            if compilado.groups < 1:
                raise ValueError(f"{f['nombre']}: el patrón {patron!r} no tiene grupo de captura")
        fuentes.append(Fuente(f["nombre"], f["licencia"], clases, exhaustivas, f["origen"], grupos))
    return fuentes


@dataclass
class Anotada:
    """Una imagen de origen con sus cajas ya traducidas a clases propias."""

    archivo: str
    ancho: int
    alto: int
    cajas: list[tuple[ClaseDetectada, Caja]]


def _caja(x1: float, y1: float, x2: float, y2: float, ancho: int, alto: int) -> Caja | None:
    """Caja normalizada y recortada al cuadro; `None` si queda vacía."""
    x1, x2 = max(x1 / ancho, 0.0), min(x2 / ancho, 1.0)
    y1, y2 = max(y1 / alto, 0.0), min(y2 / alto, 1.0)
    return Caja(x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def desde_coco(coco: dict[str, Any], fuente: Fuente) -> list[Anotada]:
    nombre_de = {int(c["id"]): str(c["name"]) for c in coco["categories"]}
    # Solo cuentan las categorías con cajas: Roboflow exporta una categoría padre vacía.
    usadas = {int(a["category_id"]) for a in coco["annotations"]}
    traduccion = fuente.traducir(nombre_de[i] for i in usadas)

    imagenes = {
        int(i["id"]): Anotada(str(i["file_name"]), int(i["width"]), int(i["height"]), [])
        for i in coco["images"]
    }
    for a in coco["annotations"]:
        clase = traduccion[nombre_de[int(a["category_id"])]]
        img = imagenes[int(a["image_id"])]
        x, y, w, h = (float(v) for v in a["bbox"])
        caja = _caja(x, y, x + w, y + h, img.ancho, img.alto)
        if clase is not None and caja is not None:
            img.cajas.append((clase, caja))
    return list(imagenes.values())


def desde_voc(xml: str, fuente: Fuente) -> Anotada:
    raiz = ET.fromstring(xml)
    objetos = raiz.findall("object")
    traduccion = fuente.traducir(o.findtext("name", "").strip() for o in objetos)

    ancho = int(raiz.findtext("size/width", "0"))
    alto = int(raiz.findtext("size/height", "0"))
    img = Anotada(raiz.findtext("filename", "").strip(), ancho, alto, [])
    for o in objetos:
        clase = traduccion[o.findtext("name", "").strip()]
        x1, y1, x2, y2 = (
            float(o.findtext(f"bndbox/{k}", "0")) for k in ("xmin", "ymin", "xmax", "ymax")
        )
        caja = _caja(x1, y1, x2, y2, ancho, alto)
        if clase is not None and caja is not None:
            img.cajas.append((clase, caja))
    return img


def grupo(nombre: str, fuente: Fuente) -> str | None:
    """El video del que salió la imagen, si su nombre lo dice; si no, `None`."""
    for patron in fuente.grupos:
        if m := re.search(patron, nombre):
            return m.group(1).lower()
    return None


def completar(
    existentes: Sequence[Caja], propuestas: Sequence[Caja], umbral: float = UMBRAL_IOU_EXISTENTE
) -> list[Caja]:
    """Las propuestas que no se solapan (IoU < `umbral`) con ninguna caja existente."""
    return [p for p in propuestas if all(p.iou(e) < umbral for e in existentes)]


#: Cuál cede cuando dos particiones comparten escena: la de menor rango pierde la imagen.
_RANGO = {Particion.ENTRENAMIENTO: 0, Particion.VALIDACION: 1, Particion.PRUEBA: 2}


def quitar_fugas(
    hashes: Sequence[int], particiones: Sequence[Particion], umbral: int = UMBRAL_DUPLICADO
) -> set[int]:
    """Índices a descartar para que ninguna escena quede en dos particiones.

    La prueba se conserva entera; si una imagen de entrenamiento se parece a una de
    validación o prueba, sale la de entrenamiento. Vectorizado: son miles de imágenes.
    """
    h = np.array(hashes, dtype=np.uint64)
    rango = np.array([_RANGO[p] for p in particiones])
    descartar: set[int] = set()
    for i in range(len(h)):
        superiores = rango > rango[i]
        if superiores.any():
            distancias = np.bitwise_count(h[superiores] ^ h[i])
            if (distancias <= umbral).any():
                descartar.add(i)
    return descartar


def particion_estable(nombre: str) -> Particion:
    """80/10/10 por hash del nombre: misma imagen, misma partición, en cualquier corrida.

    Solo para fuentes que no traen su propia partición.
    """
    cubeta = int(hashlib.sha256(nombre.encode()).hexdigest()[:8], 16) % 10
    if cubeta == 0:
        return Particion.PRUEBA
    if cubeta == 1:
        return Particion.VALIDACION
    return Particion.ENTRENAMIENTO


def a_coco(imagenes: Iterable[tuple[Anotada, str, Sequence[Caja]]]) -> dict[str, Any]:
    """COCO de salida. Cada tupla: (imagen, nombre de archivo nuevo, personas automáticas)."""
    salida: dict[str, Any] = {
        "categories": [{"id": i, "name": str(c)} for c, i in CLASES_V1.items()],
        "images": [],
        "annotations": [],
    }
    for img_id, (img, archivo, automaticas) in enumerate(imagenes, start=1):
        salida["images"].append(
            {"id": img_id, "file_name": archivo, "width": img.ancho, "height": img.alto}
        )
        cajas = [(c, k, False) for c, k in img.cajas]
        cajas += [(ClaseDetectada.PERSONA, k, True) for k in automaticas]
        for clase, caja, automatica in cajas:
            w, h = caja.ancho * img.ancho, caja.alto * img.alto
            salida["annotations"].append(
                {
                    "id": len(salida["annotations"]) + 1,
                    "image_id": img_id,
                    "category_id": CLASES_V1[clase],
                    "bbox": [caja.x1 * img.ancho, caja.y1 * img.alto, w, h],
                    "area": w * h,
                    "iscrowd": 0,
                    "automatica": automatica,
                }
            )
    return salida


# --- verificación del modelo exportado -------------------------------------------------


def _asignar(iou: np.ndarray, umbral: float) -> list[tuple[int, int]]:
    """Emparejamiento óptimo (húngaro) de filas y columnas con IoU >= `umbral`."""
    if iou.size == 0:
        return []
    filas, columnas = linear_sum_assignment(-iou)
    return [(int(f), int(c)) for f, c in zip(filas, columnas, strict=True) if iou[f, c] >= umbral]


def emparejar(
    a: Sequence[Deteccion], b: Sequence[Deteccion], umbral_iou: float = 0.9
) -> list[tuple[Deteccion, Deteccion]]:
    """Pares de detecciones de la misma clase que son la misma caja (ONNX contra PyTorch)."""
    iou = np.array([[x.caja.iou(y.caja) if x.clase is y.clase else 0.0 for y in b] for x in a])
    return [(a[f], b[c]) for f, c in _asignar(iou, umbral_iou)]


def pares_con_verdad(
    predichas: Sequence[tuple[int, Caja]],
    verdad: Sequence[tuple[ClaseDetectada, Caja]],
    umbral_iou: float = 0.5,
) -> list[tuple[int, ClaseDetectada]]:
    """(id que devolvió el modelo, clase verdadera) de cada predicción que cae sobre una caja.

    Ignora la clase a propósito: sirve para averiguar qué significa cada id del modelo.
    """
    iou = np.array([[p.iou(v) for _, v in verdad] for _, p in predichas])
    return [(predichas[f][0], verdad[c][0]) for f, c in _asignar(iou, umbral_iou)]


def acuerdo_de_clases(
    pares: Sequence[tuple[int, ClaseDetectada]], mapa: dict[int, ClaseDetectada]
) -> float:
    """Fracción de pares en que el mapa traduce el id a la clase verdadera."""
    if not pares:
        raise ValueError("sin pares: el modelo no acertó ninguna caja, no hay acuerdo que medir")
    return sum(mapa.get(i) is clase for i, clase in pares) / len(pares)


def acierto_por_id(
    pares: Sequence[tuple[int, ClaseDetectada]], mapa: dict[int, ClaseDetectada]
) -> dict[int, tuple[int, int]]:
    """Por cada id del mapa: (aciertos, predicciones contrastadas con la verdad).

    El acuerdo global no basta: si la muestra es casi toda casco, un mapa con persona y
    chaleco intercambiados acierta el 100 %. Un id con 0 contrastes no está verificado.
    """
    return {
        i: (sum(1 for j, c in pares if j == i and c is clase), sum(1 for j, _ in pares if j == i))
        for i, clase in mapa.items()
    }


def muestra_estratificada[K](
    imagenes: Sequence[tuple[K, Sequence[ClaseDetectada]]],
    n: int,
    minimo_por_clase: int,
    semilla: int = 2026,
) -> list[K]:
    """`n` imágenes al azar (semilla fija), garantizando primero `minimo_por_clase` imágenes
    con cada clase presente. Las primeras `n` en orden saldrían todas de una sola fuente."""
    orden = list(range(len(imagenes)))
    random.Random(semilla).shuffle(orden)
    elegidas: list[int] = []
    for clase in CLASES_V1:
        con_clase = [i for i in orden if clase in imagenes[i][1] and i not in elegidas]
        ya = sum(1 for i in elegidas if clase in imagenes[i][1])
        elegidas += con_clase[: max(minimo_por_clase - ya, 0)]
    elegidas += [i for i in orden if i not in elegidas][: max(n - len(elegidas), 0)]
    return [imagenes[i][0] for i in elegidas]
