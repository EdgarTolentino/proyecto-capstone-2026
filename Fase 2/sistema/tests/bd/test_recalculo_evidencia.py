"""El recálculo no deja a un hallazgo con el recorte de OTRA racha (revisión de Codex, #163).

Cuando una regla o el agregador parten en dos un hallazgo viejo, el primero conserva su
identidad (mismo track, regla e inicio) pero termina antes: sus evidencias deben caer dentro de
[ts_inicio, ts_fin]. Contra PostgreSQL real; las detecciones son las crudas guardadas.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from gepp_api.servicios.recalculo import recalcular_video
from gepp_bd import transaccion
from gepp_bd.modelos import Evidencia, Video
from gepp_bd.modelos import Hallazgo as FilaHallazgo
from gepp_bd.repositorios import detecciones, evidencias, hallazgos, videos
from gepp_bd.semilla import cargar, leer
from gepp_core import Hallazgo, Severidad, TipoEPP
from sqlalchemy import Engine, select

from ..conftest import T0, cuadro

pytestmark = pytest.mark.integration

PERFIL = Path(__file__).resolve().parents[2] / "perfiles" / "construccion.yaml"
PASO = 0.25  # múltiplos de 0,25 s: los bordes son exactos


def _escenario(bd: Engine) -> tuple[int, int]:
    """Un video con un track que, en t = 0 a 2, no lleva casco; de 5 a 7, no lleva chaleco; y
    el resto, EPP completo. Devuelve (video_id, hallazgo_id) de un hallazgo VIEJO de 0 a 7."""
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
        video, _ = videos.registrar(
            s,
            videos.NuevoVideo(
                fuente_id=1,
                ruta="/datos/videos/entrada/camara_01/clip.mp4",
                hash_sha256="b" * 64,
                bytes=1024,
                capture_ts_inicio=T0,
                origen_capture_ts="metadatos",
                duracion_s=10.0,
                fps_declarado=25.0,
            ),
        )
        cuadros = []
        for i in range(round(9.0 / PASO) + 1):
            t = i * PASO
            cuadros.append(
                cuadro(
                    t=t, idx=i, con_casco=not (0.0 <= t <= 2.0), con_chaleco=not (5.0 <= t <= 7.0)
                )
            )
        detecciones.insertar(s, video.id, (d for c in cuadros for d in c), modelo_version="falso-0")
        viejo = hallazgos.guardar(
            s,
            Hallazgo(
                track_id=1,
                regla_id=1,
                regla_version=1,
                epp_faltante=frozenset({TipoEPP.CASCO, TipoEPP.CHALECO}),
                severidad=Severidad.ALTA,
                ts_inicio=T0,
                ts_fin=T0 + timedelta(seconds=7),
                cuadros_confirmados=20,
                confianza_media=0.9,
                cuadros_evidencia=(0,),
            ),
            hallazgos.Contexto(fuente_id=1, area_id=1, video_id=video.id),
        )
        return video.id, viejo.id


def _evidencia(bd: Engine, hallazgo_id: int, segundos: float) -> int:
    with transaccion(bd) as s:
        e = evidencias.insertar(
            s,
            hallazgo_id=hallazgo_id,
            ruta=f"/datos/evidencia/{segundos}.jpg",
            hash_sha256="c" * 64,
            cuadro_idx=round(segundos / PASO),
            capture_ts=T0 + timedelta(seconds=segundos),
            purgar_el=date(2027, 1, 1),
        )
        return e.id


def _recalcular(bd: Engine, video_id: int) -> None:
    with transaccion(bd) as s:
        video = s.get(Video, video_id)
        assert video is not None
        recalcular_video(s, video)


def _evidencias_de(bd: Engine, hallazgo_id: int) -> list[float]:
    with transaccion(bd) as s:
        filas = s.execute(
            select(Evidencia.capture_ts).where(Evidencia.hallazgo_id == hallazgo_id)
        ).scalars()
        return sorted((t - T0).total_seconds() for t in filas)


def _primero(bd: Engine, video_id: int) -> FilaHallazgo:
    with transaccion(bd) as s:
        filas = list(
            s.execute(
                select(FilaHallazgo)
                .where(FilaHallazgo.video_id == video_id)
                .order_by(FilaHallazgo.ts_inicio)
            ).scalars()
        )
        s.expunge_all()
    return filas[0]


def test_el_hallazgo_partido_no_conserva_el_recorte_de_la_otra_racha(bd: Engine) -> None:
    video_id, viejo_id = _escenario(bd)
    _evidencia(bd, viejo_id, 5.5)  # el recorte que eligió el trabajador: en la 2.ª racha

    _recalcular(bd, video_id)

    primero = _primero(bd, video_id)
    assert primero.id == viejo_id  # conserva su identidad...
    assert (primero.ts_fin - T0).total_seconds() == 2.0  # ...pero ahora termina en t=2
    assert sorted(primero.epp_faltante) == ["casco"]
    assert _evidencias_de(bd, viejo_id) == []  # y ya no tiene el recorte de t=5,5


@pytest.mark.parametrize(
    ("segundos", "se_conserva"),
    [
        (0.0, True),  # justo en ts_inicio
        (1.0, True),  # dentro
        (2.0, True),  # justo en ts_fin
        (2.25, False),  # un paso después de ts_fin
        (5.5, False),  # en la otra racha
    ],
)
def test_la_evidencia_se_conserva_solo_dentro_de_inicio_y_fin(
    bd: Engine, segundos: float, se_conserva: bool
) -> None:
    video_id, viejo_id = _escenario(bd)
    _evidencia(bd, viejo_id, segundos)

    _recalcular(bd, video_id)

    assert _evidencias_de(bd, viejo_id) == ([segundos] if se_conserva else [])


def test_la_evidencia_de_un_hallazgo_que_no_cambia_se_conserva(bd: Engine) -> None:
    """Sin partir nada, el recálculo no toca los recortes (extremo sano)."""
    video_id, viejo_id = _escenario(bd)
    with transaccion(bd) as s:  # el viejo ya coincide con lo que calculará el agregador
        fila = s.get(FilaHallazgo, viejo_id)
        assert fila is not None
        fila.ts_fin = T0 + timedelta(seconds=2)
    _evidencia(bd, viejo_id, 1.0)

    _recalcular(bd, video_id)

    assert _evidencias_de(bd, viejo_id) == [1.0]
