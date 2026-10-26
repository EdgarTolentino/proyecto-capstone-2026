"""La zona `mosaico` de una cámara cambia lo que ve el detector del trabajador (#203).

PostgreSQL real y un video blanco de 320x240. Un detector espía anota la forma de cada imagen
que recibe: sin zona, el cuadro entero; con zona, solo los mosaicos de su recorte ampliado.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Fuente, Video, Zona
from gepp_core import Deteccion
from gepp_worker.trabajador import Configuracion, ParametrosMosaico, Trabajador
from sqlalchemy import Engine, select

from .test_vivo_trabajador import ALTO, ANCHO, Mundo

pytestmark = pytest.mark.integration

MITAD_IZQUIERDA = [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]]


class Espia:
    version = "espia"

    def __init__(self) -> None:
        self.formas: list[tuple[int, ...]] = []

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        del cuadro_idx, capture_ts  # el protocolo los pide; el espía solo mira la forma
        self.formas.append(imagen.shape)
        return []


@pytest.fixture
def mundo(bd: Engine, tmp_path: Path) -> Mundo:
    return Mundo(bd, tmp_path)


def zona_mosaico(mundo: Mundo, poligono: list[list[float]]) -> None:
    with transaccion(mundo.bd) as s:
        fuente = s.get(Fuente, 1)
        assert fuente is not None
        s.add(
            Zona(
                area_id=fuente.area_id,
                fuente_id=1,
                nombre="foso",
                tipo="mosaico",
                poligono=poligono,
            )
        )


def procesar(mundo: Mundo, espia: Espia, mosaico: ParametrosMosaico | None = None) -> Video:
    config = Configuracion(
        carpeta_evidencia=mundo.tmp / "evidencia", mosaico=mosaico or ParametrosMosaico()
    )
    Trabajador(mundo.bd, mundo.cola, lambda: espia, config).atender_uno()  # type: ignore[arg-type,return-value]
    with transaccion(mundo.bd) as s:
        video = s.execute(select(Video)).scalar_one()
        s.expunge(video)
    return video


def test_sin_zona_de_mosaico_el_detector_ve_el_cuadro_entero(mundo: Mundo) -> None:
    mundo.encolar()
    espia = Espia()
    video = procesar(mundo, espia)
    assert video.estado == "listo"
    assert espia.formas and set(espia.formas) == {(ALTO, ANCHO, 3)}


def test_con_zona_de_mosaico_el_detector_ve_solo_los_mosaicos_del_recorte(mundo: Mundo) -> None:
    zona_mosaico(mundo, MITAD_IZQUIERDA)
    mundo.encolar()
    espia = Espia()
    video = procesar(mundo, espia)
    assert video.estado == "listo" and video.cuadros_analizados
    # Mitad izquierda (160x240) ampliada x2 = 320x480; mosaicos de 384 con solape de 244 px:
    # una columna de 320 y dos filas de 384. Nunca el cuadro entero.
    assert set(espia.formas) == {(384, 320, 3)}
    assert len(espia.formas) == 2 * video.cuadros_analizados


def test_dos_zonas_de_mosaico_detienen_el_video_con_su_motivo(mundo: Mundo) -> None:
    zona_mosaico(mundo, MITAD_IZQUIERDA)
    zona_mosaico(mundo, MITAD_IZQUIERDA)
    mundo.encolar()
    espia = Espia()
    video = procesar(mundo, espia)
    assert (video.estado, video.intentos) == ("reintentando", 1)
    assert "2 zonas de mosaico" in (video.error_motivo or "")
    assert espia.formas == []


def test_demasiados_mosaicos_detienen_el_video_sin_llamar_al_detector(mundo: Mundo) -> None:
    zona_mosaico(mundo, MITAD_IZQUIERDA)
    mundo.encolar()
    espia = Espia()
    # x12 con objetos de hasta 10 px: 96 mosaicos de 384 por cuadro, sobre el tope de 64.
    video = procesar(mundo, espia, ParametrosMosaico(factor=12.0, objeto_max_px=10))
    assert video.estado == "reintentando"
    assert "mosaicos por cuadro" in (video.error_motivo or "")
    assert espia.formas == []
