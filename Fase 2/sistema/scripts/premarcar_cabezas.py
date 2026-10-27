"""Premarca cabezas para que una persona las corrija en CVAT (ADR-013).

    uv run python scripts/premarcar_cabezas.py PRED.coco.json MODELO.clases.json SALIDA.coco.json

`predicciones` sale de `preetiquetar.py --umbral 0.05 --con-evidencia` (clases v3, con `score`).
El modelo ve bien `persona` y `casco` en cámaras de obra y casi no ve `cabeza`; por eso toda
persona sin casco asociado (la definición de la regla, `cabeza.personas_sin_casco`) sugiere una
cabeza arriba de su caja. Salen persona, casco, chaleco y sin_chaleco sobre `--umbral` (0,45, el
de la regla) y las cabezas. Cada `cabeza` lleva `origen`: `sugerida` (la geometría de abajo, hay
que ajustarla) o `predicha` (la del modelo, también a revisar), en `attributes` y como campo.

Geometría de la sugerida, medida sobre las 3 567 cabezas de `epp-v3/train` que caen en la franja
de una persona: alto = 0,18 del alto de la persona (mediana de alto_cabeza / alto_persona 0,179),
ancho = 0,444 del ancho de la persona (mediana 0,444), centrada en x (mediana del desfase -0,010
del ancho) y pegada al borde superior (mediana del borde de la cabeza -0,009 del alto). IoU
mediano contra la cabeza real: 0,453; solo el 43,5 % llega a 0,5. Es un punto de partida para
arrastrar, no una caja lista.

Una `cabeza` predicha sobre el umbral gana a la sugerida: su dueña (`persona_dueña`, la más
cercana de las personas cuya franja la contiene) la reclama si no tiene casco y no estaba
reclamada, y una segunda predicha de la misma dueña se descarta como duplicada. Las predichas de
una persona con casco o sin persona se conservan, marcadas, para que quien corrige decida.

Para no dejar en CVAT dos cajas casi iguales, la sugerida de una persona sin casco tampoco se
escribe si su IoU con alguna predicha ya escrita en la imagen es >= `IOU_REPETIDA` (0,5, el
umbral habitual de «misma caja»). Una predicha que solo cae en la franja de otra persona, sin
solaparse con su sugerida, no la borra. Borrar es más fácil que dibujar.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gepp_core import ClaseDetectada
from gepp_core.dominio import CONFIANZA_MINIMA_REGLA
from gepp_vision.detectores.rfdetr_comun import MapaDeClases
from gepp_vision.entrenamiento import CLASES_V3
from gepp_vision.evaluacion.cabeza import (
    CLASE_CABEZA,
    persona_dueña,
    personas_sin_casco,
)
from gepp_vision.evaluacion.coco import ArchivoCoco, CajaPx, EntradaInvalida, leer_coco

#: Medianas de epp-v3/train (docstring). Sobre el alto de la persona y sobre su ancho.
ALTO_CABEZA = 0.18
ANCHO_CABEZA = 0.444
#: IoU desde el cual una sugerida y una predicha son «la misma caja» y solo sale la predicha.
IOU_REPETIDA = 0.5
_PASAN = ("persona", "casco", "chaleco", "sin_chaleco")


def cabeza_sugerida(persona: CajaPx, ancho: int, alto: int) -> CajaPx | None:
    """La cabeza que se espera en `persona`, intersectada con la imagen; None si cae fuera."""
    w, h = ANCHO_CABEZA * persona.ancho, ALTO_CABEZA * persona.alto
    x1 = persona.x + (persona.ancho - w) / 2
    x2, y2 = min(float(ancho), x1 + w), min(float(alto), persona.y + h)
    x1, y1 = max(0.0, x1), max(0.0, persona.y)
    if x2 <= x1 or y2 <= y1:
        return None
    return CajaPx(persona.archivo, CLASE_CABEZA, x1, y1, x2 - x1, y2 - y1, None)


def repite_predicha(sugerida: CajaPx, predichas: Sequence[CajaPx]) -> bool:
    """¿Alguna predicha es la misma caja que la sugerida (IoU >= `IOU_REPETIDA`)?"""
    return any(sugerida.iou(c) >= IOU_REPETIDA for c in predichas)


def premarcar(
    datos: ArchivoCoco, umbral: float
) -> list[tuple[str, tuple[int, int], list[tuple[CajaPx, str]]]]:
    """Por imagen (archivo, tamaño), las cajas a escribir con su origen (`predicha`/`sugerida`)."""
    if not 0 < umbral <= 1:
        raise ValueError(f"umbral fuera de (0, 1]: {umbral}")
    malos = [c.score for c in datos.cajas + datos.evidencia if not 0 <= (c.score or 0.0) <= 1]
    if malos:
        raise EntradaInvalida(f"score fuera de [0, 1] o no finito: {malos[:3]}")
    if not {"persona", "casco"} <= datos.categorias:
        raise EntradaInvalida(
            f"el COCO no declara persona y casco (trae {sorted(datos.categorias)}): "
            "¿es la salida de preetiquetar.py --con-evidencia?"
        )
    sobre = [c for c in datos.cajas + datos.evidencia if (c.score or 0.0) >= umbral]
    salida = []
    for archivo, (ancho, alto) in datos.imagenes.items():
        de = [c for c in sobre if c.archivo == archivo]
        personas = [c for c in de if c.clase == "persona"]
        cascos = [c for c in de if c.clase == "casco"]
        cajas = [(c, "predicha") for c in de if c.clase in _PASAN]
        sin = personas_sin_casco(personas, cascos, ancho, alto)
        reclamada = [False] * len(personas)
        predichas = sorted(
            (c for c in de if c.clase == CLASE_CABEZA), key=lambda c: -(c.score or 0.0)
        )
        escritas: list[CajaPx] = []
        for cabeza in predichas:
            i = persona_dueña(personas, *cabeza.centro, ancho, alto)
            if i is None or not sin[i]:  # sin persona o con casco: se conserva, marcada
                cajas.append((cabeza, "predicha"))
                escritas.append(cabeza)
            elif not reclamada[i]:  # la del modelo reemplaza a la sugerida de esa persona
                reclamada[i] = True
                cajas.append((cabeza, "predicha"))
                escritas.append(cabeza)
            # si no, duplicada de otra predicha de la misma persona: se descarta
        for p, s, r in zip(personas, sin, reclamada, strict=True):
            sugerida = cabeza_sugerida(p, ancho, alto) if s and not r else None
            if sugerida is not None and not repite_predicha(sugerida, escritas):
                cajas.append((sugerida, "sugerida"))
        salida.append((archivo, (ancho, alto), cajas))
    return salida


def a_coco(
    imagenes: Sequence[tuple[str, tuple[int, int], list[tuple[CajaPx, str]]]], modelo: str
) -> dict[str, Any]:
    """COCO 1.0 con ids de la v3. `origen` va como campo y en `attributes` (lo que CVAT lee)."""
    coco: dict[str, Any] = {
        "info": {"description": f"premarcado de cabezas sobre {modelo}"},
        "categories": [
            {"id": i, "name": str(c), "supercategory": ""} for c, i in CLASES_V3.items()
        ],
        "images": [],
        "annotations": [],
    }
    for img_id, (archivo, (ancho, alto), cajas) in enumerate(imagenes, start=1):
        coco["images"].append({"id": img_id, "file_name": archivo, "width": ancho, "height": alto})
        for caja, origen in cajas:
            nota: dict[str, Any] = {
                "id": len(coco["annotations"]) + 1,
                "image_id": img_id,
                "category_id": CLASES_V3[ClaseDetectada(caja.clase)],
                "bbox": [caja.x, caja.y, caja.ancho, caja.alto],
                "area": caja.area,
                "iscrowd": 0,
                "origen": origen,
                "attributes": {"origen": origen},
            }
            if caja.score is not None:
                nota["score"] = caja.score
            coco["annotations"].append(nota)
    return coco


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("predicciones", type=Path)
    p.add_argument("clases", type=Path, help="el .clases.json del modelo")
    p.add_argument("salida", type=Path)
    p.add_argument("--umbral", type=float, default=CONFIANZA_MINIMA_REGLA)
    args = p.parse_args(argv)
    try:
        mapa = MapaDeClases.desde_json(args.clases)
        faltan = {ClaseDetectada.PERSONA, ClaseDetectada.CASCO} - set(mapa.clases.values())
        if faltan:
            raise EntradaInvalida(f"el modelo {mapa.version} no tiene {sorted(map(str, faltan))}")
        datos = leer_coco(
            json.loads(args.predicciones.read_text(encoding="utf-8")), predicciones=True
        )
        coco = a_coco(premarcar(datos, args.umbral), mapa.version)
    except (ValueError, KeyError, OSError) as e:  # EntradaInvalida es ValueError
        sys.exit(f"error: {e}")
    args.salida.write_text(json.dumps(coco, ensure_ascii=False, indent=2), encoding="utf-8")
    sugeridas = sum(1 for n in coco["annotations"] if n["origen"] == "sugerida")
    print(f"{len(coco['annotations'])} cajas, {sugeridas} cabezas sugeridas -> {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
