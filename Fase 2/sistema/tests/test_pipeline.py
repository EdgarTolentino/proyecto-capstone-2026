"""Etapa 1 de punta a punta, sin GPU: video sintético + detector falso (PT-07).

Recorrido real salvo el modelo: `FuenteArchivo` lee el .mp4, el `Muestreador` lo baja a
5 fps, el pipeline enmascara, detecta con el guion, sigue y agrega.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from gepp_core import Deteccion, Regla, TipoEPP
from gepp_vision import MascaraPrivacidad, PipelineEtapa1
from gepp_vision.detectores import DetectorFalso, Guion
from gepp_vision.seguimiento import SeguidorIoU
from gepp_worker import Cuadro, FuenteArchivo, Muestreador

from .conftest import T0
from .video_sintetico import escribir_video

FIXTURES = Path(__file__).parent / "fixtures"


def _cuadros(ruta: Path) -> Iterator[Cuadro]:
    muestreador = Muestreador(FuenteArchivo(ruta, inicio_captura=T0), fps_objetivo=5.0)
    muestreador.abrir()
    try:
        while muestreador.tomar():
            cuadro = muestreador.recuperar()
            if cuadro is not None:
                yield cuadro
    finally:
        muestreador.cerrar()


def _correr(tmp_path: Path, guion: str, regla: Regla, *, fps: float, segundos: float = 5.0):
    video = escribir_video(tmp_path / f"v_{fps}.mp4", fps=fps, segundos=segundos)
    pipeline = PipelineEtapa1(
        DetectorFalso(Guion.desde_json(FIXTURES / guion)), SeguidorIoU(), [regla]
    )
    return pipeline.procesar_todo(_cuadros(video))


def test_persona_sin_casco_tres_segundos_da_un_hallazgo(tmp_path: Path, regla: Regla) -> None:
    resultado = _correr(tmp_path, "guion_sin_casco.json", regla, fps=25.0)
    assert resultado.cuadros == 25  # 5 s a 5 fps
    (hallazgo,) = resultado.hallazgos
    assert hallazgo.epp_faltante == frozenset({TipoEPP.CASCO})
    assert hallazgo.ts_inicio == T0
    # Último cuadro con la persona: 2,8 s (el siguiente, 3,0 s, ya está fuera del guion).
    assert hallazgo.duracion_segundos == pytest.approx(2.8, abs=0.05)
    assert hallazgo.cuadros_confirmados == 15


def test_persona_con_casco_no_da_hallazgos(tmp_path: Path, regla: Regla) -> None:
    resultado = _correr(tmp_path, "guion_con_casco.json", regla, fps=25.0)
    assert resultado.hallazgos == []
    assert any(d.track_id == 1 for d in resultado.detecciones)


@pytest.mark.parametrize("fps", [25.0, 30.0, 3.0])
def test_el_hallazgo_en_segundos_es_invariante_a_la_cadencia(
    tmp_path: Path, regla: Regla, fps: float
) -> None:
    """A 25 y 30 fps el muestreador entrega los mismos instantes; a 3 fps (origen más lento
    que el objetivo) entrega menos cuadros, y la regla de 2 s debe dispararse igual. Una
    regla contada en cuadros de 5 fps no se dispararía a 3."""
    (hallazgo,) = _correr(tmp_path, "guion_sin_casco.json", regla, fps=fps).hallazgos
    assert hallazgo.ts_inicio == T0
    assert hallazgo.epp_faltante == frozenset({TipoEPP.CASCO})
    assert hallazgo.duracion_segundos == pytest.approx(2.8, abs=1 / min(fps, 5.0))


def test_25_y_30_fps_dan_exactamente_el_mismo_hallazgo(tmp_path: Path, regla: Regla) -> None:
    (a,) = _correr(tmp_path, "guion_sin_casco.json", regla, fps=25.0).hallazgos
    (b,) = _correr(tmp_path, "guion_sin_casco.json", regla, fps=30.0).hallazgos
    assert (a.ts_inicio, a.ts_fin, a.cuadros_confirmados) == (
        b.ts_inicio,
        b.ts_fin,
        b.cuadros_confirmados,
    )


def test_los_epp_se_persistirian_sin_identidad(tmp_path: Path, regla: Regla) -> None:
    detecciones = _correr(tmp_path, "guion_sin_casco.json", regla, fps=25.0).detecciones
    assert {d.track_id for d in detecciones if d.clase.value == "persona"} == {1}
    assert {d.track_id for d in detecciones if d.clase.value != "persona"} == {None}


class _Espia:
    """Detector que guarda la imagen que recibe, para ver si ya venía enmascarada."""

    version = "espia"

    def __init__(self) -> None:
        self.imagenes: list[np.ndarray] = []

    def detectar(
        self, imagen: np.ndarray, *, cuadro_idx: int, capture_ts: datetime
    ) -> list[Deteccion]:
        del cuadro_idx, capture_ts  # el espía solo mira la imagen
        self.imagenes.append(imagen.copy())
        return []


def test_la_mascara_se_aplica_antes_de_inferir(tmp_path: Path, regla: Regla) -> None:
    video = escribir_video(tmp_path / "v.mp4", fps=25.0, segundos=1.0)
    espia = _Espia()
    mitad_izquierda = [(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]
    pipeline = PipelineEtapa1(
        espia, SeguidorIoU(), [regla], mascara=MascaraPrivacidad([mitad_izquierda])
    )
    pipeline.procesar_todo(_cuadros(video))
    assert len(espia.imagenes) == 5
    for imagen in espia.imagenes:
        assert not imagen[:, :70].any()  # la zona de privacidad llega en negro
        assert imagen[:, 90:].any()  # el resto no se toca


def test_sin_reglas_no_arranca() -> None:
    with pytest.raises(ValueError, match="al menos una regla"):
        PipelineEtapa1(DetectorFalso([]), SeguidorIoU(), [])
