# Base de datos

| Archivo | Qué es |
|---|---|
| `esquema.sql` | Script de creación completo, generado desde las migraciones |
| `diagrama-er.md` | Diagrama ER en Mermaid (GitHub lo dibuja), generado desde los modelos |
| `datos-ejemplo.sql` | Juego de datos de demostración: el perfil de construcción (faena, 2 áreas, 2 cámaras, 2 zonas, 2 reglas y 4 usuarios de rol con correo `.invalid`). Sin datos personales |
| `respaldo.dump` | Respaldo de la base al momento de la entrega final (S15); _pendiente_ |

`esquema.sql` y `diagrama-er.md` se regeneran con `uv run python scripts/exportar_esquema.py`
desde `Fase 2/sistema`; no se editan a mano.

`datos-ejemplo.sql` sale de una base vacía con `make migrar` y `make semilla`, exportada con
`pg_dump --data-only --inserts` (sin `alembic_version` y sin las cuentas del equipo). Se carga
después del esquema: `psql -f esquema.sql && psql -f datos-ejemplo.sql`. Se comprobó así en un
PostgreSQL 17 vacío el 2026-10-13.

> Ningún respaldo puede contener nombres, RUT ni imágenes de personas reales. Para la entrega
> se genera con datos sintéticos.
