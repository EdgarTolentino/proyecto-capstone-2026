"""Nombres de archivo en la carpeta de entrada: bordes, entradas inválidas y escapes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from gepp_core.archivos import (
    EXTENSIONES_VIDEO,
    MAXIMO_NOMBRE_BYTES,
    ArchivoNoEncontrado,
    NombreInvalido,
    validar_nombre,
    validar_nombre_en_carpeta,
)


@pytest.fixture
def carpeta(tmp_path: Path) -> Path:
    c = tmp_path / "entrada"
    c.mkdir()
    return c


def _crear(carpeta: Path, nombre: str, contenido: bytes = b"x") -> Path:
    ruta = carpeta / nombre
    ruta.write_bytes(contenido)
    return ruta


# ── Nombre mal formado (422): no necesita el disco ─────────────────────────────────────────

INVALIDOS = [
    "",
    "a/b.mp4",
    "../x.mp4",
    "/etc/passwd",
    "a\\b.mp4",
    "a\x00.mp4",
    ".oculto.mp4",
    "..mp4",
    "..",
    ".mp4",
    "x.txt",
    "x",
    "x.mp4.txt",
    "x.mp4 ",  # el espacio final cambia la extensión
    "\ud800.mp4",  # surrogate suelto: no es UTF-8
]


@pytest.mark.parametrize("nombre", INVALIDOS)
def test_un_nombre_mal_formado_es_invalido(nombre: str) -> None:
    with pytest.raises(NombreInvalido):
        validar_nombre(nombre)


@pytest.mark.parametrize("nombre", INVALIDOS)
def test_un_nombre_mal_formado_no_toca_el_disco(carpeta: Path, nombre: str) -> None:
    """Es 422 aunque la carpeta no exista: la forma se rechaza antes de mirar el disco."""
    with pytest.raises(NombreInvalido):
        validar_nombre_en_carpeta(carpeta / "no_existe", nombre)


@pytest.mark.parametrize("extension", sorted(EXTENSIONES_VIDEO))
def test_las_extensiones_validas_no_distinguen_mayusculas(extension: str) -> None:
    validar_nombre(f"video{extension}")
    validar_nombre(f"VIDEO{extension.upper()}")


def test_las_extensiones_son_las_del_vigilante() -> None:
    from gepp_worker.vigilante import EXTENSIONES_VIDEO as DEL_VIGILANTE

    assert DEL_VIGILANTE is EXTENSIONES_VIDEO
    assert {".mp4", ".mov", ".mkv", ".avi"} == EXTENSIONES_VIDEO


# ── El límite está en BYTES, no en caracteres (255 sí, 256 no) ─────────────────────────────


def test_255_bytes_es_valido_y_256_no() -> None:
    justo = "a" * (MAXIMO_NOMBRE_BYTES - 4) + ".mp4"
    assert len(justo.encode()) == 255
    validar_nombre(justo)
    with pytest.raises(NombreInvalido):
        validar_nombre("a" + justo)


def test_el_limite_cuenta_bytes_utf8_no_caracteres() -> None:
    # 'á' pesa 2 bytes: 125 tildes + '.mp4' = 254 bytes (129 caracteres) -> válido;
    # 126 tildes + '.mp4' = 256 bytes (130 caracteres) -> inválido aunque sean pocos caracteres.
    validar_nombre("á" * 125 + ".mp4")
    with pytest.raises(NombreInvalido):
        validar_nombre("á" * 126 + ".mp4")


def test_un_archivo_de_255_bytes_existe_y_uno_de_256_es_422_no_oserror(carpeta: Path) -> None:
    justo = "a" * (MAXIMO_NOMBRE_BYTES - 4) + ".mp4"
    _crear(carpeta, justo)
    assert validar_nombre_en_carpeta(carpeta, justo).name == justo
    with pytest.raises(NombreInvalido):  # y no un OSError(ENAMETOOLONG) escapado
        validar_nombre_en_carpeta(carpeta, "a" + justo)


def test_unicode_con_tildes_y_ene(carpeta: Path) -> None:
    nombre = "cámara_ñandú_1.mp4"
    _crear(carpeta, nombre)
    assert validar_nombre_en_carpeta(carpeta, nombre).name == nombre


# ── Lo que hay en el disco (404) ───────────────────────────────────────────────────────────


def test_un_archivo_normal_devuelve_su_ruta_dentro_de_la_carpeta(carpeta: Path) -> None:
    _crear(carpeta, "v.mp4")
    ruta = validar_nombre_en_carpeta(carpeta, "v.mp4")
    assert ruta == carpeta.resolve() / "v.mp4"


def test_un_byte_es_valido_y_cero_bytes_no(carpeta: Path) -> None:
    _crear(carpeta, "uno.mp4", b"x")
    _crear(carpeta, "cero.mp4", b"")
    assert validar_nombre_en_carpeta(carpeta, "uno.mp4").name == "uno.mp4"
    with pytest.raises(ArchivoNoEncontrado):
        validar_nombre_en_carpeta(carpeta, "cero.mp4")


def test_la_extension_en_mayusculas_se_acepta_en_el_disco(carpeta: Path) -> None:
    _crear(carpeta, "V.MP4")
    assert validar_nombre_en_carpeta(carpeta, "V.MP4").name == "V.MP4"


def test_un_archivo_inexistente_es_404(carpeta: Path) -> None:
    with pytest.raises(ArchivoNoEncontrado):
        validar_nombre_en_carpeta(carpeta, "no_esta.mp4")


def test_un_directorio_con_nombre_de_video_es_404(carpeta: Path) -> None:
    (carpeta / "falso.mp4").mkdir()
    with pytest.raises(ArchivoNoEncontrado):
        validar_nombre_en_carpeta(carpeta, "falso.mp4")


def test_una_fifo_con_nombre_de_video_es_404_y_no_se_queda_colgada(carpeta: Path) -> None:
    os.mkfifo(carpeta / "tuberia.mp4")
    with pytest.raises(ArchivoNoEncontrado):
        validar_nombre_en_carpeta(carpeta, "tuberia.mp4")


def test_un_enlace_a_un_archivo_de_afuera_es_404(tmp_path: Path, carpeta: Path) -> None:
    afuera = _crear(tmp_path, "secreto.mp4")
    os.symlink(afuera, carpeta / "enlace.mp4")
    with pytest.raises(ArchivoNoEncontrado):
        validar_nombre_en_carpeta(carpeta, "enlace.mp4")


def test_un_enlace_a_un_archivo_de_adentro_tambien_es_404(carpeta: Path) -> None:
    _crear(carpeta, "real.mp4")
    os.symlink(carpeta / "real.mp4", carpeta / "alias.mp4")
    with pytest.raises(ArchivoNoEncontrado):
        validar_nombre_en_carpeta(carpeta, "alias.mp4")
    assert validar_nombre_en_carpeta(carpeta, "real.mp4").name == "real.mp4"


def test_un_enlace_roto_o_en_ciclo_es_404(carpeta: Path) -> None:
    os.symlink(carpeta / "no_existe", carpeta / "roto.mp4")
    os.symlink(carpeta / "ciclo.mp4", carpeta / "ciclo.mp4")
    for nombre in ("roto.mp4", "ciclo.mp4"):
        with pytest.raises(ArchivoNoEncontrado):
            validar_nombre_en_carpeta(carpeta, nombre)


def test_una_carpeta_inexistente_es_404(tmp_path: Path) -> None:
    with pytest.raises(ArchivoNoEncontrado):
        validar_nombre_en_carpeta(tmp_path / "no_existe", "v.mp4")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignora los permisos")
def test_una_carpeta_ilegible_es_404_y_no_un_oserror(carpeta: Path) -> None:
    _crear(carpeta, "v.mp4")
    carpeta.chmod(0o000)
    try:
        with pytest.raises(ArchivoNoEncontrado):
            validar_nombre_en_carpeta(carpeta, "v.mp4")
    finally:
        carpeta.chmod(0o700)


def test_la_carpeta_puede_ser_un_enlace_a_la_real(tmp_path: Path, carpeta: Path) -> None:
    """Quien configura la carpeta puede usar un enlace; lo que no se admite es la ENTRADA."""
    _crear(carpeta, "v.mp4")
    alias = tmp_path / "alias"
    os.symlink(carpeta, alias)
    assert validar_nombre_en_carpeta(alias, "v.mp4") == carpeta.resolve() / "v.mp4"


# ── La ruta devuelta nunca sale de la carpeta (T1: la guarda de `parent` sobraba) ──────────


def test_ningun_nombre_valido_escapa_de_la_carpeta(carpeta: Path) -> None:
    """Sin separadores ni punto inicial, el padre es siempre la carpeta: por eso no hay una
    segunda guarda `parent == carpeta`. Se prueba con nombres que parecen escapes."""
    raros = ["a..mp4", "a...mp4", "a .mp4", "~.mp4", "-rf.mp4", "%2e%2e.mp4", "a;b.mp4", "ñ.MOV"]
    for nombre in raros:
        _crear(carpeta, nombre)
        ruta = validar_nombre_en_carpeta(carpeta, nombre)
        assert ruta.parent == carpeta.resolve()
        assert ruta.name == nombre


def test_los_mensajes_de_error_no_llevan_la_ruta_del_servidor(
    tmp_path: Path, carpeta: Path
) -> None:
    casos = ["no_esta.mp4", "x.txt", "a/b.mp4"]
    for nombre in casos:
        with pytest.raises((NombreInvalido, ArchivoNoEncontrado)) as e:
            validar_nombre_en_carpeta(carpeta, nombre)
        assert str(tmp_path) not in str(e.value)
