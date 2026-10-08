"""El motivo de un fallo no lleva rutas del servidor (`GET /videos` lo devuelve tal cual)."""

from __future__ import annotations

from pathlib import Path

import pytest
from gepp_worker.trabajador import sin_rutas

RUTA = "/datos/videos/entrada/clip.mp4"


ERRNO = "FileNotFoundError: [Errno 2] No such file or directory: "
CASOS = [
    (f"no existe el video: {RUTA}", "no existe el video: clip.mp4"),
    (f"OpenCV no pudo abrir el video: {RUTA}", "OpenCV no pudo abrir el video: clip.mp4"),
    (f"sin fps válidos (0.0): {RUTA}", "sin fps válidos (0.0): clip.mp4"),
    (f"{ERRNO}'{RUTA}'", f"{ERRNO}'clip.mp4'"),
    (f"No se pudo leer el video: {RUTA}.", "No se pudo leer el video: clip.mp4."),
    ("ffprobe falló en /otra/carpeta/otro.mp4 (código 1)", "ffprobe falló en otro.mp4 (código 1)"),
    (f"{RUTA} y también /var/tmp/x/y.mov", "clip.mp4 y también y.mov"),
]


@pytest.mark.parametrize(("motivo", "esperado"), CASOS)
def test_la_ruta_del_trabajo_queda_en_su_nombre(motivo: str, esperado: str) -> None:
    assert sin_rutas(motivo, RUTA) == esperado


def test_un_nombre_con_espacios_se_conserva_entero() -> None:
    ruta = "/datos/mis videos/clip uno.mp4"
    assert sin_rutas(f"no existe el video: {ruta}", ruta) == "no existe el video: clip uno.mp4"


def test_la_ruta_resuelta_de_un_enlace_tambien_se_sustituye(tmp_path: Path) -> None:
    real = tmp_path / "carpeta real"  # con espacio: la regla general no la cubriría entera
    real.mkdir()
    enlace = tmp_path / "enlace"
    enlace.symlink_to(real)
    ruta = enlace / "clip.mp4"
    motivo = f"no existe el video: {real / 'clip.mp4'} (pedido como {ruta})"
    assert sin_rutas(motivo, str(ruta)) == "no existe el video: clip.mp4 (pedido como clip.mp4)"


@pytest.mark.parametrize(
    "motivo",
    [
        "",
        "moov atom not found",
        "LookupError: el área 1 no tiene reglas activas",
        "3/4 de los cuadros",
        "http://localhost:8000/api/v1/videos",
        "ruta relativa clip.mp4",
        "disco lleno",
    ],
)
def test_lo_que_no_es_una_ruta_absoluta_no_se_toca(motivo: str) -> None:
    assert sin_rutas(motivo, RUTA) == motivo
    assert sin_rutas(motivo) == motivo


def test_sin_ruta_del_trabajo_igual_se_quitan_las_absolutas() -> None:
    assert sin_rutas(f"falló {RUTA}") == "falló clip.mp4"


def test_sanear_dos_veces_da_lo_mismo() -> None:
    una = sin_rutas(f"no existe el video: {RUTA}", RUTA)
    assert sin_rutas(una, RUTA) == una
