"""Inventario de video: la rotación del celular cambia ancho y alto (Regla 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import scripts.inventario_video as inventario  # type: ignore[import-not-found]
from scripts.inventario_video import (  # type: ignore[import-not-found]
    Ficha,
    dimensiones_de_cuadro,
    rotacion_grados,
)


def _stream(**extra: Any) -> dict[str, Any]:
    return {"width": 1024, "height": 576, **extra}


def _matriz(rotation: Any) -> dict[str, Any]:
    """Forma real de ffprobe nuevo (celular-01.mp4): `Display Matrix` en side_data_list."""
    return {
        "tags": {},
        "side_data_list": [{"side_data_type": "Display Matrix", "rotation": rotation}],
    }


@pytest.mark.parametrize(
    ("extra", "esperado"),
    [
        ({}, (1024, 576)),  # sin rotación (ausente)
        (_matriz(0), (1024, 576)),
        (_matriz(90), (576, 1024)),
        (_matriz(-90), (576, 1024)),  # el caso real del celular en vertical
        (_matriz(180), (1024, 576)),
        (_matriz(-180), (1024, 576)),
        (_matriz(270), (576, 1024)),
        ({"tags": {"rotate": "90"}}, (576, 1024)),  # ffmpeg viejo
        ({"tags": {"rotate": "270"}}, (576, 1024)),
        ({"tags": {"rotate": "180"}}, (1024, 576)),
        ({"tags": {"rotate": "0"}}, (1024, 576)),
    ],
)
def test_dimensiones_segun_la_rotacion(extra: dict[str, Any], esperado: tuple[int, int]) -> None:
    assert dimensiones_de_cuadro(_stream(**extra)) == esperado


def test_la_orientacion_sale_de_las_dimensiones_rotadas() -> None:
    ancho, alto = dimensiones_de_cuadro(_stream(**_matriz(-90)))
    ficha = Ficha("v.mp4", ancho, alto, 30.0, 10.0, "h264", 1.0, None, None)
    assert ficha.orientacion == "VERTICAL"
    assert ficha.factor_reescalado == pytest.approx(560 / 1024)


def test_rotacion_se_normaliza_a_0_90_180_270() -> None:
    assert [rotacion_grados(_matriz(g)) for g in (-90, -180, -270, 360, 450)] == [
        270,
        180,
        90,
        0,
        90,
    ]


@pytest.mark.parametrize("basura", ["abc", "", [], {"x": 1}, 45, "30", "89.75", "90.25", "0.25"])
def test_una_rotacion_invalida_falla_en_vez_de_ignorarse(basura: Any) -> None:
    with pytest.raises(ValueError, match="rotación"):
        dimensiones_de_cuadro(_stream(**_matriz(basura)))
    with pytest.raises(ValueError, match="rotación"):
        dimensiones_de_cuadro(_stream(tags={"rotate": basura}))


def test_fichar_usa_las_dimensiones_rotadas(monkeypatch: pytest.MonkeyPatch) -> None:
    """La ficha entera, no solo la función: así salía el celular en vertical antes."""
    stream = {**_stream(**_matriz(-90)), "avg_frame_rate": "30/1", "codec_name": "h264"}
    formato = {"duration": "128.9", "size": "11650352"}
    monkeypatch.setattr(inventario, "ffprobe", lambda _: {"stream": stream, "format": formato})
    monkeypatch.setattr(inventario, "analizar_movimiento", lambda _: (79.0, 4.0))
    ficha = inventario.fichar(Path("celular-01.mp4"))
    assert (ficha.ancho, ficha.alto, ficha.orientacion) == (576, 1024, "VERTICAL")
