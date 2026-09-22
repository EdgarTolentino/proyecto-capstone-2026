"""Evidencia anonimizada: cabeza pixelada, recorte, hash y fecha de purga (ADR-006)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest
from gepp_core import Caja
from gepp_vision.evidencia import (
    escribir_evidencia,
    fecha_de_purga,
    franja_de_cabeza,
    recortar,
)

PERSONA = Caja(0.25, 0.10, 0.75, 0.90)


def rugosidad(imagen: np.ndarray) -> float:
    """Diferencia media entre píxeles vecinos: alta en ruido, baja en bloques lisos."""
    gris = imagen.astype(np.float64).mean(axis=2)
    return float(np.abs(np.diff(gris, axis=1)).mean())


def _ruido(alto: int = 240, ancho: int = 320) -> np.ndarray:
    return np.random.default_rng(7).integers(0, 256, (alto, ancho, 3), dtype=np.uint8)


def test_la_franja_de_cabeza_es_la_parte_superior() -> None:
    f = franja_de_cabeza(PERSONA, 0.25)
    assert (f.x1, f.x2, f.y1) == (PERSONA.x1, PERSONA.x2, PERSONA.y1)
    assert f.alto == pytest.approx(PERSONA.alto * 0.25)


@pytest.mark.parametrize("fraccion", [0.0, 1.5])
def test_la_franja_fuera_de_rango_se_rechaza(fraccion: float) -> None:
    with pytest.raises(ValueError, match="fracción"):
        franja_de_cabeza(PERSONA, fraccion)


def test_el_recorte_se_ajusta_al_borde_del_cuadro() -> None:
    img = _ruido()
    borde = Caja(0.0, 0.0, 0.1, 0.1)
    assert recortar(img, borde, margen=1.0).shape[:2] == (48, 64)


@pytest.mark.parametrize(("dias", "esperado"), [(0, date(2026, 9, 24)), (30, date(2026, 10, 24))])
def test_la_purga_se_cuenta_desde_la_captura(dias: int, esperado: date) -> None:
    assert fecha_de_purga(datetime(2026, 9, 24, 23, 0, tzinfo=UTC), dias) == esperado


def test_la_purga_sin_zona_horaria_o_con_dias_negativos_se_rechaza() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        fecha_de_purga(datetime(2026, 9, 24), 30)  # noqa: DTZ001 — es lo que se prueba
    with pytest.raises(ValueError, match="negativo"):
        fecha_de_purga(datetime(2026, 9, 24, tzinfo=UTC), -1)


def test_la_evidencia_se_escribe_con_la_cabeza_pixelada(tmp_path: Path) -> None:
    img = _ruido()  # 320 x 240
    # Persona interior: el recorte con 25 % de margen no toca el borde del cuadro.
    persona = Caja(0.30, 0.25, 0.60, 0.75)
    capture = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
    ev = escribir_evidencia(
        img,
        persona=persona,
        personas_en_cuadro=[persona],
        carpeta=tmp_path,
        nombre="h1",
        cuadro_idx=12,
        capture_ts=capture,
        retencion_dias=30,
    )
    datos = ev.ruta.read_bytes()
    assert ev.hash_sha256 == hashlib.sha256(datos).hexdigest()
    assert ev.purgar_el == date(2026, 10, 24)
    assert list(tmp_path.iterdir()) == [ev.ruta]  # solo el recorte, nunca el cuadro

    import cv2

    recorte = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)
    # En el recorte la persona va de x 24 a 120 y de y 30 a 150; su cabeza (22 %) de 30 a 56.
    assert recorte.shape[:2] == (180, 144)
    cabeza = recorte[32:54, 26:118]
    cuerpo = recorte[90:140, 26:118]
    assert rugosidad(cabeza) < rugosidad(cuerpo) / 3
