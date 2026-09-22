"""`/metrics`: cinco métricas por fuente, leídas de la base en cada consulta.

Colector propio y no contadores en memoria: el trabajador es otro proceso y la API puede
reiniciarse; la verdad está en la base (`00-arquitectura.md`, decisión 10). Sin autenticación
ni prefijo, como espera Prometheus: solo expone conteos por cámara, ningún dato de personas.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.responses import Response
from gepp_bd.modelos import Fuente, Hallazgo, Video
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker


class ColectorFuentes(Collector):
    def __init__(self, fabrica: sessionmaker[Session]) -> None:
        self._fabrica = fabrica

    def collect(self) -> Iterator[Metric]:
        videos = GaugeMetricFamily(
            "gepp_videos", "Videos por fuente y estado de ingesta", labels=["fuente", "estado"]
        )
        cuadros = CounterMetricFamily(
            "gepp_cuadros_analizados", "Cuadros analizados por fuente", labels=["fuente"]
        )
        proceso = CounterMetricFamily(
            "gepp_proceso_segundos", "Segundos de proceso por fuente", labels=["fuente"]
        )
        hallazgos = GaugeMetricFamily(
            "gepp_hallazgos", "Hallazgos por fuente y severidad", labels=["fuente", "severidad"]
        )
        ultima = GaugeMetricFamily(
            "gepp_ultima_captura_timestamp_segundos",
            "Fin de la última captura procesada, en hora de captura (epoch)",
            labels=["fuente"],
        )
        with self._fabrica() as s:
            nombres = dict(s.execute(select(Fuente.id, Fuente.nombre)).tuples().all())

            def nombre(fid: int) -> str:
                return nombres.get(fid, str(fid))

            for fid, estado, n in s.execute(
                select(Video.fuente_id, Video.estado, func.count()).group_by(
                    Video.fuente_id, Video.estado
                )
            ):
                videos.add_metric([nombre(fid), estado], n)
            fin_captura = Video.capture_ts_inicio + func.make_interval(
                0, 0, 0, 0, 0, 0, func.coalesce(Video.duracion_s, 0)
            )
            for fid, c, ms, fin in s.execute(
                select(
                    Video.fuente_id,
                    func.coalesce(func.sum(Video.cuadros_analizados), 0),
                    func.coalesce(func.sum(Video.proceso_ms), 0),
                    func.max(fin_captura),
                )
                .where(Video.estado == "listo")
                .group_by(Video.fuente_id)
            ):
                cuadros.add_metric([nombre(fid)], float(c))
                proceso.add_metric([nombre(fid)], float(ms) / 1000)
                if fin is not None:
                    ultima.add_metric([nombre(fid)], fin.timestamp())
            for fid, sev, n in s.execute(
                select(Hallazgo.fuente_id, Hallazgo.severidad, func.count()).group_by(
                    Hallazgo.fuente_id, Hallazgo.severidad
                )
            ):
                hallazgos.add_metric([nombre(fid), str(sev)], n)
        yield from (videos, cuadros, proceso, hallazgos, ultima)


def montar(app: FastAPI) -> None:
    """Registro propio por aplicación: el global de prometheus_client duplicaría métricas
    entre instancias (y entre pruebas)."""
    registro = CollectorRegistry()
    registro.register(ColectorFuentes(app.state.fabrica))

    @app.get("/metrics", include_in_schema=False)
    def metricas() -> Response:
        return Response(generate_latest(registro), media_type=CONTENT_TYPE_LATEST)
