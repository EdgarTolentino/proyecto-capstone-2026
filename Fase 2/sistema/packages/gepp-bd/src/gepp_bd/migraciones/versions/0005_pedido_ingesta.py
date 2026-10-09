"""Pedidos de ingesta: la API pide procesar un archivo y el trabajador lo atiende.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pedido_ingesta",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("archivo", sa.Text(), nullable=False),
        sa.Column("fuente_id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=True),
        sa.Column("estado", sa.Text(), server_default="pendiente", nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("video_id", sa.BigInteger(), nullable=True),
        sa.Column("bytes", sa.BigInteger(), nullable=True),
        sa.Column("mtime_ns", sa.BigInteger(), nullable=True),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "estado IN ('pendiente','tomado','registrado','rechazado')",
            name=op.f("ck_pedido_ingesta_estado"),
        ),
        sa.ForeignKeyConstraint(
            ["fuente_id"], ["fuente.id"], name=op.f("fk_pedido_ingesta_fuente_id_fuente")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"], name=op.f("fk_pedido_ingesta_usuario_id_usuario")
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["video.id"],
            name=op.f("fk_pedido_ingesta_video_id_video"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pedido_ingesta")),
    )
    op.create_index(
        "uq_pedido_ingesta_archivo_abierto",
        "pedido_ingesta",
        ["archivo"],
        unique=True,
        postgresql_where=sa.text("estado IN ('pendiente','tomado')"),
    )


def downgrade() -> None:
    op.drop_index("uq_pedido_ingesta_archivo_abierto", table_name="pedido_ingesta")
    op.drop_table("pedido_ingesta")
