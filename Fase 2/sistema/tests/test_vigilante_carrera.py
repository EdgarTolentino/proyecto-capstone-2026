"""El vigilante no muere si un archivo desaparece a mitad de un sondeo.

Otro proceso puede quitar un archivo de la carpeta vigilada (el borrador de segmentos del celular
lo hace a propósito): entre listar la carpeta y mirarlo, o entre ver que está estable y calcular su
hash. Un `FileNotFoundError` que sale de `Vigilante.correr` mata la ingesta sin ruido, así que ese
archivo se salta y el sondeo sigue.
"""

from __future__ import annotations

from pathlib import Path

import fakeredis
import pytest
from gepp_worker import vigilante as modulo
from gepp_worker.cola import ColaTrabajos
from gepp_worker.vigilante import Vigilante


@pytest.fixture
def cola() -> ColaTrabajos:
    return ColaTrabajos(fakeredis.FakeRedis())


def _estable(v: Vigilante, *archivos: Path) -> None:
    """Deja los archivos con dos sondeos iguales ya hechos menos el último."""
    for a in archivos:
        a.write_bytes(b"x" * 100)
    assert v.sondear() == []


def test_un_archivo_que_desaparece_entre_listar_y_mirar_se_salta(
    tmp_path: Path, cola: ColaTrabajos, monkeypatch: pytest.MonkeyPatch
) -> None:
    v = Vigilante(tmp_path, cola, fuente_id=1)
    se_va, se_queda = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _estable(v, se_va, se_queda)
    real = modulo._es_candidato

    def candidato_y_borrado(ruta: Path) -> bool:
        ok = real(ruta)
        if ruta == se_va:
            ruta.unlink()  # la carrera: lo quita otro proceso justo después de listarlo
        return ok

    monkeypatch.setattr(modulo, "_es_candidato", candidato_y_borrado)

    nuevos = v.sondear()  # antes: FileNotFoundError

    assert [Path(t.ruta).name for t in nuevos] == ["b.mp4"]


def test_un_archivo_que_desaparece_antes_del_hash_se_salta(
    tmp_path: Path, cola: ColaTrabajos, monkeypatch: pytest.MonkeyPatch
) -> None:
    v = Vigilante(tmp_path, cola, fuente_id=1)
    se_va, se_queda = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _estable(v, se_va, se_queda)
    real = modulo.sha256_de_archivo

    def hash_tras_borrar(ruta: Path, *args: int) -> str:
        if ruta == se_va:
            ruta.unlink()
        return real(ruta, *args)

    monkeypatch.setattr(modulo, "sha256_de_archivo", hash_tras_borrar)

    nuevos = v.sondear()

    assert [Path(t.ruta).name for t in nuevos] == ["b.mp4"]
    assert cola.pendientes() == 1


def test_un_fallo_de_es_en_un_sondeo_no_detiene_el_bucle(
    tmp_path: Path, cola: ColaTrabajos, monkeypatch: pytest.MonkeyPatch
) -> None:
    v = Vigilante(tmp_path, cola, fuente_id=1)
    llamadas = {"n": 0}
    real = Vigilante.sondear

    def sondear_con_fallo(self: Vigilante) -> list:
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise OSError("E/S transitoria")
        return real(self)

    monkeypatch.setattr(Vigilante, "sondear", sondear_con_fallo)

    v.correr(intervalo_s=0.0, seguir=lambda: llamadas["n"] < 3)

    assert llamadas["n"] == 3


def test_un_error_que_no_es_de_es_no_se_oculta(
    tmp_path: Path, cola: ColaTrabajos, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Solo se perdona la E/S: un defecto de código tiene que seguir cayendo a la vista."""
    v = Vigilante(tmp_path, cola, fuente_id=1)

    def defecto(_: Vigilante) -> list:
        raise ValueError("un defecto")

    monkeypatch.setattr(Vigilante, "sondear", defecto)

    vueltas = iter(range(3))  # acotado: si el error se tragara, el bucle terminaría solo
    with pytest.raises(ValueError, match="un defecto"):
        v.correr(intervalo_s=0.0, seguir=lambda: next(vueltas, None) is not None)
