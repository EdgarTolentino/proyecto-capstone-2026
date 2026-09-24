"""Las tablas de `docs/arquitectura/01-modelo-de-datos.md`, en SQLAlchemy.

Este módulo es el ÚNICO dueño del esquema (ADR-012). La API y el trabajador lo importan;
ninguno declara tablas propias. Si una columna cambia aquí, cambia con una migración de
Alembic en `gepp_bd/migraciones/versions/` y con el documento del modelo de datos.

Tres decisiones que el esquema hace cumplir y que no se discuten en el código de arriba:

- Todos los umbrales de `regla` están en SEGUNDOS (ADR-005).
- `deteccion` guarda cajas, nunca imágenes, y su `track_id` es efímero (ADR-006).
- `auditoria` no admite UPDATE ni DELETE: lo impiden dos reglas de PostgreSQL.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    ARRAY,
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Nombres de restricciones deterministas: sin esto Alembic genera nombres distintos en
#: cada máquina y `alembic downgrade` no encuentra lo que tiene que borrar.
CONVENCION_DE_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Valores de las columnas TEXT con CHECK. Se exportan para que la API y el trabajador
# validen contra la misma lista que la base, en vez de copiarla.
TIPOS_ZONA = ("interes", "privacidad")
TIPOS_FUENTE = ("carpeta", "rtsp")
ORIGENES_CAPTURE_TS = ("metadatos", "mtime", "manual", "ocr")
ESTADOS_VIDEO = ("en_cola", "procesando", "listo", "error")
BASES_LICITUD = ("obligacion_legal", "interes_legitimo", "contrato")
ESTADOS_HALLAZGO = ("por_revisar", "confirmado", "falso_positivo", "duplicado", "pospuesto")
ESTADOS_ACCION = ("abierta", "en_curso", "cerrada", "vencida")
TIPOS_NOTIFICACION = ("inmediata", "resumen_turno", "escalamiento")
CANALES_NOTIFICACION = ("correo", "telegram", "whatsapp", "webhook")
ESTADOS_NOTIFICACION = ("pendiente", "enviada", "fallida", "acusada")
ROLES = ("administrador", "prevencionista", "supervisor", "auditor")


def en(columna: str, valores: tuple[str, ...]) -> str:
    """Texto de un CHECK `columna IN (...)` a partir de una de las tuplas de arriba."""
    lista = ",".join(f"'{v}'" for v in valores)
    return f"{columna} IN ({lista})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCION_DE_NOMBRES)


TSTZ = DateTime(timezone=True)


class Faena(Base):
    __tablename__ = "faena"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    zona_horaria: Mapped[str] = mapped_column(Text, server_default="America/Santiago")
    creado_en: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now())


class Area(Base):
    __tablename__ = "area"
    __table_args__ = (
        UniqueConstraint("faena_id", "nombre"),
        CheckConstraint("criticidad BETWEEN 1 AND 4", name="criticidad"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    faena_id: Mapped[int] = mapped_column(ForeignKey("faena.id"))
    nombre: Mapped[str] = mapped_column(Text)
    criticidad: Mapped[int] = mapped_column(SmallInteger, server_default="1")


class Fuente(Base):
    """Una sola tabla para la carpeta vigilada (v1) y RTSP (v2): solo cambia `tipo`."""

    __tablename__ = "fuente"
    __table_args__ = (CheckConstraint(en("tipo", TIPOS_FUENTE), name="tipo"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("area.id"))
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    uri: Mapped[str] = mapped_column(Text)
    fps_objetivo: Mapped[float] = mapped_column(REAL, server_default="5.0")
    activa: Mapped[bool] = mapped_column(Boolean, server_default="true")
    cuadro_referencia: Mapped[str | None] = mapped_column(Text)


class Zona(Base):
    """Polígono sobre el cuadro de referencia. `privacidad` se ennegrece ANTES de inferir."""

    __tablename__ = "zona"
    __table_args__ = (CheckConstraint(en("tipo", TIPOS_ZONA), name="tipo"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("area.id"))
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuente.id"))
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    #: [[x, y], ...] normalizado 0..1
    poligono: Mapped[list[list[float]]] = mapped_column(JSONB)
    solape_minimo: Mapped[float] = mapped_column(REAL, server_default="0.5")
    color: Mapped[str | None] = mapped_column(Text)
    #: EPP que la cámara resuelve en esta zona (tabla `zona x EPP x evaluable` de V2, #3).
    #: NULL = sin medir: no restringe. El motor nunca exige lo que la cámara no ve.
    evaluable: Mapped[list[str] | None] = mapped_column(ARRAY(Text))


class Video(Base):
    __tablename__ = "video"
    __table_args__ = (
        CheckConstraint(en("origen_capture_ts", ORIGENES_CAPTURE_TS), name="origen_capture_ts"),
        CheckConstraint(en("estado", ESTADOS_VIDEO), name="estado"),
        Index("ix_video_estado_creado_en", "estado", "creado_en"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuente.id"))
    ruta: Mapped[str] = mapped_column(Text)
    #: Clave de idempotencia: reprocesar el mismo archivo no duplica nada.
    hash_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    bytes: Mapped[int] = mapped_column(BigInteger)
    duracion_s: Mapped[float | None] = mapped_column(REAL)
    fps_declarado: Mapped[float | None] = mapped_column(REAL)
    ancho: Mapped[int | None] = mapped_column(Integer)
    alto: Mapped[int | None] = mapped_column(Integer)
    #: El reloj del sistema. Sale de los metadatos o de (mtime - duración); NUNCA de la hora
    #: de procesamiento (ADR-005).
    capture_ts_inicio: Mapped[datetime] = mapped_column(TSTZ)
    origen_capture_ts: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text, server_default="en_cola")
    error_motivo: Mapped[str | None] = mapped_column(Text)
    cuadros_analizados: Mapped[int | None] = mapped_column(Integer)
    proceso_ms: Mapped[int | None] = mapped_column(BigInteger)
    creado_en: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now())


class Deteccion(Base):
    """La tabla cruda. Guardarla es lo que permite recalcular reglas sin GPU."""

    __tablename__ = "deteccion"
    __table_args__ = (
        CheckConstraint("array_length(bbox, 1) = 4", name="bbox_cuatro"),
        Index("ix_deteccion_video_track_cuadro", "video_id", "track_id", "cuadro_idx"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id", ondelete="CASCADE"))
    cuadro_idx: Mapped[int] = mapped_column(Integer)
    capture_ts: Mapped[datetime] = mapped_column(TSTZ)
    #: EFÍMERO: único dentro del video, jamás entre videos (ADR-006). NULL en los EPP que el
    #: seguidor no sigue: se asocian a la persona al agregar, igual que en `gepp_core`.
    track_id: Mapped[int | None] = mapped_column(Integer)
    clase: Mapped[str] = mapped_column(Text)
    confianza: Mapped[float] = mapped_column(REAL)
    #: x1, y1, x2, y2 normalizado 0..1
    bbox: Mapped[list[float]] = mapped_column(ARRAY(REAL, dimensions=1))
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zona.id"))
    modelo_version: Mapped[str] = mapped_column(Text)


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (CheckConstraint(en("rol", ROLES), name="rol"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    nombre: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(Text)
    #: El supervisor solo ve su área.
    area_id: Mapped[int | None] = mapped_column(ForeignKey("area.id"))
    activo: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Regla(Base):
    """Versionada: cambiar una regla crea una fila nueva y desactiva la anterior."""

    __tablename__ = "regla"
    __table_args__ = (
        UniqueConstraint("area_id", "nombre", "version"),
        CheckConstraint("severidad BETWEEN 1 AND 4", name="severidad"),
        CheckConstraint(en("base_licitud", BASES_LICITUD), name="base_licitud"),
        CheckConstraint("cardinality(epp_exigido) > 0", name="epp_exigido_no_vacio"),
        CheckConstraint(
            "confirmacion_segundos > 0 AND cierre_segundos > 0", name="umbrales_positivos"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("area.id"))
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zona.id"))
    nombre: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    epp_exigido: Mapped[list[str]] = mapped_column(ARRAY(Text))
    # TODOS los umbrales en SEGUNDOS. Los cuadros se derivan en ejecución (ADR-005).
    confirmacion_segundos: Mapped[float] = mapped_column(REAL, server_default="2.0")
    cierre_segundos: Mapped[float] = mapped_column(REAL, server_default="3.0")
    confianza_minima: Mapped[float] = mapped_column(REAL, server_default="0.45")
    severidad: Mapped[int] = mapped_column(SmallInteger)
    #: NULL = todos los turnos
    turno: Mapped[str | None] = mapped_column(Text)
    hora_desde: Mapped[time | None] = mapped_column(Time)
    hora_hasta: Mapped[time | None] = mapped_column(Time)
    activa: Mapped[bool] = mapped_column(Boolean, server_default="true")
    # Gobernanza: la trazabilidad jurídica se audita con un SELECT, no con un PDF.
    base_licitud: Mapped[str] = mapped_column(Text)
    norma_fundante: Mapped[str | None] = mapped_column(Text)
    finalidad_declarada: Mapped[str] = mapped_column(Text)
    retencion_dias: Mapped[int] = mapped_column(Integer, server_default="30")
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    creada_en: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now())


class Hallazgo(Base):
    """La unidad del sistema: una persona, un incumplimiento, un intervalo (ADR-004)."""

    __tablename__ = "hallazgo"
    __table_args__ = (
        CheckConstraint("severidad BETWEEN 1 AND 4", name="severidad"),
        CheckConstraint(en("estado", ESTADOS_HALLAZGO), name="estado"),
        Index("ix_hallazgo_estado_severidad_ts", "estado", "severidad", text("ts_inicio DESC")),
        Index("ix_hallazgo_area_ts", "area_id", text("ts_inicio DESC")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("video.id", ondelete="SET NULL"))
    fuente_id: Mapped[int] = mapped_column(ForeignKey("fuente.id"))
    area_id: Mapped[int] = mapped_column(ForeignKey("area.id"))
    zona_id: Mapped[int | None] = mapped_column(ForeignKey("zona.id"))
    regla_id: Mapped[int] = mapped_column(ForeignKey("regla.id"))
    #: Sin la versión, nadie puede explicar en la S16 un hallazgo disparado con un umbral
    #: que ya no existe.
    regla_version: Mapped[int] = mapped_column(Integer)
    track_id: Mapped[int] = mapped_column(Integer)
    epp_faltante: Mapped[list[str]] = mapped_column(ARRAY(Text))
    severidad: Mapped[int] = mapped_column(SmallInteger)
    # Reloj de captura, no de procesamiento.
    ts_inicio: Mapped[datetime] = mapped_column(TSTZ)
    #: NULL mientras el evento está vivo (v2).
    ts_fin: Mapped[datetime | None] = mapped_column(TSTZ)
    duracion_s: Mapped[float | None] = mapped_column(
        REAL, Computed("EXTRACT(EPOCH FROM (ts_fin - ts_inicio))", persisted=True)
    )
    cuadros_confirmados: Mapped[int] = mapped_column(Integer)
    confianza_media: Mapped[float] = mapped_column(REAL)
    # Triage. Severidad y confianza son ejes INDEPENDIENTES.
    estado: Mapped[str] = mapped_column(Text, server_default="por_revisar")
    revisado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    revisado_en: Mapped[datetime | None] = mapped_column(TSTZ)
    # Etapa 2: el VLM describe, no decide (ADR-001).
    vlm_titulo: Mapped[str | None] = mapped_column(Text)
    vlm_descripcion: Mapped[str | None] = mapped_column(Text)
    vlm_confianza: Mapped[float | None] = mapped_column(REAL)
    vlm_modelo: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now())


class Evidencia(Base):
    """Recorte del hallazgo. Se escribe YA anonimizado: no hay versión con rostro en disco."""

    __tablename__ = "evidencia"
    __table_args__ = (Index("ix_evidencia_purgar_el", "purgar_el"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hallazgo_id: Mapped[int] = mapped_column(ForeignKey("hallazgo.id", ondelete="CASCADE"))
    ruta: Mapped[str] = mapped_column(Text)
    hash_sha256: Mapped[str] = mapped_column(String(64))
    cuadro_idx: Mapped[int] = mapped_column(Integer)
    capture_ts: Mapped[datetime] = mapped_column(TSTZ)
    anonimizado: Mapped[bool] = mapped_column(Boolean, server_default="true")
    #: Calculada según `regla.retencion_dias` (anillo 1 de retención).
    purgar_el: Mapped[date] = mapped_column(Date)


class AccionCorrectiva(Base):
    __tablename__ = "accion_correctiva"
    __table_args__ = (CheckConstraint(en("estado", ESTADOS_ACCION), name="estado"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hallazgo_id: Mapped[int] = mapped_column(ForeignKey("hallazgo.id"))
    responsable_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    descripcion: Mapped[str] = mapped_column(Text)
    plazo: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(Text, server_default="abierta")
    cerrada_en: Mapped[datetime | None] = mapped_column(TSTZ)
    comentario_cierre: Mapped[str | None] = mapped_column(Text)


class Notificacion(Base):
    """Outbox: se escribe en la misma transacción que el hallazgo; otro proceso la envía."""

    __tablename__ = "notificacion"
    __table_args__ = (
        CheckConstraint(en("tipo", TIPOS_NOTIFICACION), name="tipo"),
        CheckConstraint(en("canal", CANALES_NOTIFICACION), name="canal"),
        CheckConstraint(en("estado", ESTADOS_NOTIFICACION), name="estado"),
        Index("ix_notificacion_estado_creada_en", "estado", "creada_en"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    hallazgo_id: Mapped[int | None] = mapped_column(ForeignKey("hallazgo.id"))
    tipo: Mapped[str] = mapped_column(Text)
    canal: Mapped[str] = mapped_column(Text)
    destinatario: Mapped[str] = mapped_column(Text)
    cuerpo: Mapped[dict[str, Any]] = mapped_column(JSONB)
    estado: Mapped[str] = mapped_column(Text, server_default="pendiente")
    intentos: Mapped[int] = mapped_column(Integer, server_default="0")
    enviada_en: Mapped[datetime | None] = mapped_column(TSTZ)
    #: Cierra el ciclo: alguien la recibió.
    acusada_en: Mapped[datetime | None] = mapped_column(TSTZ)
    acusada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    creada_en: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now())
    #: Id del mensaje en el canal. Varias filas comparten uno cuando se agruparon en un aviso.
    id_externo: Mapped[str | None] = mapped_column(Text)
    #: Token de un solo uso del botón "Acuso recibo" (compartido por el grupo).
    token_acuse: Mapped[str | None] = mapped_column(Text, index=True)
    #: Tras un fallo transitorio del canal, no antes de este instante.
    reintentar_despues: Mapped[datetime | None] = mapped_column(TSTZ)
    #: Por qué quedó fallida o bajó al resumen (presupuesto, espera por cámara, ...).
    motivo: Mapped[str | None] = mapped_column(Text)


class Dotacion(Base):
    """Dato ADMINISTRATIVO del cliente. Nada de esto se infiere desde la imagen."""

    __tablename__ = "dotacion"
    __table_args__ = (UniqueConstraint("area_id", "fecha", "turno"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("area.id"))
    fecha: Mapped[date] = mapped_column(Date)
    turno: Mapped[str] = mapped_column(Text)
    n_hombres: Mapped[int] = mapped_column(Integer)
    n_mujeres: Mapped[int] = mapped_column(Integer)
    n_otro: Mapped[int] = mapped_column(Integer, server_default="0")


class Auditoria(Base):
    """Append-only. Las reglas `auditoria_no_update` y `auditoria_no_delete` viven en la
    migración inicial: sin ellas, en una controversia el sistema no puede acreditar nada."""

    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    rol: Mapped[str] = mapped_column(Text)
    accion: Mapped[str] = mapped_column(Text)
    entidad: Mapped[str] = mapped_column(Text)
    entidad_id: Mapped[int | None] = mapped_column(BigInteger)
    motivo: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    ts: Mapped[datetime] = mapped_column(TSTZ, server_default=func.now())
