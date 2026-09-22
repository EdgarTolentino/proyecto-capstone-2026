"""El despachador del outbox: un ciclo corto que se repite (`python -m gepp_api.notificaciones`).

Cada ciclo:

1. recoge los acuses ("Acuso recibo") y cierra esos avisos en la base;
2. baja al resumen lo corriente y decide lo grave con la política (agrupación, esperas y
   presupuesto de 6 por turno);
3. envía lo que corresponde, con reintentos si el canal falla;
4. al empezar un turno, envía el resumen del anterior.

Entrega "al menos una vez": si el canal acepta y la base cae antes de confirmar, el aviso puede
repetirse. Perder un aviso sería peor.
"""

from __future__ import annotations

import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from gepp_bd import transaccion
from gepp_bd.modelos import Area, Hallazgo, Notificacion
from gepp_bd.repositorios import auditoria
from gepp_bd.repositorios import notificaciones as repo
from gepp_bd.turnos import turno_en_curso
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from gepp_api.notificaciones.canal import Aviso, CanalNotificacion, Estado
from gepp_api.notificaciones.politica import (
    Decision,
    Historial,
    Pendiente,
    agrupar,
    decidir,
    es_grave,
    texto_inmediato,
    texto_resumen,
)


@dataclass(slots=True)
class ResultadoCiclo:
    acusados: int = 0
    avisos_enviados: int = 0
    al_resumen: int = 0
    esperando: int = 0
    fallos: int = 0
    resumenes: int = 0
    motivos: list[str] = field(default_factory=list)

    @property
    def vacio(self) -> bool:
        return not any(
            (self.acusados, self.avisos_enviados, self.al_resumen, self.fallos, self.resumenes)
        )


