"""Exporta el esquema y el diagrama entidad-relación a la carpeta de evidencias.

    uv run python scripts/exportar_esquema.py

- `esquema.sql`: el SQL de las migraciones en modo sin conexión (`alembic upgrade --sql`).
  Sale de las migraciones, no de una base viva: dos máquinas generan el mismo archivo.
- `diagrama-er.md`: diagrama Mermaid generado desde `gepp_bd.modelos` (GitHub lo dibuja).

No necesita PostgreSQL levantado.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from alembic import command
from gepp_bd.migrar import configuracion
from gepp_bd.modelos import Base
from sqlalchemy import ForeignKey

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ.parent / "Evidencias Proyecto" / "Evidencias de sistema" / "Base de datos"
URL_FICTICIA = "postgresql+psycopg://gepp@localhost/gepp"


def esquema_sql() -> str:
    salida = io.StringIO()
    cfg = configuracion(URL_FICTICIA)
    cfg.output_buffer = salida
    with contextlib.redirect_stderr(io.StringIO()):
        command.upgrade(cfg, "head", sql=True)
    cabecera = (
        "-- Guardián EPP — esquema de la base de datos (PostgreSQL 17).\n"
        "-- GENERADO por scripts/exportar_esquema.py desde las migraciones de gepp-bd.\n"
        "-- No se edita a mano: se cambia la migración y se vuelve a exportar.\n\n"
    )
    return cabecera + salida.getvalue()


def diagrama_er() -> str:
    lineas = ["erDiagram"]
    relaciones: list[str] = []
    for tabla in Base.metadata.sorted_tables:
        lineas.append(f"    {tabla.name} {{")
        for col in tabla.columns:
            tipo = col.type.compile().split("(")[0].replace(" ", "_").replace("[]", "_ARRAY")
            marcas = []
            if col.primary_key:
                marcas.append("PK")
            if col.foreign_keys:
                marcas.append("FK")
            if col.unique:
                marcas.append("UK")
            sufijo = f" {','.join(marcas)}" if marcas else ""
            lineas.append(f"        {tipo} {col.name}{sufijo}")
        lineas.append("    }")
        for col in tabla.columns:
            fk: ForeignKey
            for fk in col.foreign_keys:
                destino = fk.column.table.name
                cardinal = "|o--o{" if col.nullable else "||--o{"
                relaciones.append(f'    {destino} {cardinal} {tabla.name} : "{col.name}"')
    cuerpo = "\n".join(lineas + relaciones)
    return (
        "# Diagrama entidad-relación\n\n"
        "Generado por `scripts/exportar_esquema.py` desde `gepp_bd.modelos`. La explicación de "
        "cada tabla está en [`docs/arquitectura/01-modelo-de-datos.md`]"
        "(../../../../docs/arquitectura/01-modelo-de-datos.md).\n\n"
        f"```mermaid\n{cuerpo}\n```\n"
    )


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    (DESTINO / "esquema.sql").write_text(esquema_sql(), encoding="utf-8")
    (DESTINO / "diagrama-er.md").write_text(diagrama_er(), encoding="utf-8")
    print(f"Escrito en {DESTINO.relative_to(RAIZ.parent.parent)}")


if __name__ == "__main__":
    main()
