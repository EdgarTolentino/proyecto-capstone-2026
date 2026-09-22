"""`/metrics`: cinco métricas por fuente, leídas de la base en cada consulta.

Colector propio y no contadores en memoria: el trabajador es otro proceso y la API puede
reiniciarse; la verdad está en la base (`00-arquitectura.md`, decisión 10). Sin autenticación
ni prefijo, como espera Prometheus: solo expone conteos por cámara, ningún dato de personas.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.responses import Response
from gepp_bd.modelos import AccionCorrectiva, Faena, Fuente, Hallazgo, Notificacion, Video
from gepp_bd.turnos import turno_en_curso
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from gepp_api.notificaciones.politica import PRESUPUESTO_POR_TURNO


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


class ColectorAlertas(Collector):
    """El presupuesto de avisos, MEDIDO, y la tasa de alertas accionables (ADR-008)."""

    def __init__(self, fabrica: sessionmaker[Session]) -> None:
        self._fabrica = fabrica

    def collect(self) -> Iterator[Metric]:
        avisos = GaugeMetricFamily(
            "gepp_avisos", "Notificaciones por tipo y estado", labels=["tipo", "estado"]
        )
        turno = GaugeMetricFamily(
            "gepp_avisos_inmediatos_turno",
            "Avisos inmediatos enviados en el turno en curso (un aviso agrupado cuenta una vez)",
            labels=["turno"],
        )
        presupuesto = GaugeMetricFamily(
            "gepp_presupuesto_avisos_turno", "Presupuesto de avisos inmediatos por turno de 12 h"
        )
        presupuesto.add_metric([], PRESUPUESTO_POR_TURNO)
        accionables = GaugeMetricFamily(
            "gepp_alertas_accionables_ratio",
            "Hallazgos avisados que terminaron en acción correctiva / hallazgos avisados",
        )
        with self._fabrica() as s:
            for tipo, estado, n in s.execute(
                select(Notificacion.tipo, Notificacion.estado, func.count()).group_by(
                    Notificacion.tipo, Notificacion.estado
                )
            ):
                avisos.add_metric([tipo, estado], n)
            zona = s.scalar(select(Faena.zona_horaria).limit(1)) or "America/Santiago"
            t, inicio = turno_en_curso(s.execute(select(func.now())).scalar_one(), zona)
            enviados = s.scalar(
                select(func.count(func.distinct(Notificacion.id_externo))).where(
                    Notificacion.tipo == "inmediata",
                    Notificacion.estado.in_(("enviada", "acusada")),
                    Notificacion.enviada_en >= inicio,
                )
            )
            turno.add_metric([t.codigo], enviados or 0)
            avisados = select(Notificacion.hallazgo_id).where(
                Notificacion.estado.in_(("enviada", "acusada")),
                Notificacion.hallazgo_id.isnot(None),
            )
            emitidos = s.scalar(select(func.count(func.distinct(avisados.c.hallazgo_id))))
            if emitidos:
                con_accion = s.scalar(
                    select(func.count(func.distinct(AccionCorrectiva.hallazgo_id))).where(
                        AccionCorrectiva.hallazgo_id.in_(avisados)
                    )
                )
                accionables.add_metric([], (con_accion or 0) / emitidos)
        yield from (avisos, turno, presupuesto, accionables)


def montar(app: FastAPI) -> None:
    """Registro propio por aplicación: el global de prometheus_client duplicaría métricas
    entre instancias (y entre pruebas)."""
    registro = CollectorRegistry()
    registro.register(ColectorFuentes(app.state.fabrica))
    registro.register(ColectorAlertas(app.state.fabrica))

    @app.get("/metrics", include_in_schema=False)
    def metricas() -> Response:
        return Response(generate_latest(registro), media_type=CONTENT_TYPE_LATEST)