class Despachador:
    def __init__(
        self, motor: Engine, canal: CanalNotificacion, zona_horaria: str = "America/Santiago"
    ) -> None:
        self._motor = motor
        self._canal = canal
        self._tz = zona_horaria

    def ciclo(self) -> ResultadoCiclo:
        r = ResultadoCiclo()
        tokens = self._canal.acuses_recibidos()
        with transaccion(self._motor) as s:
            for token in tokens:
                r.acusados += repo.acusar_por_token(s, token)
        with transaccion(self._motor) as s:
            ahora = s.execute(select(func.now())).scalar_one()
            turno, inicio = turno_en_curso(ahora, self._tz)
            self._inmediatos(s, ahora, turno.codigo, inicio, r)
        with transaccion(self._motor) as s:
            self._resumenes(s, inicio, r)
        return r

    # ── Avisos inmediatos ───────────────────────────────────────────────────────────────

    def _pendientes(self, s: Session) -> list[Pendiente]:
        filas = [
            n
            for n in repo.tomar_pendientes(s, limite=500, tipo="inmediata")
            if n.canal == self._canal.nombre and n.hallazgo_id is not None
        ]
        if not filas:
            return []
        datos = {
            h.id: (h, nombre)
            for h, nombre in s.execute(
                select(Hallazgo, Area.nombre)
                .join(Area, Area.id == Hallazgo.area_id)
                .where(Hallazgo.id.in_([n.hallazgo_id for n in filas]))
            ).all()
        }
        pendientes = []
        for n in filas:
            h, area = datos[n.hallazgo_id]
            pendientes.append(
                Pendiente(
                    id=n.id,
                    destinatario=n.destinatario,
                    canal=n.canal,
                    area=area,
                    fuente_id=h.fuente_id,
                    epp=tuple(sorted(h.epp_faltante)),
                    severidad=h.severidad,
                    duracion_s=h.duracion_s or 0.0,
                    ts_inicio=h.ts_inicio,
                    ts_fin=h.ts_fin,
                )
            )
        return pendientes

    def _historial(self, s: Session, inicio_turno: datetime) -> Historial:
        """Lo enviado de inmediato en este turno. Un aviso agrupado cuenta UNA vez."""
        enviados = (
            select(
                Notificacion.destinatario,
                Notificacion.id_externo,
                func.max(Notificacion.enviada_en).label("en"),
            )
            .where(
                Notificacion.tipo == "inmediata",
                Notificacion.canal == self._canal.nombre,
                Notificacion.estado.in_(("enviada", "acusada")),
                Notificacion.enviada_en >= inicio_turno,
            )
            .group_by(Notificacion.destinatario, Notificacion.id_externo)
        )
        h = Historial()
        for destinatario, _, en in s.execute(enviados).all():
            h.enviados_en_turno[destinatario] = h.enviados_en_turno.get(destinatario, 0) + 1
            if destinatario not in h.ultimo_envio or en > h.ultimo_envio[destinatario]:
                h.ultimo_envio[destinatario] = en
        por_camara = (
            select(Notificacion.destinatario, Hallazgo.fuente_id, func.max(Notificacion.enviada_en))
            .join(Hallazgo, Hallazgo.id == Notificacion.hallazgo_id)
            .where(
                Notificacion.tipo == "inmediata",
                Notificacion.estado.in_(("enviada", "acusada")),
                Notificacion.enviada_en >= inicio_turno - timedelta(hours=1),
            )
            .group_by(Notificacion.destinatario, Hallazgo.fuente_id)
        )
        for destinatario, fuente_id, en in s.execute(por_camara).all():
            h.ultimo_por_camara[(destinatario, fuente_id)] = en
        return h

    def _inmediatos(
        self, s: Session, ahora: datetime, turno: str, inicio: datetime, r: ResultadoCiclo
    ) -> None:
        pendientes = self._pendientes(s)
        corrientes = [p.id for p in pendientes if not es_grave(p)]
        if corrientes:
            # Dos velocidades (ADR-008): lo corriente no interrumpe, va al resumen del turno.
            repo.bajar_al_resumen(s, corrientes, motivo="corriente")
            r.al_resumen += len(corrientes)
        graves = [p for p in pendientes if es_grave(p)]
        tz = ZoneInfo(self._tz)
        for v in decidir(agrupar(graves), self._historial(s, inicio), ahora):
            ids = [p.id for p in v.grupo.items]
            if v.decision is Decision.ESPERAR:
                r.esperando += len(ids)
                continue
            if v.decision is Decision.AL_RESUMEN:
                repo.bajar_al_resumen(s, ids, motivo=v.motivo)
                r.al_resumen += len(ids)
                r.motivos.append(v.motivo)
                # El presupuesto es un requisito con número: cada vez que actúa queda registrado.
                auditoria.registrar(
                    s,
                    rol="sistema",
                    accion=f"aviso:{v.motivo}",
                    entidad="notificacion",
                    entidad_id=ids[0],
                    motivo=f"{len(ids)} filas al resumen · {v.grupo.area}",
                )
                continue
            titulo, cuerpo = texto_inmediato(v.grupo, turno, tz)
            aviso = Aviso(titulo, cuerpo, secrets.token_urlsafe(16))
            if self._enviar(s, ids, aviso, v.grupo.destinatario, r):
                r.avisos_enviados += 1

    def _enviar(
        self, s: Session, ids: list[int], aviso: Aviso, destino: str, r: ResultadoCiclo
    ) -> bool:
        resultado = self._canal.enviar(aviso, destino)
        if resultado.estado is Estado.ACEPTADO:
            repo.marcar_grupo_enviado(
                s, ids, id_externo=resultado.id_externo or "", token_acuse=aviso.token_acuse
            )
            return True
        r.fallos += 1
        if resultado.estado is Estado.FALLO_TRANSITORIO:
            repo.marcar_grupo_fallido(
                s,
                ids,
                reintentar_en_s=resultado.reintentar_en_s or 30,
                motivo=resultado.motivo or "fallo transitorio",
            )
        else:
            repo.marcar_grupo_rechazado(s, ids, motivo=resultado.motivo or "rechazado")
        return False

    # ── Resumen de fin de turno ─────────────────────────────────────────────────────────

    def _resumenes(self, s: Session, inicio_turno: datetime, r: ResultadoCiclo) -> None:
        """Lo corriente de turnos YA terminados, en un mensaje por destinatario."""
        filas = [
            n
            for n in repo.tomar_pendientes(s, limite=5000, tipo="resumen_turno")
            if n.canal == self._canal.nombre and n.creada_en < inicio_turno
        ]
        if not filas:
            return
        hallazgos = {
            h.id: (nombre, tuple(sorted(h.epp_faltante)))
            for h, nombre in s.execute(
                select(Hallazgo, Area.nombre)
                .join(Area, Area.id == Hallazgo.area_id)
                .where(Hallazgo.id.in_([n.hallazgo_id for n in filas if n.hallazgo_id]))
            ).all()
        }
        por_destino: dict[str, list[Notificacion]] = defaultdict(list)
        for n in filas:
            por_destino[n.destinatario].append(n)
        anterior, _ = turno_en_curso(inicio_turno - timedelta(seconds=1), self._tz)
        for destino, grupo in por_destino.items():
            contenido = [hallazgos[n.hallazgo_id] for n in grupo if n.hallazgo_id in hallazgos]
            titulo, cuerpo = texto_resumen(contenido, anterior.codigo)
            if self._enviar(
                s,
                [n.id for n in grupo],
                Aviso(titulo, cuerpo, secrets.token_urlsafe(16)),
                destino,
                r,
            ):
                r.resumenes += 1
