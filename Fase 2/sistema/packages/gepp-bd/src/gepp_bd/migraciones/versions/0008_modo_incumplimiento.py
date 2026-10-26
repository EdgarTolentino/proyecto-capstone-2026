"""Modo de incumplimiento: por ausencia o por evidencia positiva (ADR-013, #31).

`ausencia` (el comportamiento de siempre) deduce «sin casco» de que el detector no lo vio;
`evidencia` exige que el modelo haya visto la falta (`cabeza`, `sin_chaleco`). La faena dice
qué modo quiere (`faena.modo_incumplimiento`) y el video guarda el que se aplicó
(`video.modo_incumplimiento`). No se expone en la API (contrato congelado).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "faena",
        sa.Column("modo_incumplimiento", sa.Text(), server_default="ausencia", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_faena_modo_incumplimiento"),
        "faena",
        "modo_incumplimiento IN ('ausencia','evidencia')",
    )

    # El modo EFECTIVO es del video: un modelo sin `cabeza` ni `sin_chaleco` nunca trae
    # evidencia, y recalcular su video en `evidencia` borraría todos sus hallazgos sin aviso.
    # NULL = procesado antes de existir el modo = `ausencia`.
    op.add_column("video", sa.Column("modo_incumplimiento", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_video_modo_incumplimiento"),
        "video",
        "modo_incumplimiento IN ('ausencia','evidencia')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_video_modo_incumplimiento"), "video", type_="check")
    op.drop_column("video", "modo_incumplimiento")
    op.drop_constraint(op.f("ck_faena_modo_incumplimiento"), "faena", type_="check")
    op.drop_column("faena", "modo_incumplimiento")
