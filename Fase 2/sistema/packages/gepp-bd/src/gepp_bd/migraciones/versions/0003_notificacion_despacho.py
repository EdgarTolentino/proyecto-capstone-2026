"""Notificación: datos del despacho (PT-13): id en el canal, token de acuse, reintento, motivo.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notificacion", sa.Column("id_externo", sa.Text(), nullable=True))
    op.add_column("notificacion", sa.Column("token_acuse", sa.Text(), nullable=True))
    op.add_column(
        "notificacion", sa.Column("reintentar_despues", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("notificacion", sa.Column("motivo", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_notificacion_token_acuse"), "notificacion", ["token_acuse"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notificacion_token_acuse"), table_name="notificacion")
    op.drop_column("notificacion", "motivo")
    op.drop_column("notificacion", "reintentar_despues")
    op.drop_column("notificacion", "token_acuse")
    op.drop_column("notificacion", "id_externo")
