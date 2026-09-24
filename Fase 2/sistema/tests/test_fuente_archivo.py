"""`FuenteArchivo`: el puerto, el reloj y la ruta (ADR-005)."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from gepp_worker import FuenteArchivo, FuenteDeCuadros, OrigenReloj
from gepp_worker.fuente_archivo import (
    MetadatosContenedor,
    parsear_ffprobe,
    reloj_de_respaldo,
    resolver_inicio_captura,
    validar_ruta,
)

from .conftest import T0
from .video_sintetico import ALTO, ANCHO, escribir_video


@pytest.fixture
def video_25(tmp_path: Path) -> Path:
    return escribir_video(tmp_path / "camara_01.mp4", fps=25, segundos=2)


def test_cumple_el_protocolo(video_25: Path) -> None:
    assert isinstance(FuenteArchivo(video_25), FuenteDeCuadros)


def test_lee_todos_los_cuadros_con_su_instante(video_25: Path) -> None:
    fuente = FuenteArchivo(video_25, inicio_captura=T0)
    fuente.abrir()
    props = fuente.propiedades()
    cuadros = []
    while fuente.tomar():
        cuadro = fuente.recuperar()
        assert cuadro is not None
        cuadros.append(cuadro)
    fuente.cerrar()

    assert (props.fps, props.ancho, props.alto) == (25.0, ANCHO, ALTO)
    assert props.es_archivo and not props.reconectable
    assert props.cuadros_totales == 50
    assert [c.indice for c in cuadros] == list(range(50))
    for c in cuadros:
        assert c.capture_ts == T0 + timedelta(seconds=c.indice / 25)
        assert c.imagen.shape == (ALTO, ANCHO, 3)


def test_recuperar_sin_tomar_no_devuelve_nada(video_25: Path) -> None:
    fuente = FuenteArchivo(video_25, inicio_captura=T0)
    fuente.abrir()
    assert fuente.recuperar() is None
    fuente.cerrar()


def test_usar_sin_abrir_falla(video_25: Path) -> None:
    fuente = FuenteArchivo(video_25)
    with pytest.raises(RuntimeError, match="abrir"):
        fuente.tomar()
    with pytest.raises(RuntimeError, match="abrir"):
        fuente.propiedades()


def test_video_inexistente_falla(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        FuenteArchivo(tmp_path / "no_existe.mp4").abrir()


@pytest.mark.parametrize("ruta", ["/mnt/c/videos/camara.mp4", "/mnt/d/x.mp4"])
def test_rechaza_rutas_bajo_mnt(ruta: str) -> None:
    with pytest.raises(ValueError, match="/mnt/"):
        FuenteArchivo(ruta)


def test_no_rechaza_mnt_como_parte_de_otro_nombre(tmp_path: Path) -> None:
    ruta = tmp_path / "mnt" / "video.mp4"
    assert validar_ruta(ruta) == ruta.resolve()


# ─────────────────────────── el reloj ───────────────────────────


def test_inicio_manual_manda_sobre_todo(tmp_path: Path) -> None:
    meta = MetadatosContenedor(duracion_s=2.0, creation_time=T0 + timedelta(days=1))
    inicio, origen = resolver_inicio_captura(tmp_path, meta, 2.0, manual=T0)
    assert (inicio, origen) == (T0, OrigenReloj.MANUAL)


def test_inicio_manual_sin_zona_horaria_se_rechaza(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        resolver_inicio_captura(
            tmp_path,
            MetadatosContenedor(),
            2.0,
            manual=datetime(2026, 9, 2, 2, 10),  # noqa: DTZ001 — es lo que se prueba
        )


def test_sin_metadatos_usa_mtime_menos_duracion(video_25: Path) -> None:
    fin = T0 + timedelta(seconds=60)
    os.utime(video_25, (fin.timestamp(), fin.timestamp()))
    inicio, origen = resolver_inicio_captura(video_25, MetadatosContenedor(), 2.0)
    assert origen is OrigenReloj.MTIME
    assert inicio == fin - timedelta(seconds=2)


def test_el_video_sintetico_sin_creation_time_cae_a_mtime(video_25: Path) -> None:
    fin = T0 + timedelta(seconds=60)
    os.utime(video_25, (fin.timestamp(), fin.timestamp()))
    fuente = FuenteArchivo(video_25)
    fuente.abrir()
    props = fuente.propiedades()
    fuente.cerrar()
    assert props.origen_reloj == "mtime"
    assert props.inicio_captura == fin - timedelta(seconds=2)


def test_los_origenes_coinciden_con_el_check_de_la_tabla_video() -> None:
    assert {o.value for o in OrigenReloj} == {"metadatos", "mtime", "manual", "ocr"}


def test_parsea_creation_time_de_ffprobe() -> None:
    salida = (
        '{"format": {"duration": "12.5", "tags": {"creation_time": "2026-09-02T02:10:00.000000Z"}}}'
    )
    meta = parsear_ffprobe(salida)
    assert meta == MetadatosContenedor(duracion_s=12.5, creation_time=T0)


@pytest.mark.parametrize(
    "creation_time",
    ["1970-01-01T00:00:00.000000Z", "1904-01-01T00:00:00Z", "no es fecha"],
)
def test_creation_time_de_equipo_sin_reloj_se_descarta(creation_time: str) -> None:
    salida = f'{{"format": {{"tags": {{"creation_time": "{creation_time}"}}}}}}'
    assert parsear_ffprobe(salida).creation_time is None


def test_creation_time_sin_zona_se_asume_utc() -> None:
    salida = '{"format": {"tags": {"creation_time": "2026-09-02T02:10:00"}}}'
    assert parsear_ffprobe(salida).creation_time == T0


@pytest.mark.integration
@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="necesita ffmpeg y ffprobe instalados",
)
def test_inicio_sale_de_los_metadatos_reales(video_25: Path, tmp_path: Path) -> None:
    con_fecha = tmp_path / "con_fecha.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "quiet", "-y", "-i", str(video_25), "-c", "copy",
            "-metadata", "creation_time=2026-09-02T02:10:00Z", str(con_fecha),
        ],
        check=True,
    )  # fmt: skip
    fuente = FuenteArchivo(con_fecha)
    fuente.abrir()
    props = fuente.propiedades()
    fuente.cerrar()
    assert props.origen_reloj == "metadatos"
    assert props.inicio_captura == datetime(2026, 9, 2, 2, 10, tzinfo=UTC)


def test_el_reloj_de_respaldo_es_la_fecha_del_archivo(tmp_path: Path) -> None:
    # Sin poder leer el video no hay duración: el mtime (fin de la grabación) es lo único.
    roto = tmp_path / "roto.mp4"
    roto.write_bytes(b"no es un video")
    os.utime(roto, (T0.timestamp(), T0.timestamp()))
    assert reloj_de_respaldo(roto) == (T0, OrigenReloj.MTIME)
