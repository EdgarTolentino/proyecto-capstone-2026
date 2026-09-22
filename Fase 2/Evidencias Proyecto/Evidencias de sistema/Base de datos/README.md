# Base de datos

| Archivo | Qué es |
|---|---|
| `esquema.sql` | Script de creación completo, generado desde las migraciones |
| `diagrama-er.md` | Diagrama ER en Mermaid (GitHub lo dibuja), generado desde los modelos |
| `datos-ejemplo.sql` | Juego de datos de demostración, sin datos personales reales |
| `respaldo.dump` | Respaldo de la base al momento de la entrega |

`esquema.sql` y `diagrama-er.md` se regeneran con `uv run python scripts/exportar_esquema.py`
desde `Fase 2/sistema`; no se editan a mano.

> Ningún respaldo puede contener nombres, RUT ni imágenes de personas reales. Para la entrega
> se genera con datos sintéticos.
