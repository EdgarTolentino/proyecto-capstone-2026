"""Vigilante por sondeo: estabilidad, `.part`, idempotencia y rechazo de /mnt/ (PT-06)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import fakeredis
import pytest
from gepp_worker.cola import ColaTrabajos
from gepp_worker.vigilante import Vigilante, sha256_de_archivo


@pytest.fixture
def cola() -> ColaTrabajos:
    return ColaTrabajos(fakeredis.FakeRedis())


def test_una_carpeta_bajo_mnt_se_rechaza(cola: ColaTrabajos) -> None:
    with pytest.raises(ValueError, match="/mnt/"):
        Vigilante("/mnt/c/videos", cola, fuente_id=1)


def test_un_archivo_se_encola_solo_cuando_esta_estable(tmp_path: Path, cola: ColaTrabajos) -> None:
    v = Vigilante(tmp_path, cola, fuente_id=1)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"a" * 100)
    assert v.sondear() == []  # primera vez que se ve: todavía no hay con qué comparar
    video.write_bytes(b"a" * 200)  # sigue copiándose
    assert v.sondear() == []
    (trabajo,) = v.sondear()  # dos sondeos iguales: estable
    assert trabajo.bytes == 200
    assert trabajo.hash_sha256 == hashlib.sha256(b"a" * 200).hexdigest()
    assert v.sondear() == []  # no se vuelve a encolar


def test_part_ocultos_vacios_y_no_video_se_ignoran(tmp_path: Path, cola: ColaTrabajos) -> None:
    v = Vigilante(tmp_path, cola, fuente_id=1)
    (tmp_path / "clip.mp4.part").write_bytes(b"x" * 50)
    (tmp_path / ".clip.mp4").write_bytes(b"x" * 50)
    (tmp_path / "vacio.mp4").write_bytes(b"")
    (tmp_path / "notas.txt").write_bytes(b"x" * 50)
    for _ in range(3):
        assert v.sondear() == []
    assert cola.pendientes() == 0


def test_renombrar_el_part_lo_encola(tmp_path: Path, cola: ColaTrabajos) -> None:
    v = Vigilante(tmp_path, cola, fuente_id=1)
    parcial = tmp_path / "clip.mp4.part"
    parcial.write_bytes(b"x" * 50)
    v.sondear()
    v.sondear()
    parcial.rename(tmp_path / "clip.mp4")
    assert v.sondear() == []
    assert len(v.sondear()) == 1


def test_el_mismo_contenido_con_otro_nombre_no_se_duplica(
    tmp_path: Path, cola: ColaTrabajos
) -> None:
    v = Vigilante(tmp_path, cola, fuente_id=1)
    (tmp_path / "a.mp4").write_bytes(b"z" * 64)
    v.sondear()
    assert len(v.sondear()) == 1
    (tmp_path / "copia.mp4").write_bytes(b"z" * 64)
    v.sondear()
    assert v.sondear() == []
    assert cola.pendientes() == 1


@pytest.mark.parametrize("tamano", [0, 1, 7, 8, 9, 100])
def test_el_hash_por_bloques_coincide_con_el_completo(tmp_path: Path, tamano: int) -> None:
    ruta = tmp_path / "f.bin"
    datos = bytes(range(256))[:tamano] * 1
    ruta.write_bytes(datos)
    assert sha256_de_archivo(ruta, bloque=8) == hashlib.sha256(datos).hexdigest()
