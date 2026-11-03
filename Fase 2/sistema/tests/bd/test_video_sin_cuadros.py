"""Un video del que no se leyó ni un cuadro queda en `error`, no en `listo` (AV1 sin decodificador).

Recorrido real (vigilante -> cola -> trabajador -> PostgreSQL), como `test_ingesta.py`.
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Deteccion, Evidencia, Hallazgo, Video
from gepp_worker import fuente_archivo
from gepp_worker.cola import EstadoTrabajo
from sqlalchemy import select

from .test_ingesta import ALTO, ANCHO, FPS, MTIME, contar, entorno, escribir_video_ruido

pytestmark = pytest.mark.integration

__all__ = ["entorno"]  # la fixture se reutiliza de test_ingesta


def escribir_video_de_un_cuadro(ruta: Path) -> Path:
    escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (ANCHO, ALTO))
    escritor.write(np.random.default_rng(3).integers(0, 256, (ALTO, ANCHO, 3), dtype=np.uint8))
    escritor.release()
    marca = MTIME.timestamp()
    os.utime(ruta, (marca, marca))
    return ruta


def test_un_video_que_abre_pero_no_entrega_cuadros_queda_en_error_y_no_se_reintenta(
    entorno, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, vigilante, trabajador, _tmp = entorno
    # Lo que hace AV1 sin decodificador: `isOpened()` es verdadero y `grab()` devuelve falso desde
    # el primer cuadro (reproducido con un AV1 real). El decodificador depende de la máquina, por
    # eso aquí se simula el `grab` y no se versiona un archivo.
    monkeypatch.setattr(fuente_archivo.FuenteArchivo, "tomar", lambda _self: False)
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    (trabajo,) = vigilante.sondear()

    assert trabajador.atender_uno() is None

    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    # `error` a la primera: reintentar el mismo archivo con el mismo decodificador falla igual.
    assert (video.estado, video.intentos) == ("error", 1)
    assert video.error_motivo and video.error_motivo.startswith("No se leyó ningún cuadro")
    assert "H.264" in video.error_motivo and str(entrada) not in video.error_motivo
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.ERROR
    filas = [contar(motor, m) for m in (Deteccion, Hallazgo, Evidencia)]
    assert filas == [0, 0, 0]
    assert trabajador.atender_uno() is None  # nada vuelve a la cola
    with transaccion(motor) as s:
        assert s.execute(select(Video.intentos)).scalar_one() == 1


def test_un_video_de_un_solo_cuadro_sigue_el_camino_normal(entorno) -> None:  # type: ignore[no-untyped-def]
    motor, entrada, cola, vigilante, trabajador, _tmp = entorno
    escribir_video_de_un_cuadro(entrada / "uno.mp4")
    vigilante.sondear()
    (trabajo,) = vigilante.sondear()

    assert trabajador.atender_uno() is not None

    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    assert (video.estado, video.intentos, video.error_motivo) == ("listo", 0, None)
    assert video.cuadros_analizados == 1
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.LISTO


def test_si_la_base_cae_al_anotar_el_fallo_el_video_no_queda_atascado(
    entorno, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """Revisión de Codex: con la base caída al anotar, Redis no puede cerrar el trabajo; si lo
    cierra, la fila queda `procesando` y nadie la recupera. Vuelve a la cola y, con la base de
    vuelta, queda en `error` a la primera."""
    motor, entrada, cola, vigilante, trabajador, _tmp = entorno
    monkeypatch.setattr(fuente_archivo.FuenteArchivo, "tomar", lambda _self: False)
    escribir_video_ruido(entrada / "clip.mp4")
    vigilante.sondear()
    (trabajo,) = vigilante.sondear()

    def base_caida(*_a: object, **_k: object) -> bool:
        raise ConnectionError("la base no responde")

    with monkeypatch.context() as m:
        m.setattr(type(trabajador), "_anotar_fallo", base_caida)
        assert trabajador.atender_uno() is None
    assert cola.estado(trabajo.hash_sha256) is not EstadoTrabajo.ERROR  # vuelve a la cola

    assert trabajador.atender_uno() is None  # la base volvió
    with transaccion(motor) as s:
        (video,) = s.execute(select(Video)).scalars()
    assert (video.estado, video.intentos) == ("error", 1)
    assert cola.estado(trabajo.hash_sha256) is EstadoTrabajo.ERROR
