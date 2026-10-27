# Validación operativa de alertas por Telegram — issue #36

Validación manual del ciclo real de alertas de Guardián EPP con un teléfono. Se sigue
[`docs/operacion/alertas-telegram.md`](../../../../docs/operacion/alertas-telegram.md) y la
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

## Paso 7 — reporte y diagnóstico

El fallo se publicó en la issue #36:
<https://github.com/EdgarTolentino/proyecto-capstone-2026/issues/36#issuecomment-6424417137>.
Su corrección tiene seguimiento independiente en la
[issue #225](https://github.com/EdgarTolentino/proyecto-capstone-2026/issues/225); la solución
propuesta abajo aún no se ha implementado ni probado.

La causa está en la combinación de tres hechos:

1. `scripts/demo.py` inicia el trabajador con `python -m gepp_worker`.
2. `gepp_worker/__main__.py` define `correr_vigilante` y `correr_trabajador`, y las entrega como
   destinos de `multiprocessing.Process`.
3. Windows usa `spawn`: cada hijo inicia un intérprete nuevo y reconstruye el destino por su
   módulo y nombre. Al ejecutar el paquete con `-m`, esas funciones pertenecen temporalmente a
   `__main__`; el `__main__` del hijo es el proceso de arranque de `multiprocessing` y no contiene
   las funciones. Por eso falla al buscarlas.

En Ubuntu, el método habitual es `fork`: el hijo hereda la memoria del padre y no necesita volver
a importar el destino. Todos los jobs de CI actuales usan `ubuntu-latest`, y las pruebas importan
funciones auxiliares de `gepp_worker.__main__` pero no arrancan el comando real con `spawn`. Eso
explica por qué la suite puede pasar mientras la demo falla en Windows.

El archivo ya tiene la protección `if __name__ == "__main__"`; agregar solo `freeze_support()` no
resuelve que los destinos estén definidos en el módulo ejecutado como `__main__`.

La solución recomendada es mover ambos destinos a un módulo importable estable, por ejemplo
`gepp_worker/procesos.py`, e importarlos desde `__main__.py`. Así se serializan como
`gepp_worker.procesos.correr_trabajador` y `gepp_worker.procesos.correr_vigilante`, nombres que el
hijo puede importar en Windows. Debe acompañarse con una prueba que fuerce el contexto `spawn` y
una ejecución del comando real en Windows o en un job de CI para Windows.

Como alternativa operativa, la demo puede ejecutarse en Linux o WSL, donde usa `fork`; eso permite
continuar la validación, pero no corrige la incompatibilidad del comando documentado con Windows.
Otra alternativa técnica es lanzar un punto de entrada que importe `gepp_worker.__main__` como
módulo antes de llamar a `main`; es un parche menor, pero deja la arquitectura más frágil que mover
los destinos a un módulo dedicado.

## Paso 8 — disponibilidad de Ubuntu

Después de informar el fallo, Edgar pidió intentar resolverlo con cambios mínimos. Se eligió
primero la alternativa operativa sin cambios de código: ejecutar la demo en Ubuntu mediante WSL 2.

| Comprobación | Resultado | Estado |
|---|---|---|
| Sistema | Ubuntu sobre WSL 2, kernel Linux x86-64 | Disponible |
| Python del sistema | 3.14.4; el proyecto exige `>=3.12,<3.14` | Requiere entorno separado |
| `uv` | Instalado | Disponible |
| `make` | Instalado | Disponible |
| Docker CLI | Instalado | Disponible |
| Repositorio | Visible desde Ubuntu | Disponible |
| `generativa.mp4` | Visible desde Ubuntu | Disponible |
| PostgreSQL local | Puerto 5432 accesible | Disponible |
| Redis local | Puerto 6379 accesible | Disponible |

No se instaló nada ni se modificó la `.venv` de Windows. El entorno Linux se preparará fuera del
repositorio para no reemplazarla.

## Paso 9 — entorno Linux separado

Se creó `/tmp/gepp-issue36-venv` dentro de Ubuntu mediante `uv`, con el lockfile congelado y sin
extras de GPU. El primer intento terminó antes de instalar porque WSL no conservó una variable de
shell con la ruta que contiene espacios; el segundo usó rutas literales y completó la instalación.

| Comprobación | Resultado | Estado |
|---|---|---|
| Entorno | `/tmp/gepp-issue36-venv` | Creado fuera del repositorio |
| Python | 3.13.15 | Compatible |
| Dependencias | 66 paquetes | Instaladas |
| Paquetes GEPP | `gepp-core`, `gepp-bd`, `gepp-api`, `gepp-vision`, `gepp-worker` | Importables |
| Lockfile | Congelado durante la sincronización | Sin cambios |
| Árbol Git | Limpio después de instalar | Pasó |

`uv` no pudo crear hardlinks entre su caché y `/tmp`, por lo que copió los archivos. La advertencia
afecta el tiempo y espacio de instalación, no el entorno resultante.

## Paso 10 — demo crítica en Ubuntu

Se ejecutó `make demo` desde Ubuntu, con el entorno Linux separado, `generativa.mp4`, detector
simulado y `FUENTE=2`. La ejecución terminó con código 0.

| Resultado | Valor observado |
|---|---|
| Estado del video | `listo` |
| Intentos fallidos | 0 |
| Cuadros analizados | 40 |
| Detecciones | 269 |
| Personas seguidas | 4 |
| Hallazgos | 1 |
| EPP faltante | Casco y chaleco |
| Severidad | 4, crítica |
| Duración | 2,0 segundos |
| Estado del hallazgo | `por_revisar` |
| Evidencias | 1 recorte en la carpeta temporal de Ubuntu |
| Avisos en el outbox | 1 notificación Telegram `pendiente` |

El destinatario se ocultó de la salida. El despachador todavía no se ejecutó, por lo que esta
corrida prepara la prueba de llegada al teléfono pero aún no la acredita.

## Paso 11 — llegada y privacidad del aviso

Se inició el despachador contra `gepp_demo`. Informó `enviados=1` y `fallos=0`. El usuario confirmó
en un iPhone que llegó un mensaje con:

```text
Despachador, campos registrados: enviados=1; fallos=0
PostgreSQL: la marca enviada_en se comprobó en la consulta posterior al acuse (paso 12)
```

Esos campos se anotaron durante la prueba; no se conservó el log textual completo del proceso ni
una consulta individual de PostgreSQL antes del acuse.

- «Frente de obra gruesa · turno A»;
- una persona sin casco ni chaleco;
- «Indicio automatizado. Requiere validación humana.»;
- el botón «Acuso recibo»;
- ningún nombre de persona ni imagen.

La [captura redactada](2026-10-26-alerta-telegram-telefono-redactada.jpg) conserva el mensaje y el
botón; el nombre del bot fue ocultado antes de incorporarla. No contiene metadatos GPS ni de autor.
Su SHA-256 es `E19E6B12D8FA225DD04A0F1AABD02D72281FA4BD55A0195029ABF012761C4D85`.

## Paso 12 — acuse de recibo

El usuario pulsó «Acuso recibo» en Telegram y confirmó que el botón desapareció. La
[captura posterior al acuse](2026-10-26-acuse-telegram-boton-retirado-redactada.jpg) conserva el
mensaje sin el botón y con el nombre del bot oculto. No contiene metadatos GPS. Su SHA-256 es
`9F2027BD0D70C863ABFB885793686925571EBF769B0FC9F3BDBC8052C79D56AB`.

El despachador informó `acusados=1` y `fallos=0`. La consulta de PostgreSQL devolvió una fila con:

```text
Despachador, campos registrados: acusados=1; fallos=0
PostgreSQL, campos registrados: estado=acusada; enviada_en=presente;
acusada_en=presente; acusada_en >= enviada_en
```

Después de comprobar el resultado, el despachador se detuvo de forma controlada.

## Paso 13 — el hallazgo corriente no interrumpe

Se recreó `gepp_demo` y se procesó `generativa.mp4` con detector simulado y `FUENTE=1`. El video
quedó `listo` y produjo un hallazgo de severidad 3, con una notificación inicialmente pendiente.

Al ejecutar un ciclo del despachador se observó:

```text
Despachador, campos registrados: enviados=0; al_resumen=1; fallos=0
PostgreSQL, campos registrados: tipo=resumen_turno; estado=pendiente;
motivo=corriente; enviada_en=vacío
```

La ausencia de un mensaje nuevo se constató manualmente en el iPhone; no es una medición de la API
de Telegram. Después de la comprobación,
el despachador se detuvo de forma controlada.

## Paso 14 — caída y recuperación del canal

Se recreó `gepp_demo` con `FUENTE=2` y una notificación crítica pendiente. Para mantener la sesión
de trabajo conectada, la caída se simuló únicamente en el proceso del despachador mediante un proxy
HTTPS local inaccesible (`HTTPS_PROXY=http://127.0.0.1:1`); no hubo una pérdida real de red ni se
apagó físicamente el wifi.

Durante la caída controlada se observó:

| Resultado | Valor |
|---|---|
| Avisos enviados | 0 |
| Fallos del ciclo | 1 |
| `notificacion.estado` | `pendiente` |
| `notificacion.intentos` | 1 |
| `notificacion.motivo` | `ConnectError` |
| Reintento programado | Sí |
| `notificacion.enviada_en` | Vacío |

Comando usado para aislar la salida HTTPS del despachador, sin cortar PostgreSQL:

```bash
HTTPS_PROXY=http://127.0.0.1:1 \
NO_PROXY=localhost,127.0.0.1 \
UV_PROJECT_ENVIRONMENT=/tmp/gepp-issue36-venv \
UV_PYTHON=3.13 UV_FROZEN=1 \
timeout --signal=INT 8s make \
  GEPP_BD_URL=postgresql+psycopg://gepp:gepp_dev@localhost:5432/gepp_demo \
  despachador
```

Consulta usada después del fallo:

```sql
select estado, intentos, motivo,
       reintentar_despues is not null as tiene_reintento,
       enviada_en is null as sin_envio
from notificacion order by id;
```

Después de vencer la espera de 30 segundos, se retiró el proxy y se ejecutó nuevamente el
despachador. Informó `enviados=1` y `fallos=0`; PostgreSQL mostró `estado=enviada`, dos intentos,
sin espera pendiente y con `enviada_en` presente. El motivo histórico `ConnectError` permaneció en
la fila aun después del envío exitoso.

Comandos de recuperación y comprobación:

```bash
UV_PROJECT_ENVIRONMENT=/tmp/gepp-issue36-venv \
UV_PYTHON=3.13 UV_FROZEN=1 \
make GEPP_BD_URL=postgresql+psycopg://gepp:gepp_dev@localhost:5432/gepp_demo \
  despachador
```

```sql
select estado, intentos, motivo,
       reintentar_despues is null as sin_reintento,
       enviada_en is not null as tiene_envio
from notificacion order by id;
```

El usuario confirmó en el iPhone que llegó el nuevo aviso. La
[captura de la recuperación](2026-10-26-alerta-telegram-recuperada-redactada.jpg) muestra el aviso
anterior de las 4:12 sin botón y el recuperado de las 4:33 con «Acuso recibo». El nombre del bot
está oculto y la imagen no contiene metadatos GPS. Su SHA-256 es
`22D90B0004A04954CEE8FA1A2CD603E7B85FC63B807DD0AC48C61BD721474853`.

## Paso 15 — verificación completa

Con PostgreSQL y Redis arriba se ejecutaron los controles completos de backend y frontend.

| Control | Resultado copiado de la salida |
|---|---|
| Ruff | `All checks passed!` |
| Formato Python | 185 archivos ya formateados |
| Mypy estricto | Sin problemas en 94 archivos fuente |
| Pytest | 1.414 aprobadas, 1 omitida por requerir GPU, 7 advertencias |
| ESLint | Aprobado sin advertencias |
| TypeScript | Aprobado |
| Vitest | 25 archivos y 363 pruebas aprobadas |
| Build | 1.972 módulos transformados |

La primera ejecución de Vitest dentro del sandbox falló al leer archivos temporales internos de
`AppData/Local/Packages/sandbox...` (`ENOENT` en 21 suites). Lint y tipos ya habían aprobado. La
suite se repitió fuera del sandbox y aprobó completa; el primer resultado fue una limitación del
entorno, no una aserción del proyecto.

Se omiten los tiempos porque varían por corrida. Los conteos se verificarán sobre el último commit
del PR y se copiarán en su descripción junto con los comandos y la salida final.

## Avance de las pruebas

| # | Prueba | Estado | Evidencia |
|---|---|---|---|
| 1 | El aviso llega | Pasó | Despachador: `enviados=1`, `fallos=0`; captura redactada |
| 2 | El acuse vuelve a la base | Pasó | `acusados=1`; PostgreSQL en `acusada`; captura sin botón |
| 3 | Lo corriente no avisa de inmediato | Pasó | `enviados=0`, motivo `corriente`; confirmación en iPhone |
| 4 | Una caída temporal no pierde el aviso | Pasó | Pendiente tras `ConnectError`; enviada al recuperar; captura |
| 5 | El aviso no identifica personas | Pasó | Texto del aviso y captura redactada |
| 6 | Presupuesto de 6 avisos por turno | Pendiente | Edgar lo medirá en la máquina con GPU, según #36 |
| 7 | Supresión por cámara y agrupación | Pendiente | No se ejecutaron en esta validación manual |
