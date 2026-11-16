# Base de datos

| Archivo | Qué es |
|---|---|
| `esquema.sql` | Script de creación completo, generado desde las migraciones |
| `diagrama-er.md` | Diagrama ER en Mermaid (GitHub lo dibuja), generado desde los modelos |
| `datos-ejemplo.sql` | Juego de datos de demostración: el perfil de construcción (faena, 2 áreas, 2 cámaras, 2 zonas, 2 reglas y 4 usuarios de rol con correo `.invalid`). Sin datos personales |
| `respaldo.dump` | Respaldo sintético de la entrega final (S15), en formato personalizado de PostgreSQL 17; restauración comprobada |

`esquema.sql` y `diagrama-er.md` se regeneran con `uv run python scripts/exportar_esquema.py`
desde `Fase 2/sistema`; no se editan a mano.

`datos-ejemplo.sql` sale de una base vacía con `make migrar` y `make semilla`, exportada con
`pg_dump --data-only --inserts` (sin `alembic_version` y sin las cuentas del equipo). Se carga
después del esquema: `psql -f esquema.sql && psql -f datos-ejemplo.sql`. Se comprobó así en un
PostgreSQL 17 vacío el 2026-10-13.

> Ningún respaldo puede contener nombres, RUT ni imágenes de personas reales. Para la entrega
> se genera con datos sintéticos.

## Restaurar y comprobar el respaldo

La restauración se comprobó el 2026-11-16 en PostgreSQL 17.11, sobre una base vacía y con
`pg_restore --exit-on-error --single-transaction`. El respaldo restaurado quedó en la migración
`0008`, con cuatro usuarios ficticios y cuatro correos del dominio reservado `.invalid`.

Desde esta carpeta, la prueba se reproduce con Bash y Docker:

```bash
set -euo pipefail
contenedor=$(docker run --detach --rm --network none \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -v "$PWD/respaldo.dump:/respaldo.dump:ro" postgres:17-alpine)
trap 'docker stop "$contenedor" >/dev/null' EXIT

until docker exec "$contenedor" pg_isready -h 127.0.0.1 -U postgres >/dev/null; do
  sleep 1
done
docker exec "$contenedor" createdb -U postgres -T template0 restaurada
docker exec "$contenedor" pg_restore -U postgres --no-owner --no-privileges \
  --exit-on-error --single-transaction -d restaurada /respaldo.dump
docker exec "$contenedor" psql -X -U postgres -d restaurada -v ON_ERROR_STOP=1 \
  -c 'SELECT version_num FROM alembic_version' \
  -c "SELECT count(*) AS usuarios, count(*) FILTER (WHERE email LIKE '%@%.invalid') AS correos_ficticios FROM usuario"
sha256sum respaldo.dump
```

SHA-256 comprobado: `0bca28ca4bcc03ab128b80f89e20084119ea89d705d0e6a1a140153ff657f917`.
