"""Esquema inicial: las tablas de docs/arquitectura/01-modelo-de-datos.md.

Revision ID: 0001
Revises:
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "faena",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("zona_horaria", sa.Text(), server_default="America/Santiago", nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_faena")),
    )
    op.create_table(
        "area",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("faena_id", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("criticidad", sa.SmallInteger(), server_default="1", nullable=False),
        sa.CheckConstraint("criticidad BETWEEN 1 AND 4", name=op.f("ck_area_criticidad")),
        sa.ForeignKeyConstraint(["faena_id"], ["faena.id"], name=op.f("fk_area_faena_id_faena")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_area")),
        sa.UniqueConstraint("faena_id", "nombre", name=op.f("uq_area_faena_id_nombre")),
    )
    op.create_table(
        "dotacion",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("turno", sa.Text(), nullable=False),
        sa.Column("n_hombres", sa.Integer(), nullable=False),
        sa.Column("n_mujeres", sa.Integer(), nullable=False),
        sa.Column("n_otro", sa.Integer(), server_default="0", nullable=False),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"], name=op.f("fk_dotacion_area_id_area")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dotacion")),
        sa.UniqueConstraint(
            "area_id", "fecha", "turno", name=op.f("uq_dotacion_area_id_fecha_turno")
        ),
    )
    op.create_table(
        "fuente",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("fps_objetivo", sa.REAL(), server_default="5.0", nullable=False),
        sa.Column("activa", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("cuadro_referencia", sa.Text(), nullable=True),
        sa.CheckConstraint("tipo IN ('carpeta','rtsp')", name=op.f("ck_fuente_tipo")),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"], name=op.f("fk_fuente_area_id_area")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fuente")),
    )
    op.create_table(
        "usuario",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("rol", sa.Text(), nullable=False),
        sa.Column("area_id", sa.BigInteger(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default="true", nullable=False),
        sa.CheckConstraint(
            "rol IN ('administrador','prevencionista','supervisor','auditor')",
            name=op.f("ck_usuario_rol"),
        ),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"], name=op.f("fk_usuario_area_id_area")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuario")),
        sa.UniqueConstraint("email", name=op.f("uq_usuario_email")),
    )
    op.create_table(
        "auditoria",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        sa.Column("rol", sa.Text(), nullable=False),
        sa.Column("accion", sa.Text(), nullable=False),
        sa.Column("entidad", sa.Text(), nullable=False),
        sa.Column("entidad_id", sa.BigInteger(), nullable=True),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "ts", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"], name=op.f("fk_auditoria_usuario_id_usuario")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auditoria")),
    )
    op.create_table(
        "video",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("fuente_id", sa.BigInteger(), nullable=False),
        sa.Column("ruta", sa.Text(), nullable=False),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("duracion_s", sa.REAL(), nullable=True),
        sa.Column("fps_declarado", sa.REAL(), nullable=True),
        sa.Column("ancho", sa.Integer(), nullable=True),
        sa.Column("alto", sa.Integer(), nullable=True),
        sa.Column("capture_ts_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origen_capture_ts", sa.Text(), nullable=False),
        sa.Column("estado", sa.Text(), server_default="en_cola", nullable=False),
        sa.Column("error_motivo", sa.Text(), nullable=True),
        sa.Column("cuadros_analizados", sa.Integer(), nullable=True),
        sa.Column("proceso_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "estado IN ('en_cola','procesando','listo','error')", name=op.f("ck_video_estado")
        ),
        sa.CheckConstraint(
            "origen_capture_ts IN ('metadatos','mtime','manual','ocr')",
            name=op.f("ck_video_origen_capture_ts"),
        ),
        sa.ForeignKeyConstraint(
            ["fuente_id"], ["fuente.id"], name=op.f("fk_video_fuente_id_fuente")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_video")),
        sa.UniqueConstraint("hash_sha256", name=op.f("uq_video_hash_sha256")),
    )
    op.create_index("ix_video_estado_creado_en", "video", ["estado", "creado_en"], unique=False)
    op.create_table(
        "zona",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column("fuente_id", sa.BigInteger(), nullable=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("poligono", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("solape_minimo", sa.REAL(), server_default="0.5", nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
        sa.CheckConstraint("tipo IN ('interes','privacidad')", name=op.f("ck_zona_tipo")),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"], name=op.f("fk_zona_area_id_area")),
        sa.ForeignKeyConstraint(
            ["fuente_id"], ["fuente.id"], name=op.f("fk_zona_fuente_id_fuente")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_zona")),
    )
    op.create_table(
        "deteccion",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("video_id", sa.BigInteger(), nullable=False),
        sa.Column("cuadro_idx", sa.Integer(), nullable=False),
        sa.Column("capture_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("clase", sa.Text(), nullable=False),
        sa.Column("confianza", sa.REAL(), nullable=False),
        sa.Column("bbox", sa.ARRAY(sa.REAL(), dimensions=1), nullable=False),
        sa.Column("zona_id", sa.BigInteger(), nullable=True),
        sa.Column("modelo_version", sa.Text(), nullable=False),
        sa.CheckConstraint("array_length(bbox, 1) = 4", name=op.f("ck_deteccion_bbox_cuatro")),
        sa.ForeignKeyConstraint(
            ["video_id"], ["video.id"], name=op.f("fk_deteccion_video_id_video"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["zona_id"], ["zona.id"], name=op.f("fk_deteccion_zona_id_zona")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deteccion")),
    )
    op.create_index(
        "ix_deteccion_video_track_cuadro",
        "deteccion",
        ["video_id", "track_id", "cuadro_idx"],
        unique=False,
    )
    op.create_table(
        "regla",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column("zona_id", sa.BigInteger(), nullable=True),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("epp_exigido", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("confirmacion_segundos", sa.REAL(), server_default="2.0", nullable=False),
        sa.Column("cierre_segundos", sa.REAL(), server_default="3.0", nullable=False),
        sa.Column("confianza_minima", sa.REAL(), server_default="0.45", nullable=False),
        sa.Column("severidad", sa.SmallInteger(), nullable=False),
        sa.Column("turno", sa.Text(), nullable=True),
        sa.Column("hora_desde", sa.Time(), nullable=True),
        sa.Column("hora_hasta", sa.Time(), nullable=True),
        sa.Column("activa", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("base_licitud", sa.Text(), nullable=False),
        sa.Column("norma_fundante", sa.Text(), nullable=True),
        sa.Column("finalidad_declarada", sa.Text(), nullable=False),
        sa.Column("retencion_dias", sa.Integer(), server_default="30", nullable=False),
        sa.Column("creada_por", sa.BigInteger(), nullable=True),
        sa.Column(
            "creada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "base_licitud IN ('obligacion_legal','interes_legitimo','contrato')",
            name=op.f("ck_regla_base_licitud"),
        ),
        sa.CheckConstraint(
            "cardinality(epp_exigido) > 0", name=op.f("ck_regla_epp_exigido_no_vacio")
        ),
        sa.CheckConstraint(
            "confirmacion_segundos > 0 AND cierre_segundos > 0",
            name=op.f("ck_regla_umbrales_positivos"),
        ),
        sa.CheckConstraint("severidad BETWEEN 1 AND 4", name=op.f("ck_regla_severidad")),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"], name=op.f("fk_regla_area_id_area")),
        sa.ForeignKeyConstraint(
            ["creada_por"], ["usuario.id"], name=op.f("fk_regla_creada_por_usuario")
        ),
        sa.ForeignKeyConstraint(["zona_id"], ["zona.id"], name=op.f("fk_regla_zona_id_zona")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regla")),
        sa.UniqueConstraint(
            "area_id", "nombre", "version", name=op.f("uq_regla_area_id_nombre_version")
        ),
    )
    op.create_table(
        "hallazgo",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("video_id", sa.BigInteger(), nullable=True),
        sa.Column("fuente_id", sa.BigInteger(), nullable=False),
        sa.Column("area_id", sa.BigInteger(), nullable=False),
        sa.Column("zona_id", sa.BigInteger(), nullable=True),
        sa.Column("regla_id", sa.BigInteger(), nullable=False),
        sa.Column("regla_version", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("epp_faltante", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("severidad", sa.SmallInteger(), nullable=False),
        sa.Column("ts_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ts_fin", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "duracion_s",
            sa.REAL(),
            sa.Computed("EXTRACT(EPOCH FROM (ts_fin - ts_inicio))", persisted=True),
            nullable=True,
        ),
        sa.Column("cuadros_confirmados", sa.Integer(), nullable=False),
        sa.Column("confianza_media", sa.REAL(), nullable=False),
        sa.Column("estado", sa.Text(), server_default="por_revisar", nullable=False),
        sa.Column("revisado_por", sa.BigInteger(), nullable=True),
        sa.Column("revisado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vlm_titulo", sa.Text(), nullable=True),
        sa.Column("vlm_descripcion", sa.Text(), nullable=True),
        sa.Column("vlm_confianza", sa.REAL(), nullable=True),
        sa.Column("vlm_modelo", sa.Text(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "estado IN ('por_revisar','confirmado','falso_positivo','duplicado','pospuesto')",
            name=op.f("ck_hallazgo_estado"),
        ),
        sa.CheckConstraint("severidad BETWEEN 1 AND 4", name=op.f("ck_hallazgo_severidad")),
        sa.ForeignKeyConstraint(["area_id"], ["area.id"], name=op.f("fk_hallazgo_area_id_area")),
        sa.ForeignKeyConstraint(
            ["fuente_id"], ["fuente.id"], name=op.f("fk_hallazgo_fuente_id_fuente")
        ),
        sa.ForeignKeyConstraint(
            ["regla_id"], ["regla.id"], name=op.f("fk_hallazgo_regla_id_regla")
        ),
        sa.ForeignKeyConstraint(
            ["revisado_por"], ["usuario.id"], name=op.f("fk_hallazgo_revisado_por_usuario")
        ),
        sa.ForeignKeyConstraint(
            ["video_id"], ["video.id"], name=op.f("fk_hallazgo_video_id_video"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["zona_id"], ["zona.id"], name=op.f("fk_hallazgo_zona_id_zona")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hallazgo")),
    )
    op.create_index(
        "ix_hallazgo_area_ts",
        "hallazgo",
        ["area_id", sa.literal_column("ts_inicio DESC")],
        unique=False,
    )
    op.create_index(
        "ix_hallazgo_estado_severidad_ts",
        "hallazgo",
        ["estado", "severidad", sa.literal_column("ts_inicio DESC")],
        unique=False,
    )
    op.create_table(
        "accion_correctiva",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("hallazgo_id", sa.BigInteger(), nullable=False),
        sa.Column("responsable_id", sa.BigInteger(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("plazo", sa.Date(), nullable=False),
        sa.Column("estado", sa.Text(), server_default="abierta", nullable=False),
        sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comentario_cierre", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "estado IN ('abierta','en_curso','cerrada','vencida')",
            name=op.f("ck_accion_correctiva_estado"),
        ),
        sa.ForeignKeyConstraint(
            ["hallazgo_id"], ["hallazgo.id"], name=op.f("fk_accion_correctiva_hallazgo_id_hallazgo")
        ),
        sa.ForeignKeyConstraint(
            ["responsable_id"],
            ["usuario.id"],
            name=op.f("fk_accion_correctiva_responsable_id_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accion_correctiva")),
    )
    op.create_table(
        "evidencia",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("hallazgo_id", sa.BigInteger(), nullable=False),
        sa.Column("ruta", sa.Text(), nullable=False),
        sa.Column("hash_sha256", sa.String(length=64), nullable=False),
        sa.Column("cuadro_idx", sa.Integer(), nullable=False),
        sa.Column("capture_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anonimizado", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("purgar_el", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["hallazgo_id"],
            ["hallazgo.id"],
            name=op.f("fk_evidencia_hallazgo_id_hallazgo"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidencia")),
    )
    op.create_index("ix_evidencia_purgar_el", "evidencia", ["purgar_el"], unique=False)
    op.create_table(
        "notificacion",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("hallazgo_id", sa.BigInteger(), nullable=True),
        sa.Column("tipo", sa.Text(), nullable=False),
        sa.Column("canal", sa.Text(), nullable=False),
        sa.Column("destinatario", sa.Text(), nullable=False),
        sa.Column("cuerpo", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estado", sa.Text(), server_default="pendiente", nullable=False),
        sa.Column("intentos", sa.Integer(), server_default="0", nullable=False),
        sa.Column("enviada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acusada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acusada_por", sa.BigInteger(), nullable=True),
        sa.Column(
            "creada_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "canal IN ('correo','telegram','whatsapp','webhook')",
            name=op.f("ck_notificacion_canal"),
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente','enviada','fallida','acusada')",
            name=op.f("ck_notificacion_estado"),
        ),
        sa.CheckConstraint(
            "tipo IN ('inmediata','resumen_turno','escalamiento')",
            name=op.f("ck_notificacion_tipo"),
        ),
        sa.ForeignKeyConstraint(
            ["acusada_por"], ["usuario.id"], name=op.f("fk_notificacion_acusada_por_usuario")
        ),
        sa.ForeignKeyConstraint(
            ["hallazgo_id"], ["hallazgo.id"], name=op.f("fk_notificacion_hallazgo_id_hallazgo")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notificacion")),
    )
    op.create_index(
        "ix_notificacion_estado_creada_en", "notificacion", ["estado", "creada_en"], unique=False
    )
    # Append-only: sin esto, en una controversia el sistema no puede acreditar nada.
    # Van aquí y no en los modelos porque SQLAlchemy no declara reglas de PostgreSQL.
    op.execute("CREATE RULE auditoria_no_update AS ON UPDATE TO auditoria DO INSTEAD NOTHING")
    op.execute("CREATE RULE auditoria_no_delete AS ON DELETE TO auditoria DO INSTEAD NOTHING")


def downgrade() -> None:
    op.execute("DROP RULE IF EXISTS auditoria_no_delete ON auditoria")
    op.execute("DROP RULE IF EXISTS auditoria_no_update ON auditoria")
    op.drop_index("ix_notificacion_estado_creada_en", table_name="notificacion")
    op.drop_table("notificacion")
    op.drop_index("ix_evidencia_purgar_el", table_name="evidencia")
    op.drop_table("evidencia")
    op.drop_table("accion_correctiva")
    op.drop_index("ix_hallazgo_estado_severidad_ts", table_name="hallazgo")
    op.drop_index("ix_hallazgo_area_ts", table_name="hallazgo")
    op.drop_table("hallazgo")
    op.drop_table("regla")
    op.drop_index("ix_deteccion_video_track_cuadro", table_name="deteccion")
    op.drop_table("deteccion")
    op.drop_table("zona")
    op.drop_index("ix_video_estado_creado_en", table_name="video")
    op.drop_table("video")
    op.drop_table("auditoria")
    op.drop_table("usuario")
    op.drop_table("fuente")
    op.drop_table("dotacion")
    op.drop_table("area")
    op.drop_table("faena")
