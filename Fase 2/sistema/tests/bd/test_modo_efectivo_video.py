"""El modo efectivo es del VIDEO, no de la faena (ADR-013, revisión del PR #207).

Un modelo sin `cabeza` ni `sin_chaleco` nunca trae evidencia. Si la faena pasa a `evidencia` y
se recalcula un video así, el agregador no ve ninguna falta y el recálculo borra los hallazgos
pendientes sin avisar. Por eso el trabajador baja a `ausencia` cuando el modelo no sabe ver la
falta, lo guarda en `video.modo_incumplimiento`, y el recálculo y el simulador usan ese valor.

PostgreSQL real. El detector falso reproduce el guion «persona sin casco, 3 s»: en `ausencia`
da UN hallazgo; en `evidencia` ninguno (el guion no trae cabezas).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from gepp_api.servicios.recalculo import recalcular_video
from gepp_bd import transaccion
from gepp_bd.modelos import Hallazgo, Video
from gepp_core import ClaseDetectada
from gepp_vision.detectores.falso import DetectorFalso, Guion
from gepp_worker.trabajador import Configuracion, Trabajador
from sqlalchemy import Engine, func, select, text

from .test_vivo_trabajador import GUION, Mundo

pytestmark = pytest.mark.integration

TODAS = frozenset(ClaseDetectada)
SIN_SIN_CHALECO = TODAS - {ClaseDetectada.SIN_CHALECO}


class ConClases(DetectorFalso):
    """El detector falso, pero declarando qué clases sabe ver (como un modelo real)."""

    def __init__(self, guion: Guion, clases: frozenset[ClaseDetectada]) -> None:
        super().__init__(guion)
        self._clases = clases

    @property
    def clases(self) -> frozenset[ClaseDetectada]:
        return self._clases


@pytest.fixture
def mundo(bd: Engine, tmp_path: Path) -> Mundo:
    return Mundo(bd, tmp_path)


def _faena(bd: Engine, modo: str) -> None:
    with bd.begin() as c:
        c.execute(text("UPDATE faena SET modo_incumplimiento = :m"), {"m": modo})


def _procesar(mundo: Mundo, detector: DetectorFalso) -> Video:
    mundo.encolar()
    config = Configuracion(carpeta_evidencia=mundo.tmp / "evidencia")
    Trabajador(mundo.bd, mundo.cola, lambda: detector, config).atender_uno()  # type: ignore[arg-type,return-value]
    with transaccion(mundo.bd) as s:
        video = s.execute(select(Video)).scalar_one()
        s.expunge(video)
    assert video.estado == "listo"
    return video


def _hallazgos(bd: Engine) -> int:
    with transaccion(bd) as s:
        return s.scalar(select(func.count()).select_from(Hallazgo)) or 0


def _recalcular(bd: Engine, video_id: int):  # type: ignore[no-untyped-def]
    with transaccion(bd) as s:
        video = s.get(Video, video_id)
        assert video is not None
        return recalcular_video(s, video)


def _fijar_modo_del_video(bd: Engine, modo: str | None) -> None:
    with bd.begin() as c:
        c.execute(text("UPDATE video SET modo_incumplimiento = :m"), {"m": modo})


def _falso() -> DetectorFalso:
    return DetectorFalso(Guion.desde_json(GUION))


def test_faena_en_evidencia_con_un_detector_sin_clases_deja_el_video_en_ausencia(
    mundo: Mundo, capsys: pytest.CaptureFixture[str]
) -> None:
    """El escenario del P1: el detector no declara sus clases, el video se analiza por ausencia
    (conserva su hallazgo) y el recálculo posterior NO lo borra."""
    _faena(mundo.bd, "evidencia")
    video = _procesar(mundo, _falso())
    assert video.modo_incumplimiento == "ausencia"
    assert _hallazgos(mundo.bd) == 1
    assert "no declara sus clases" in capsys.readouterr().err

    resultado = _recalcular(mundo.bd, video.id)
    assert (resultado.eliminados, resultado.conservados) == (0, 0)
    assert _hallazgos(mundo.bd) == 1


def test_faena_en_evidencia_con_un_modelo_sin_sin_chaleco_deja_el_video_en_ausencia(
    mundo: Mundo, capsys: pytest.CaptureFixture[str]
) -> None:
    """Basta que falte UNA de las dos clases de evidencia, y el mensaje dice cuál."""
    _faena(mundo.bd, "evidencia")
    video = _procesar(mundo, ConClases(Guion.desde_json(GUION), SIN_SIN_CHALECO))
    assert video.modo_incumplimiento == "ausencia"
    assert "sin_chaleco" in capsys.readouterr().err
    assert _hallazgos(mundo.bd) == 1


def test_faena_en_evidencia_con_un_modelo_que_trae_las_clases_deja_el_video_en_evidencia(
    mundo: Mundo, capsys: pytest.CaptureFixture[str]
) -> None:
    _faena(mundo.bd, "evidencia")
    video = _procesar(mundo, ConClases(Guion.desde_json(GUION), TODAS))
    assert video.modo_incumplimiento == "evidencia"
    assert capsys.readouterr().err == ""  # sin aviso: se aplicó lo que la faena pidió
    assert _hallazgos(mundo.bd) == 0  # el guion no trae `cabeza`: sin evidencia no hay alerta


def test_faena_en_ausencia_deja_el_video_en_ausencia_aunque_el_modelo_traiga_las_clases(
    mundo: Mundo,
) -> None:
    _faena(mundo.bd, "ausencia")
    video = _procesar(mundo, ConClases(Guion.desde_json(GUION), TODAS))
    assert video.modo_incumplimiento == "ausencia"
    assert _hallazgos(mundo.bd) == 1


def test_un_video_sin_modo_se_recalcula_en_ausencia_aunque_la_faena_pida_evidencia(
    mundo: Mundo,
) -> None:
    """`NULL` = procesado antes de existir el modo."""
    video = _procesar(mundo, _falso())
    _fijar_modo_del_video(mundo.bd, None)
    _faena(mundo.bd, "evidencia")
    resultado = _recalcular(mundo.bd, video.id)
    assert resultado.eliminados == 0
    assert _hallazgos(mundo.bd) == 1


def test_el_recalculo_usa_el_modo_del_video_y_no_el_de_la_faena(mundo: Mundo) -> None:
    """Con la faena en `ausencia` pero el video guardado como `evidencia`, el recálculo
    reevalúa por evidencia: el guion no trae cabezas y el hallazgo pendiente desaparece."""
    video = _procesar(mundo, _falso())
    assert _hallazgos(mundo.bd) == 1
    _fijar_modo_del_video(mundo.bd, "evidencia")
    _faena(mundo.bd, "ausencia")
    assert _recalcular(mundo.bd, video.id).eliminados == 1
    assert _hallazgos(mundo.bd) == 0
