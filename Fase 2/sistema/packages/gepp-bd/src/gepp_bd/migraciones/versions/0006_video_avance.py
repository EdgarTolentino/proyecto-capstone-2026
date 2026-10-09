"""Avance del procesamiento de un video, para mostrarlo mientras se analiza.

Todas las columnas son opcionales: un video que no se está analizando no tiene avance. Es
telemetría del procesamiento (ADR-005): ninguna fecha de detección ni de hallazgo sale de aquí.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("video", sa.Column("avance_fase", sa.Text(), nullable=True))
    op.add_column("video", sa.Column("avance_s", sa.REAL(), nullable=True))
    op.add_column("video", sa.Column("avance_total_s", sa.REAL(), nullable=True))
    op.add_column("video", sa.Column("avance_velocidad", sa.REAL(), nullable=True))
    op.add_column(
        "video", sa.Column("avance_ultimo", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column(
        "video", sa.Column("avance_actualizado", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_video_avance_fase"),
        "video",
        "avance_fase IN ('analizando','guardando')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_video_avance_fase"), "video", type_="check")
    for columna in (
        "avance_actualizado",
        "avance_ultimo",
        "avance_velocidad",
        "avance_total_s",
        "avance_s",
        "avance_fase",
    ):
        op.drop_column("video", columna)
