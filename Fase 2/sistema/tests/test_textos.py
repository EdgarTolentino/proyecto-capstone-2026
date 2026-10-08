"""`gepp_core.textos.sin_rutas`: el texto que sale del servidor no lleva rutas del disco."""

from __future__ import annotations

import pytest
from gepp_core.textos import sin_rutas

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


def test_una_ruta_despues_de_dos_puntos_tambien_se_sanea() -> None:
    assert sin_rutas("modelo:/srv/modelos/epp.onnx") == "modelo:epp.onnx"
    assert sin_rutas(f"video:{RUTA}", RUTA) == "video:clip.mp4"


@pytest.mark.parametrize(
    "url",
    [
        "http://host/a/b.mp4",
        "https://h:80/x/y",
        "http://localhost:8000/api/v1/videos",
        f"http://localhost:8000{RUTA}",
        "ver http://localhost:8000/datos/videos/entrada/clip.mp4 ahora",
    ],
)
def test_una_url_no_se_corrompe_ni_con_la_ruta_del_trabajo_dentro(url: str) -> None:
    assert sin_rutas(url, RUTA) == url
    assert sin_rutas(url) == url


def test_la_ruta_del_trabajo_solo_se_sustituye_si_esta_aparte() -> None:
    assert sin_rutas("/datos/a/clip.mp4 y /datos/ab/x.mp4", "/datos/a") == "a/clip.mp4 y x.mp4"
    assert sin_rutas("x/datos/videos/entrada/clip.mp4", RUTA) == "x/datos/videos/entrada/clip.mp4"
    assert sin_rutas(f"({RUTA})", RUTA) == "(clip.mp4)"
    assert sin_rutas(f"'{RUTA}'", RUTA) == "'clip.mp4'"


def test_un_nombre_con_barra_invertida_no_se_toma_por_una_referencia() -> None:
    ruta = "/datos/a\\1b.mp4"
    assert sin_rutas(f"falló {ruta}", ruta) == "falló a\\1b.mp4"


def test_un_nombre_con_espacios_se_conserva_entero() -> None:
    ruta = "/datos/mis videos/clip uno.mp4"
    assert sin_rutas(f"no existe el video: {ruta}", ruta) == "no existe el video: clip uno.mp4"


def test_cada_variante_de_la_ruta_se_sustituye_aunque_lleve_espacios() -> None:
    pedida = "/datos/enlace/clip.mp4"
    resuelta = "/datos/carpeta real/clip.mp4"  # con espacio: la regla general no la cubriría
    motivo = f"no existe el video: {resuelta} (pedido como {pedida})"
    esperado = "no existe el video: clip.mp4 (pedido como clip.mp4)"
    assert sin_rutas(motivo, pedida, resuelta) == esperado
    assert sin_rutas(motivo, resuelta, pedida) == esperado  # el orden de los argumentos no importa


def test_una_ruta_que_contiene_a_otra_se_sustituye_primero_la_mas_larga() -> None:
    larga, corta = "/datos/a b/clip.mp4", "/datos/a b"
    assert sin_rutas(f"falló {larga}", corta, larga) == "falló clip.mp4"


def test_una_ruta_vacia_se_ignora() -> None:
    assert sin_rutas("moov atom not found", "") == "moov atom not found"


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
