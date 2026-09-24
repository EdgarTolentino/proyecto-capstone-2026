"""Video: intentos y estado `reintentando`, para que un fallo se vea en `GET /videos` (#29).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("video", sa.Column("intentos", sa.Integer(), server_default="0", nullable=False))
    op.drop_constraint(op.f("ck_video_estado"), "video", type_="check")
    op.create_check_constraint(
        op.f("ck_video_estado"),
        "video",
        "estado IN ('en_cola','procesando','reintentando','listo','error')",
    )


def downgrade() -> None:
    op.execute("UPDATE video SET estado = 'error' WHERE estado = 'reintentando'")
    op.drop_constraint(op.f("ck_video_estado"), "video", type_="check")
    op.create_check_constraint(
        op.f("ck_video_estado"), "video", "estado IN ('en_cola','procesando','listo','error')"
    )
    op.drop_column("video", "intentos")
