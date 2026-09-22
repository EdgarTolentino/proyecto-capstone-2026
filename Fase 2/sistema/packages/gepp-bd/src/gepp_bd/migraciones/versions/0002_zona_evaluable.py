"""Zona: EPP evaluables por cámara (tabla `zona x EPP x evaluable` de V2, #3).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL = sin medir todavía: no restringe. Un arreglo vacío sí restringe (nada es evaluable).
    op.add_column("zona", sa.Column("evaluable", sa.ARRAY(sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("zona", "evaluable")
