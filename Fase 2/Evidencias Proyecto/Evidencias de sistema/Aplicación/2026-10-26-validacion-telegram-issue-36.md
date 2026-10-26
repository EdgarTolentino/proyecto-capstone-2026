# Validación operativa de alertas por Telegram — issue #36

Validación manual del ciclo real de alertas de Guardián EPP con un teléfono. Se sigue
[`docs/operacion/alertas-telegram.md`](../../../../../docs/operacion/alertas-telegram.md) y la
instrucción registrada en la issue #36. El detector es simulado y no requiere GPU.

## Alcance

Esta evidencia debe comprobar:

1. Un aviso crítico llega al teléfono.
2. El acuse vuelve a la base de datos.
3. Un incumplimiento corriente no genera un aviso inmediato.
4. Una caída temporal del canal no pierde la notificación.
5. El aviso identifica área, turno, cantidad de personas y EPP, sin nombres ni imágenes.

La medición del presupuesto de seis avisos por turno queda fuera de esta ejecución: según la
asignación de la issue #36, Edgar la realiza en la máquina con GPU.

## Seguridad de la evidencia

- El token del bot y el `chat_id` viven solo en `Fase 2/sistema/.env`.
- El video de prueba no se incorpora al repositorio.
- La captura final debe ocultar el nombre del bot y cualquier dato personal antes de publicarse.
- Si una prueba falla, se registra el resultado antes de modificar código.

## Paso 1 — preparación del repositorio

| Comprobación | Resultado |
|---|---|
| Fecha | 2026-10-26 |
| Commit base | `886f820` |
| Rama de trabajo | `docs/issue-36-validacion-telegram` |
| Árbol antes de iniciar | Limpio |
| Entorno Python local | Disponible en `.venv` |
| Docker, uv y Git | Instalados |
| `Fase 2/sistema/.env` | No existía al comenzar |
| Servicios de Docker | Aún no levantados en este paso |

## Paso 2 — servicios locales

Se levantaron los servicios definidos en `Fase 2/sistema/docker/compose.yml` y se comprobó cada
dependencia directamente.

| Comprobación | Resultado observado | Estado |
|---|---|---|
| `docker compose -f docker/compose.yml up -d --wait` | PostgreSQL y Redis quedaron saludables | Pasó |
| `pg_isready -U gepp -d gepp` | Puerto 5432: acepta conexiones | Pasó |
| `redis-cli ping` | `PONG` | Pasó |

En este paso no se creó la base `gepp_demo`, no se ejecutó el video y no se configuró Telegram.

## Paso 3 — insumos locales

Se encontró `generativa.mp4` en la carpeta local de descargas. El archivo mide 4.566.510 bytes;
no se abrió, procesó ni incorporó al repositorio en este paso.

Se creó `Fase 2/sistema/.env` con la conexión local a PostgreSQL y Redis, el canal `telegram` y
el intervalo del despachador. `GEPP_TELEGRAM_TOKEN` y `GEPP_AVISO_DESTINATARIO` quedaron vacíos.

| Comprobación | Resultado | Estado |
|---|---|---|
| Video local disponible | `generativa.mp4`, 4.566.510 bytes | Pasó |
| `.env` local | Existe | Pasó |
| Protección del `.env` | `git check-ignore` lo reconoce | Pasó |
| Token de Telegram | Vacío | Espera acción del usuario |
| Destinatario de Telegram | Vacío | Se obtiene después de iniciar el bot |

## Avance de las pruebas

| # | Prueba | Estado | Evidencia |
|---|---|---|---|
| 1 | El aviso llega | Pendiente | — |
| 2 | El acuse vuelve a la base | Pendiente | — |
| 3 | Lo corriente no avisa de inmediato | Pendiente | — |
| 4 | Una caída temporal no pierde el aviso | Pendiente | — |
| 5 | El aviso no identifica personas | Pendiente | — |
