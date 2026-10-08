"""Revisión automática de una exportación «CVAT for images 1.1» (annotations.xml).

Aplica a las etiquetas ya hechas las reglas de `docs/datos/guia-etiquetado.md` (§4, §5 y §6) que
una máquina puede comprobar. Reporta; **no corrige ni borra nada**: decide quien etiqueta.

Por qué CVAT XML y no COCO: la exportación COCO 1.0 de CVAT pierde las etiquetas de imagen
(trae la categoría `tiene_pequenos` sin ninguna anotación). El XML sí las trae.

Cuatro comprobaciones, todas sobre un mismo cuadro:

1. `PAR_REPETIDO`: dos cajas de la misma clase con IoU >= `umbral_iou`.
2. `CAJA_MINIMA`: una caja con `bajo_minimo(ancho, alto, clase)` (el criterio de `a_coco`:
   10 px, y 8 px para el casco).
3. `FALTA_TIENE_PEQUENOS`: un cuadro con **alguna** caja bajo el mínimo (de cualquier clase) y sin
   la etiqueta de imagen `tiene_pequenos` (§4.2 de la guía). El hallazgo trae la caja chica.
4. `SIN_PERSONA`: un casco o chaleco **puesto** (`puesto = si`) que ninguna persona del cuadro
   contiene. El que está en el suelo, en un perchero o en la mano (`puesto = no`) es un negativo
   útil y no se asocia a nadie (§5 de la guía): no es hallazgo. Contiene =
   el **centro** de la caja cae dentro de la caja de la persona, ampliada hacia arriba en
   `margen_cabeza` por su alto (el casco sobresale de la cabeza, y la caja de la persona suele
   empezar en ella). Borde inclusivo. No se amplía hacia los lados ni hacia abajo.

Solo se lee «CVAT for images 1.1»: la exportación «for video» (`<track>`) es un error, y una
exportación sin ningún `<image>` también. Nada de esto lee imágenes: solo cuadro, clase y
coordenadas.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from gepp_vision.etiquetado import bajo_minimo

CLASES_CAJA = frozenset({"persona", "casco", "chaleco"})
#: Etiquetas de imagen de la guía (§5). Cualquier otra es un error de la exportación.
ETIQUETAS_IMAGEN = frozenset({"tiene_pequenos", "negativo_duro", "grupo_denso"})
TIENE_PEQUENOS = "tiene_pequenos"

UMBRAL_IOU = 0.8
MARGEN_CABEZA = 0.15


class ErrorExportacion(ValueError):
    """El XML no es una exportación válida (mal formado, caja invertida, etiqueta desconocida)."""


class Regla(StrEnum):
    PAR_REPETIDO = "par_repetido"
    CAJA_MINIMA = "caja_minima"
    FALTA_TIENE_PEQUENOS = "falta_tiene_pequenos"
    SIN_PERSONA = "sin_persona"


@dataclass(frozen=True)
class CajaEtiquetada:
    clase: str
    x1: float
    y1: float
    x2: float
    y2: float
    #: `si` o `no` en casco y chaleco (guía §3); None en persona.
    puesto: str | None = None

    @property
    def ancho(self) -> float:
        return self.x2 - self.x1

    @property
    def alto(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.ancho * self.alto

    @property
    def centro(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)


@dataclass(frozen=True)
class Cuadro:
    id: int
    nombre: str
    cajas: tuple[CajaEtiquetada, ...]
    etiquetas: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Hallazgo:
    regla: Regla
    cuadro: int
    nombre: str
    clase: str
    #: Una caja o, en un par repetido, las dos.
    cajas: tuple[CajaEtiquetada, ...]
    #: IoU del par (solo `PAR_REPETIDO`).
    iou: float | None = None


def _numero(el: ET.Element, atributo: str) -> float:
    try:
        valor = float(el.attrib[atributo])
    except (KeyError, ValueError) as e:
        raise ErrorExportacion(f"<{el.tag}> sin «{atributo}» numérico: {el.attrib}") from e
    if not math.isfinite(valor):  # float() acepta «nan» e «inf»
        raise ErrorExportacion(f"<{el.tag}> con «{atributo}» no finito: {el.attrib}")
    return valor


def _entero(el: ET.Element, atributo: str) -> int:
    try:
        return int(el.attrib[atributo])
    except (KeyError, ValueError) as e:
        raise ErrorExportacion(f"<{el.tag}> sin «{atributo}» entero: {el.attrib}") from e


def _puesto(caja: ET.Element, cuadro: int, clase: str) -> str | None:
    """El atributo `puesto` de un casco o chaleco: `si` o `no`. Falta o vale otra cosa: error,
    porque sin él no se sabe si el objeto debe tener una persona."""
    if clase == "persona":
        return None
    for atributo in caja.findall("attribute"):
        if atributo.attrib.get("name") == "puesto":
            valor = (atributo.text or "").strip()
            if valor not in ("si", "no"):
                raise ErrorExportacion(f"cuadro {cuadro}: «{clase}» con puesto «{valor}»")
            return valor
    raise ErrorExportacion(f"cuadro {cuadro}: «{clase}» sin el atributo puesto")


def leer_cvat_xml(texto: str) -> list[Cuadro]:
    """Cuadros de un annotations.xml «CVAT for images 1.1». Solo lee `<box>` y `<tag>`; otras
    formas (polígonos, cuboides) no existen en este proyecto y se ignoran."""
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as e:
        raise ErrorExportacion(f"XML mal formado: {e}") from e
    if raiz.tag != "annotations":
        raise ErrorExportacion(f"la raíz es <{raiz.tag}>, no <annotations>")

    if raiz.find("track") is not None:
        raise ErrorExportacion(
            "la exportación trae <track>: es «CVAT for video». Exporta con el formato "
            "«CVAT for images 1.1»"
        )

    cuadros: list[Cuadro] = []
    for img in raiz.iter("image"):
        id_ = _entero(img, "id")
        nombre = img.attrib.get("name", "")
        cajas: list[CajaEtiquetada] = []
        for caja in img.findall("box"):
            clase = caja.attrib.get("label", "")
            if clase not in CLASES_CAJA:
                raise ErrorExportacion(f"cuadro {id_}: clase de caja desconocida «{clase}»")
            x1, y1 = _numero(caja, "xtl"), _numero(caja, "ytl")
            x2, y2 = _numero(caja, "xbr"), _numero(caja, "ybr")
            if x2 < x1 or y2 < y1:
                raise ErrorExportacion(
                    f"cuadro {id_}: caja «{clase}» invertida ({x1},{y1})-({x2},{y2})"
                )
            cajas.append(CajaEtiquetada(clase, x1, y1, x2, y2, _puesto(caja, id_, clase)))
        etiquetas: set[str] = set()
        for tag in img.findall("tag"):
            etiqueta = tag.attrib.get("label", "")
            if etiqueta not in ETIQUETAS_IMAGEN:
                raise ErrorExportacion(f"cuadro {id_}: etiqueta de imagen desconocida «{etiqueta}»")
            etiquetas.add(etiqueta)
        cuadros.append(Cuadro(id_, nombre, tuple(cajas), frozenset(etiquetas)))
    if not cuadros:
        raise ErrorExportacion("la exportación no trae ningún <image>")
    return cuadros


def leer_cvat_xml_archivo(ruta: Path) -> list[Cuadro]:
    return leer_cvat_xml(ruta.read_text(encoding="utf-8"))


def iou(a: CajaEtiquetada, b: CajaEtiquetada) -> float:
    """Intersección sobre unión; 0 si no se solapan con área (incluye cajas sin área)."""
    ancho = min(a.x2, b.x2) - max(a.x1, b.x1)
    alto = min(a.y2, b.y2) - max(a.y1, b.y1)
    if ancho <= 0 or alto <= 0:
        return 0.0
    inter = ancho * alto
    return inter / (a.area + b.area - inter)


def contiene_persona(
    persona: CajaEtiquetada, objeto: CajaEtiquetada, margen_cabeza: float = MARGEN_CABEZA
) -> bool:
    """El centro de `objeto` cae en la caja de `persona` ampliada hacia arriba en
    `margen_cabeza` por su alto. Borde inclusivo."""
    cx, cy = objeto.centro
    tope = persona.y1 - margen_cabeza * persona.alto
    return persona.x1 <= cx <= persona.x2 and tope <= cy <= persona.y2


def _bajo_minimo(c: CajaEtiquetada) -> bool:
    return bajo_minimo(c.ancho, c.alto, c.clase)


def revisar(
    cuadros: Iterable[Cuadro],
    umbral_iou: float = UMBRAL_IOU,
    margen_cabeza: float = MARGEN_CABEZA,
) -> list[Hallazgo]:
    """Los hallazgos de todos los cuadros, en orden de cuadro y de regla."""
    if not 0 < umbral_iou <= 1:  # también rechaza NaN: la comparación encadenada da falso
        raise ValueError(f"umbral_iou debe estar en (0, 1], vino {umbral_iou}")
    if not (math.isfinite(margen_cabeza) and margen_cabeza >= 0):
        raise ValueError(f"margen_cabeza debe ser un número finito >= 0, vino {margen_cabeza}")

    hallazgos: list[Hallazgo] = []
    for cuadro in cuadros:
        base = (cuadro.id, cuadro.nombre)
        cajas = cuadro.cajas
        for i, a in enumerate(cajas):
            for b in cajas[i + 1 :]:
                if a.clase == b.clase and (valor := iou(a, b)) >= umbral_iou:
                    hallazgos.append(Hallazgo(Regla.PAR_REPETIDO, *base, a.clase, (a, b), valor))
        for c in cajas:
            if _bajo_minimo(c):
                hallazgos.append(Hallazgo(Regla.CAJA_MINIMA, *base, c.clase, (c,)))
        if TIENE_PEQUENOS not in cuadro.etiquetas:
            for c in cajas:
                if _bajo_minimo(c):
                    hallazgos.append(Hallazgo(Regla.FALTA_TIENE_PEQUENOS, *base, c.clase, (c,)))
        personas = [c for c in cajas if c.clase == "persona"]
        for c in cajas:
            if (
                c.clase in ("casco", "chaleco")
                and c.puesto == "si"
                and not any(contiene_persona(p, c, margen_cabeza) for p in personas)
            ):
                hallazgos.append(Hallazgo(Regla.SIN_PERSONA, *base, c.clase, (c,)))
    return hallazgos


def resumen(hallazgos: Iterable[Hallazgo]) -> dict[str, dict[str, int]]:
    """Por regla: cuántos hallazgos y en cuántos cuadros distintos."""
    hallazgos = list(hallazgos)
    salida: dict[str, dict[str, int]] = {}
    for r in Regla:
        de_la_regla = [h for h in hallazgos if h.regla is r]
        salida[r.value] = {
            "hallazgos": len(de_la_regla),
            "cuadros": len({h.cuadro for h in de_la_regla}),
        }
    return salida
