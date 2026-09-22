"""Evidencia de un hallazgo: recorte anonimizado escrito en disco (ADR-006).

El recorte llega a disco YA anonimizado: no existe una versión con el rostro visible, ni
siquiera temporal. El cuadro original nunca se escribe; solo el recorte.

**Privacidad por defecto, sin detector de rostros.** La v1 no tiene detector facial, así que
se pixela la franja superior de la caja de CADA persona del cuadro (la cabeza, donde va el
casco). Pixelar de más es el error barato: el recorte sigue mostrando si hay casco, que es lo
que importa. Un detector facial que acote la zona queda para después; entraría aquí sin
cambiar la firma.

`purgar_el` se calcula desde la fecha de CAPTURA más `retencion_dias` de la regla, no desde la
fecha en que se procesa: un video procesado con una semana de atraso no puede ganar una
semana de retención (anillo 1, `01-modelo-de-datos.md`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
from gepp_core import Caja

from gepp_vision.privacidad import difuminar_regiones

#: Fracción superior de la caja de la persona que se pixela. La cabeza de una persona de
#: pie ocupa ~1/8 de su alto; 0,22 cubre la cabeza con casco y algo de margen.
FRACCION_CABEZA = 0.22
#: Margen alrededor de la persona en el recorte, en fracción de su caja.
MARGEN_RECORTE = 0.25
CALIDAD_JPG = 90


@dataclass(frozen=True, slots=True)
class EvidenciaEscrita:
    """Lo que se persiste en la tabla `evidencia`."""

    ruta: Path
    hash_sha256: str
    cuadro_idx: int
    capture_ts: datetime
    purgar_el: date


def franja_de_cabeza(persona: Caja, fraccion: float = FRACCION_CABEZA) -> Caja:
    """La parte superior de la caja de una persona."""
    if not 0 < fraccion <= 1:
        raise ValueError("la fracción de cabeza debe estar en (0, 1]")
    return Caja(persona.x1, persona.y1, persona.x2, persona.y1 + persona.alto * fraccion)


def anonimizar(imagen: np.ndarray, personas: Sequence[Caja]) -> np.ndarray:
    """Copia de la imagen con la cabeza de cada persona pixelada."""
    return difuminar_regiones(imagen, [franja_de_cabeza(p) for p in personas], margen=0.0)


def recortar(imagen: np.ndarray, caja: Caja, margen: float = MARGEN_RECORTE) -> np.ndarray:
    alto, ancho = imagen.shape[:2]
    mx, my = caja.ancho * margen, caja.alto * margen
    x1 = max(0, int(np.floor((caja.x1 - mx) * ancho)))
    y1 = max(0, int(np.floor((caja.y1 - my) * alto)))
    x2 = min(ancho, int(np.ceil((caja.x2 + mx) * ancho)))
    y2 = min(alto, int(np.ceil((caja.y2 + my) * alto)))
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"el recorte de {caja} queda vacío")
    return imagen[y1:y2, x1:x2].copy()


def fecha_de_purga(capture_ts: datetime, retencion_dias: int) -> date:
    if capture_ts.tzinfo is None:
        raise ValueError("capture_ts debe llevar zona horaria (ver ADR-005)")
    if retencion_dias < 0:
        raise ValueError("retencion_dias no puede ser negativo")
    return capture_ts.date() + timedelta(days=retencion_dias)


def escribir_evidencia(
    imagen: np.ndarray,
    *,
    persona: Caja,
    personas_en_cuadro: Sequence[Caja],
    carpeta: Path,
    nombre: str,
    cuadro_idx: int,
    capture_ts: datetime,
    retencion_dias: int,
) -> EvidenciaEscrita:
    """Anonimiza el cuadro completo, recorta a la persona y escribe el JPG.

    Se anonimiza ANTES de recortar para que la cabeza de otra persona que caiga dentro del
    margen del recorte también salga pixelada.
    """
    purgar_el = fecha_de_purga(capture_ts, retencion_dias)
    recorte = recortar(anonimizar(imagen, [persona, *personas_en_cuadro]), persona)
    ok, codificado = cv2.imencode(".jpg", recorte, [cv2.IMWRITE_JPEG_QUALITY, CALIDAD_JPG])
    if not ok:
        raise RuntimeError("OpenCV no pudo codificar el recorte")
    datos = codificado.tobytes()
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{nombre}.jpg"
    ruta.write_bytes(datos)
    return EvidenciaEscrita(
        ruta=ruta,
        hash_sha256=hashlib.sha256(datos).hexdigest(),
        cuadro_idx=cuadro_idx,
        capture_ts=capture_ts,
        purgar_el=purgar_el,
    )
