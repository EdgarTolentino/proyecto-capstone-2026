"""Privacidad sobre la imagen: máscaras antes de inferir, rostros pixelados (ADR-006)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from gepp_core import Caja
from gepp_vision import MascaraPrivacidad, aplicar_mascaras, difuminar_regiones
from gepp_worker import FuenteArchivo

from .conftest import T0
from .video_sintetico import cuadro_sintetico, escribir_video

MITAD_IZQUIERDA = [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]


def test_la_mascara_anula_los_pixeles_del_poligono() -> None:
    imagen = np.full((100, 200, 3), 200, dtype=np.uint8)
    salida = aplicar_mascaras(imagen, [MITAD_IZQUIERDA])
    assert (salida[:, :99] == 0).all()
    assert (salida[:, 102:] == 200).all()
    assert (imagen == 200).all(), "la imagen original no se modifica"


def test_sin_poligonos_la_imagen_queda_igual() -> None:
    imagen = cuadro_sintetico(3)
    assert np.array_equal(MascaraPrivacidad([]).aplicar(imagen), imagen)


@pytest.mark.parametrize(
    "poligono",
    [[(0.0, 0.0), (1.0, 1.0)], [(0.0, 0.0), (1.2, 0.0), (0.5, 0.5)]],
)
def test_poligonos_invalidos_se_rechazan(poligono: list[tuple[float, float]]) -> None:
    with pytest.raises(ValueError):
        MascaraPrivacidad([poligono])


def test_la_mascara_se_aplica_a_cada_cuadro_del_video(tmp_path: Path) -> None:
    ruta = escribir_video(tmp_path / "v.mp4", fps=25, segundos=1)
    mascara = MascaraPrivacidad([MITAD_IZQUIERDA])
    fuente = FuenteArchivo(ruta, inicio_captura=T0)
    fuente.abrir()
    vistos = 0
    while fuente.tomar():
        cuadro = fuente.recuperar()
        assert cuadro is not None
        salida = mascara.aplicar(cuadro.imagen)
        assert (salida[:, :79] == 0).all()
        assert salida[:, 81:].any()
        vistos += 1
    fuente.cerrar()
    assert vistos == 25


def test_el_rostro_queda_pixelado_y_el_resto_intacto() -> None:
    rng = np.random.default_rng(0)
    imagen = rng.integers(0, 256, size=(120, 160, 3), dtype=np.uint8)
    rostro = Caja(0.25, 0.25, 0.50, 0.50)
    salida = difuminar_regiones(imagen, [rostro], margen=0.0, bloques=4)

    region = salida[30:60, 40:80].astype(int)
    # Con 4 bloques por lado quedan como mucho 16 colores distintos donde había ~1200.
    assert len({tuple(p) for p in region.reshape(-1, 3)}) <= 16
    assert region.std() < imagen[30:60, 40:80].astype(int).std()
    fuera = np.ones(imagen.shape[:2], dtype=bool)
    fuera[30:60, 40:80] = False
    assert np.array_equal(salida[fuera], imagen[fuera])
    assert not np.array_equal(salida, imagen)


def test_el_margen_amplia_la_region_y_se_recorta_al_borde() -> None:
    imagen = np.random.default_rng(1).integers(0, 256, size=(100, 100, 3), dtype=np.uint8)
    esquina = Caja(0.9, 0.9, 1.0, 1.0)
    salida = difuminar_regiones(imagen, [esquina], margen=0.5, bloques=1)
    # La caja crece a 0,85..1,0 y se recorta en el borde sin fallar: un solo color.
    assert len({tuple(p) for p in salida[85:, 85:].reshape(-1, 3)}) == 1
    assert np.array_equal(salida[:85, :], imagen[:85, :])


def test_bloques_invalidos_se_rechazan() -> None:
    with pytest.raises(ValueError):
        difuminar_regiones(cuadro_sintetico(0), [Caja(0.1, 0.1, 0.2, 0.2)], bloques=0)
