"""Las clases que un detector declara saber ver, y el modo que de ahí sale (ADR-013).

`DetectorRFDETR.clases` sale del mismo `MapaDeClases` que `DetectorOnnx.clases`, pero necesita
los pesos y el extra `gpu`: no se prueba aquí (ver `test_detector_rfdetr.py`).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion, ModoIncumplimiento
from gepp_vision.detectores import DetectorOnnx
from gepp_vision.detectores.falso import DetectorFalso, Guion
from gepp_vision.detectores.mosaico import DetectorMosaico, Mosaico
from gepp_worker.trabajador import modo_efectivo

from .test_detector_onnx import escribir_modelo

AUSENCIA, EVIDENCIA = ModoIncumplimiento.AUSENCIA, ModoIncumplimiento.EVIDENCIA
EVIDENCIAS = frozenset({ClaseDetectada.CABEZA, ClaseDetectada.SIN_CHALECO})


class SinClases:
    """Un detector que no declara sus clases."""

    version = "sin-clases"

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        del imagen, cuadro_idx, capture_ts
        return []


class ConClases(SinClases):
    clases = frozenset({ClaseDetectada.PERSONA, ClaseDetectada.CABEZA})


MOSAICO = Mosaico(Caja(0.0, 0.0, 0.5, 1.0), 2.0, 384, 100)


def test_el_detector_onnx_declara_las_clases_de_su_mapa(tmp_path: Path) -> None:
    modelo = escribir_modelo(tmp_path / "m.onnx")  # su mapa: persona y casco
    assert DetectorOnnx(modelo).clases == {ClaseDetectada.PERSONA, ClaseDetectada.CASCO}


def test_el_mosaico_delega_las_clases_a_su_detector_interno() -> None:
    assert DetectorMosaico(ConClases(), MOSAICO).clases == ConClases.clases


def test_el_mosaico_sobre_un_detector_sin_clases_tampoco_las_declara() -> None:
    mosaico = DetectorMosaico(SinClases(), MOSAICO)
    assert getattr(mosaico, "clases", None) is None  # el patrón del trabajador


def test_el_detector_falso_no_declara_clases() -> None:
    """Su guion dice qué aparece, no qué sabría ver un modelo: declararlo sería inventarlo."""
    assert getattr(DetectorFalso(Guion("g", ())), "clases", None) is None


def test_la_faena_en_ausencia_nunca_pasa_a_evidencia() -> None:
    assert modo_efectivo(AUSENCIA, EVIDENCIAS) == (AUSENCIA, None)


def test_evidencia_con_las_dos_clases_se_mantiene() -> None:
    assert modo_efectivo(EVIDENCIA, EVIDENCIAS | {ClaseDetectada.PERSONA}) == (EVIDENCIA, None)


@pytest.mark.parametrize("falta", sorted(EVIDENCIAS))
def test_evidencia_sin_una_de_las_dos_clases_baja_a_ausencia_y_dice_cual(
    falta: ClaseDetectada,
) -> None:
    modo, motivo = modo_efectivo(EVIDENCIA, EVIDENCIAS - {falta})
    assert modo is AUSENCIA
    assert motivo is not None and falta.value in motivo


def test_evidencia_con_un_detector_sin_clases_baja_a_ausencia() -> None:
    modo, motivo = modo_efectivo(EVIDENCIA, None)
    assert modo is AUSENCIA and motivo is not None and "no declara" in motivo


def test_evidencia_con_un_conjunto_vacio_baja_a_ausencia() -> None:
    assert modo_efectivo(EVIDENCIA, frozenset())[0] is AUSENCIA
