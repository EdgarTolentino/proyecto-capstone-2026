"""La zona `mosaico` de una cámara cambia lo que ve el detector del trabajador (#203).

PostgreSQL real y un video blanco de 320x240. Un detector espía anota la forma de cada imagen
que recibe: sin zona, el cuadro entero; con zona, solo los mosaicos de su recorte ampliado.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Evidencia, Fuente, Video, Zona
from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_worker.trabajador import Configuracion, ParametrosMosaico, Trabajador
from sqlalchemy import Engine, select

from .test_ingesta import MTIME
from .test_vivo_trabajador import ALTO, ANCHO, Mundo

pytestmark = pytest.mark.integration

MITAD_IZQUIERDA = [[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]]
MITAD_DERECHA = [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]]


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


class EspiaBrillo(Espia):
    """Anota además el brillo medio de cada imagen que recibe."""

    def __init__(self) -> None:
        super().__init__()
        self.brillos: list[float] = []

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        self.brillos.append(float(imagen.mean()))
        return super().detectar(imagen, cuadro_idx=cuadro_idx, capture_ts=capture_ts)


class EspiaPersona(Espia):
    """Ve una persona sin casco pegada al borde izquierdo de cada mosaico."""

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        super().detectar(imagen, cuadro_idx=cuadro_idx, capture_ts=capture_ts)
        return [
            Deteccion(
                capture_ts=capture_ts,
                cuadro_idx=cuadro_idx,
                clase=ClaseDetectada.PERSONA,
                caja=Caja(0.0, 0.3, 0.25, 0.6),
                confianza=0.9,
            )
        ]


def encolar_cuadro(mundo: Mundo, cuadro: np.ndarray, segundos: int = 4) -> None:
    """Un video de 10 fps que repite `cuadro`, encolado como lo haría el vigilante."""
    ruta = mundo.tmp / "cuadro.mp4"
    escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), 10, (ANCHO, ALTO))
    for _ in range(10 * segundos):
        escritor.write(cuadro)
    escritor.release()
    os.utime(ruta, (MTIME.timestamp(), MTIME.timestamp()))
    shutil.copy2(ruta, mundo.entrada / "cuadro.mp4")
    mundo.vigilante.sondear()
    assert len(mundo.vigilante.sondear()) == 1


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
    trabajador = Trabajador(mundo.bd, mundo.cola, lambda: espia, config)  # type: ignore[arg-type,return-value]
    trabajador.atender_uno()
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


def test_el_mosaico_mira_la_zona_y_no_su_espejo(mundo: Mundo) -> None:
    """Las dos mitades miden lo mismo: solo el brillo dice cuál se analizó."""
    cuadro = np.full((ALTO, ANCHO, 3), 30, dtype=np.uint8)
    cuadro[:, ANCHO // 2 :] = 225
    zona_mosaico(mundo, MITAD_DERECHA)
    encolar_cuadro(mundo, cuadro)
    espia = EspiaBrillo()
    assert procesar(mundo, espia).estado == "listo"
    assert espia.brillos and min(espia.brillos) > 200


def test_un_recorte_sin_pixeles_detiene_el_video_en_vez_de_terminar_listo(
    mundo: Mundo,
) -> None:
    zona_mosaico(mundo, [[0.5, 0.5], [0.5001, 0.5], [0.5001, 0.5001], [0.5, 0.5001]])
    mundo.encolar()
    espia = Espia()
    video = procesar(mundo, espia)
    assert video.estado == "reintentando"
    assert "no cubre ningún píxel" in (video.error_motivo or "")
    assert espia.formas == []


def test_la_evidencia_pixela_lo_que_queda_fuera_de_la_zona(mundo: Mundo) -> None:
    """Fuera de la zona no se buscan personas: un rostro ahí no se taparía (ADR-006). La mitad
    izquierda es un damero; si el margen del recorte la muestra sin pixelar, se ve."""
    cuadro = np.full((ALTO, ANCHO, 3), 128, dtype=np.uint8)
    damero = ((np.indices((ALTO, ANCHO // 2)).sum(axis=0) // 4) % 2 * 255).astype(np.uint8)
    cuadro[:, : ANCHO // 2] = damero[..., None]
    zona_mosaico(mundo, MITAD_DERECHA)
    encolar_cuadro(mundo, cuadro)
    assert procesar(mundo, EspiaPersona()).estado == "listo"
    with transaccion(mundo.bd) as s:
        rutas = list(s.execute(select(Evidencia.ruta)).scalars())
    assert rutas
    for ruta in rutas:
        recorte = cv2.imread(ruta)
        assert recorte is not None
        # La persona empieza en x = 160 (borde de la zona) y mide 40 px: el margen del 25 %
        # deja 10 columnas de la mitad izquierda a la izquierda del recorte.
        assert float(recorte[:, :8].std()) < 30
