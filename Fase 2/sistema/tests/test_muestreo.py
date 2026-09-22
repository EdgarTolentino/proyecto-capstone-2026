"""Muestreo a 5 fps: invariante a la cadencia de origen y sin deriva."""

from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

import pytest
from gepp_worker import FuenteArchivo, FuenteDeCuadros, Muestreador
from gepp_worker.muestreo import fps_objetivo_configurado, pasa

from .conftest import T0
from .video_sintetico import escribir_video


def _indices(fps_origen: float, segundos: float, fps_objetivo: float = 5.0) -> list[int]:
    total = round(fps_origen * segundos)
    return [i for i in range(total) if pasa(i, fps_origen, fps_objetivo)]


@pytest.mark.parametrize("fps_origen", [24.0, 25.0, 30.0, 29.97, 60.0, 12.5])
def test_entrega_cinco_por_segundo_desde_cualquier_cadencia(fps_origen: float) -> None:
    for segundos in (1, 10, 600):
        assert len(_indices(fps_origen, segundos)) == 5 * segundos


@pytest.mark.parametrize("fps_origen", [24.0, 25.0, 30.0, 29.97])
def test_sin_deriva_en_una_hora(fps_origen: float) -> None:
    """Cada cuadro elegido cae en su tic: el error nunca supera un cuadro de origen."""
    for n, indice in enumerate(_indices(fps_origen, 3600)):
        instante = indice / fps_origen
        assert n / 5 <= instante + 1e-9
        assert instante - n / 5 < 1 / fps_origen


def test_con_origen_mas_lento_que_el_objetivo_pasan_todos() -> None:
    assert _indices(3.0, 4) == list(range(12))
    assert _indices(5.0, 2) == list(range(10))


def test_pasa_valida_sus_argumentos() -> None:
    with pytest.raises(ValueError):
        pasa(-1, 25, 5)
    with pytest.raises(ValueError):
        pasa(0, 0, 5)


@pytest.mark.parametrize("fps_origen", [24, 25, 30])
def test_sobre_video_real_el_reloj_es_el_de_origen(tmp_path: Path, fps_origen: int) -> None:
    ruta = escribir_video(tmp_path / f"v{fps_origen}.mp4", fps=fps_origen, segundos=2)
    muestreador = Muestreador(FuenteArchivo(ruta, inicio_captura=T0), fps_objetivo=5)
    assert isinstance(muestreador, FuenteDeCuadros)
    muestreador.abrir()
    cuadros = []
    while muestreador.tomar():
        cuadro = muestreador.recuperar()
        assert cuadro is not None
        cuadros.append(cuadro)
    assert muestreador.fps_efectivo == 5
    assert muestreador.propiedades().fps == fps_origen
    muestreador.cerrar()

    assert len(cuadros) == 10
    for n, c in enumerate(cuadros):
        assert c.capture_ts == T0 + timedelta(seconds=c.indice / fps_origen)
        assert c.indice == math.ceil(n * fps_origen / 5)


def test_fps_efectivo_no_supera_al_de_origen(tmp_path: Path) -> None:
    ruta = escribir_video(tmp_path / "lento.mp4", fps=3, segundos=2)
    muestreador = Muestreador(FuenteArchivo(ruta, inicio_captura=T0), fps_objetivo=5)
    muestreador.abrir()
    assert muestreador.fps_efectivo == 3
    muestreador.cerrar()


def test_objetivo_desde_el_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEPP_FPS_OBJETIVO", raising=False)
    assert fps_objetivo_configurado() == 5.0
    monkeypatch.setenv("GEPP_FPS_OBJETIVO", "10")
    assert fps_objetivo_configurado() == 10.0
    for malo in ("0", "-2", "nan"):
        monkeypatch.setenv("GEPP_FPS_OBJETIVO", malo)
        with pytest.raises(ValueError):
            fps_objetivo_configurado()
