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

## Paso 4 — bot y token local

El usuario creó el bot desde Telegram en iPhone y guardó el token entregado por BotFather
directamente en `Fase 2/sistema/.env`.

La comprobación local confirmó que `GEPP_TELEGRAM_TOKEN` existe, no está vacío y cumple el formato
básico esperado. El valor no se imprimió, no se añadió a Git y no se envió a ningún servicio en
este paso. `GEPP_AVISO_DESTINATARIO` continúa vacío.

## Paso 5 — destinatario del aviso

El usuario inició el bot desde Telegram en iPhone y le envió un mensaje. La primera consulta no
encontró actualizaciones; después de enviar un mensaje nuevo al bot correcto, la segunda consulta
encontró exactamente un chat.

El `chat_id` se guardó directamente en `GEPP_AVISO_DESTINATARIO` dentro de `.env`. La verificación
confirmó que el campo contiene un identificador válido. Su valor no se imprimió ni se incorporó a
Git.

## Paso 6 — demo crítica con `FUENTE=2`

Se ejecutó en Windows el equivalente directo de
`make demo VIDEO=.../generativa.mp4 FUENTE=2`, usando el Python del entorno virtual y el detector
simulado. La ejecución recreó `gepp_demo` y vació la base Redis de la demo, pero falló antes de
registrar el video.

| Campo | Resultado |
|---|---|
| Esperado | Video `listo`, hallazgo crítico y aviso pendiente en el outbox |
| Observado | Los procesos hijos no pudieron cargar `correr_trabajador` y `correr_vigilante` desde `__main__` |
| Estado final informado | `sin registrar` |
| Filas en `video` | 0 |
| Hallazgos | 0 |
| Avisos en el outbox | 0 |
| Código de salida | 1 |

No se intentó corregir ni ejecutar una variante después del fallo. Se conserva el resultado para
informarlo en la issue antes de modificar código, como indican las instrucciones de #36.

### Borrador para la issue #36

> Probé el inicio del recorrido solicitado en Windows, con el detector simulado y `FUENTE=2`.
>
> Comando equivalente ejecutado, porque `make` no está disponible en esta instalación:
>
> ```powershell
> .\.venv\Scripts\python.exe scripts/demo.py <ruta-local>\generativa.mp4 --fuente 2
> ```
>
> Resultado: ❌ la demo recreó `gepp_demo`, pero el video quedó `sin registrar`. Los procesos
> hijos fallaron al iniciar con estos errores:
>
> ```text
> AttributeError: Can't get attribute 'correr_trabajador' on <module '__main__'>
> AttributeError: Can't get attribute 'correr_vigilante' on <module '__main__'>
> ```
>
> Estado comprobado al terminar: 0 videos, 0 hallazgos y 0 avisos en el outbox. Por eso todavía
> no ejecuté las pruebas 1–5 con el teléfono. No intenté corregir el código ni otra variante del
> recorrido, siguiendo la instrucción de esta issue. El token, el `chat_id` y el nombre del bot
> no se incluyeron en la evidencia.

## Avance de las pruebas

| # | Prueba | Estado | Evidencia |
|---|---|---|---|
| 1 | El aviso llega | Pendiente | — |
| 2 | El acuse vuelve a la base | Pendiente | — |
| 3 | Lo corriente no avisa de inmediato | Pendiente | — |
| 4 | Una caída temporal no pierde el aviso | Pendiente | — |
| 5 | El aviso no identifica personas | Pendiente | — |
