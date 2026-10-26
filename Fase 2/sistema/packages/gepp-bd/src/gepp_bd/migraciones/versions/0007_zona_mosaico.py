"""Zona de tipo `mosaico`: la región de la cámara que el trabajador analiza en mosaico (#203).

Sin mosaico, el modelo achica el cuadro entero a su entrada y en el CCTV de prueba no ve
ningún casco. Con una zona `mosaico`, el trabajador recorta la caja que encierra el polígono,
la amplía y la parte en mosaicos (`gepp_vision.detectores.mosaico`). Va por cámara, como las
de privacidad, porque depende de dónde está y hacia dónde mira cada una.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_zona_tipo"), "zona", type_="check")
    op.create_check_constraint(
        op.f("ck_zona_tipo"), "zona", "tipo IN ('interes','privacidad','mosaico')"
    )


def downgrade() -> None:
    # Una zona `mosaico` no cabe en el esquema anterior: se borra antes de restringir.
    op.execute("DELETE FROM zona WHERE tipo = 'mosaico'")
    op.drop_constraint(op.f("ck_zona_tipo"), "zona", type_="check")
    op.create_check_constraint(op.f("ck_zona_tipo"), "zona", "tipo IN ('interes','privacidad')")
