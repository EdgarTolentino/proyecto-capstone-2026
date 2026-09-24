"""Evidencia de un hallazgo: recorte anonimizado escrito en disco (ADR-006).

El recorte llega a disco YA anonimizado: no existe una versión con el rostro visible, ni
siquiera temporal. El cuadro original nunca se escribe; solo el recorte.

**Se pixela la cara, no la cabeza.** La v1 no tiene detector facial, así que la zona de la cara
se estima desde la caja de CADA persona del cuadro: bajo la visera y centrada. La coronilla,
donde va el casco, queda VISIBLE: una evidencia que no deja ver si hay casco no sirve para
revisar el hallazgo (lo detectó Edgar en la demo del 22-sep: la primera versión pixelaba el
22 % superior de la caja, casco incluido).

Límite conocido: con una persona agachada, de espaldas o parcialmente fuera del cuadro la
estimación puede quedar corta. Un detector facial que acote la zona entraría aquí sin cambiar
la firma (PT-17).

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

#: Zona de la cara, en fracción de la caja de la persona. La cabeza de una persona de pie
#: ocupa ~1/8 de su alto: el casco va en el ~5 % superior y la cara, bajo la visera, hasta
#: ~15 %. A lo ancho, la caja incluye brazos y hombros: la cabeza va en el centro.
ROSTRO_VERTICAL = (0.05, 0.15)
ROSTRO_HORIZONTAL = (0.30, 0.70)
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


def zona_de_rostro(persona: Caja) -> Caja:
    """La zona de la cara dentro de la caja de una persona. Deja fuera la coronilla (casco)."""
    (y_desde, y_hasta), (x_desde, x_hasta) = ROSTRO_VERTICAL, ROSTRO_HORIZONTAL
    return Caja(
        persona.x1 + persona.ancho * x_desde,
        persona.y1 + persona.alto * y_desde,
        persona.x1 + persona.ancho * x_hasta,
        persona.y1 + persona.alto * y_hasta,
    )


def anonimizar(imagen: np.ndarray, personas: Sequence[Caja]) -> np.ndarray:
    """Copia de la imagen con la cara de cada persona pixelada y el casco a la vista."""
    return difuminar_regiones(imagen, [zona_de_rostro(p) for p in personas], margen=0.0)


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
