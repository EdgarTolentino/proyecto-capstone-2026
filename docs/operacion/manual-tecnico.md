# Manual técnico — Guardián EPP

**Versión 1.0 · noviembre de 2026.** Explica cómo instalar, configurar, levantar y verificar el
sistema en un equipo nuevo. Está escrito para quien lo instala desde cero, sin ayuda del equipo.
El uso de la web está en el *Manual de Usuario* (`Fase 2/Evidencias Proyecto/Evidencias de
documentación/`).

Todos los comandos se corren desde `Fase 2/sistema`, salvo que se indique otra carpeta. **La ruta
tiene un espacio**, así que siempre va entre comillas.

## 1. Qué se instala

| Pieza | Qué hace | Cómo se levanta | Puerto |
|---|---|---|---|
| PostgreSQL 17 | Hallazgos, reglas, videos, notificaciones y auditoría | `make up` (Docker) | 5432 |
| Redis 7.2 | Cola entre el vigilante y el trabajador (ADR-009) | `make up` (Docker) | 6379 |
| API (`gepp-api`) | REST de la web, autenticación por rol y reportes | `make api` | 8000 |
| Trabajador (`gepp-worker`) | Vigila la carpeta, atiende los pedidos de la web y corre el detector | `uv run --env-file .env python -m gepp_worker` | — |
| Despachador | Envía los avisos del outbox por Telegram | `make despachador` | — |
| Web (`apps/web`) | Bandeja, visor, reglas, panel, reportes y sala en vivo | `npm run dev` en `apps/web` | 5173 |

El dominio (`gepp-core`), la base (`gepp-bd`) y la visión (`gepp-vision`) son bibliotecas: no se
levantan solas. Las fronteras entre paquetes están en el ADR-007.

## 2. Requisitos

| Requisito | Versión | Nota |
|---|---|---|
| Sistema operativo | Linux o Windows con WSL2 (Ubuntu) | En Windows nativo la demo falla al iniciar procesos (#225) |
| Python | 3.12 o 3.13 | Los dos se prueban en el CI |
| [uv](https://docs.astral.sh/uv/) | reciente | Crea el entorno y las dependencias |
| Docker con Compose | reciente | PostgreSQL y Redis |
| Node.js | 22 | La versión del CI. Solo para la web |
| GPU NVIDIA con CUDA | opcional | Solo para el modelo en PyTorch y para el procesamiento en vivo |
| ffmpeg | opcional | Solo para el celular como cámara y para `scripts/inventario_video.py` |

Sin GPU, el sistema funciona completo con el modelo ONNX en CPU o con el detector simulado.

## 3. Instalación

### 3.1 Portátil sin GPU

```bash
git clone https://github.com/EdgarTolentino/proyecto-capstone-2026.git
cd "proyecto-capstone-2026/Fase 2/sistema"

make setup                 # entorno Python con todos los paquetes
cp .env.example .env       # configuración local: ajusta las carpetas a rutas que existan (§4.1)
make up                    # PostgreSQL y Redis, espera a que estén listos
make migrar                # crea las tablas en la base de GEPP_BD_URL
make semilla               # faena, cámaras, zonas, reglas, dotación y cuentas (ADR-011)
make test                  # pruebas sin GPU; las de base de datos usan la de `make up`
```

La web se instala aparte:

```bash
cd apps/web
npm ci
cp .env.example .env.development.local   # ver §4.2
```

### 3.2 Máquina con GPU

```bash
make setup-gpu             # igual que setup, más rfdetr y torch con CUDA
export UV_NO_SYNC=1        # ver la advertencia
```

> **Advertencia.** En la máquina con GPU, un `uv sync` sin `--extra gpu` **desinstala `rfdetr` y
> `torch`**, y `uv run` sincroniza el entorno antes de correr. Después de `make setup-gpu`, exporta
> `UV_NO_SYNC=1` (equivale a `uv run --no-sync`) para que los `make` no toquen el entorno, o llama
> a las herramientas desde `.venv/bin/`. Vuelve a correr `make setup-gpu` si cambian las
> dependencias.

## 4. Configuración

### 4.1 Servidor y trabajador: `.env`

`make` carga el `.env` de `Fase 2/sistema` si existe. Lo que se corre sin `make` no lo lee solo: va
con `uv run --env-file .env`. **El `.env` nunca se versiona**: el token de
Telegram y las cuentas viven solo ahí. Cada variable está comentada en `.env.example`; estas son
las que hay que decidir:

| Grupo | Variable | Qué fija | Por defecto |
|---|---|---|---|
| Servicios | `GEPP_BD_URL` | Base PostgreSQL | la de `docker/compose.yml` |
| | `GEPP_REDIS_URL` | Cola del trabajador | `redis://localhost:6379/0` |
| Acceso | `GEPP_API_TOKENS` | Quién entra a la API: `token=correo,...` | Sin definir: las cuentas de demostración (ver §9) |
| | `GEPP_API_HOST`, `GEPP_API_PUERTO` | Dónde escucha la API | `127.0.0.1`, `8000` |
| Carpetas | `GEPP_CARPETA_VIGILADA` | Videos que se procesan solos, de una cámara | **obligatoria** para el trabajador |
| | `GEPP_FUENTE_ID` | Cámara a la que pertenece la carpeta vigilada | `1` |
| | `GEPP_CARPETA_ENTRADA` | Videos que se piden desde la web | Sin valor: la web no puede pedirlos |
| | `GEPP_CARPETA_EVIDENCIA` | Recortes de evidencia, ya difuminados | `/datos/evidencia` |
| Detector | `GEPP_GUION_FALSO` | Detector simulado con un guion JSON | Si está, no se usa modelo |
| | `GEPP_MODELO_RUTA` | Modelo, con su `.clases.json` al lado (§6) | — |
| | `GEPP_MODELO_MOTOR` | `onnx` (CPU) o `rfdetr` (GPU) | `onnx` |
| | `GEPP_MODELO_VARIANTE` | Con `rfdetr`: `nano` o `small` | `nano` |
| | `GEPP_UMBRAL_CONFIANZA` | Corte del detector | `0.25` |
| | `GEPP_FPS_OBJETIVO` | Cuadros por segundo que se analizan | `5.0` |
| | `GEPP_MOSAICO_FACTOR`, `_LADO`, `_OBJETO_MAX_PX` | Cómo se parte la zona `mosaico` de una cámara | `2.0`, entrada del modelo, `100` |
| | `GEPP_MAXIMO_INTENTOS` | Intentos antes de dejar un video en `error` | `3` |
| Avisos | `GEPP_AVISO_CANAL`, `GEPP_AVISO_DESTINATARIO` | Si están los dos, cada hallazgo escribe su aviso | — |
| | `GEPP_TELEGRAM_TOKEN` | Token del bot. **Es un secreto** | — |
| | `GEPP_DESPACHO_INTERVALO_S` | Cada cuánto revisa el despachador | `5` |
| Vista en vivo | `GEPP_VISTA_EN_VIVO` | `1` la enciende. Muestra rostros sin tapar (ADR-006) | `0` |
| | `GEPP_CARPETA_VIVO`, `GEPP_VIVO_FPS` | Dónde y a qué ritmo se escribe | `/dev/shm/gepp-vivo`, `25` |

Las tres carpetas de video y evidencia **deben estar en el sistema de archivos de Linux**: en WSL2,
inotify no funciona sobre `/mnt/c` y el sistema rechaza esas rutas (ADR-005).
`GEPP_CARPETA_ENTRADA` no puede ser ni estar dentro de `GEPP_CARPETA_VIGILADA`, ni al revés.

### 4.2 Web: `apps/web/.env.development.local`

| Variable | Qué fija | Por defecto |
|---|---|---|
| `VITE_API_URL` | API real, por ejemplo `http://localhost:8000/api/v1` | Sin valor: el servidor simulado de `make mock` en `:4010` |
| `VITE_API_TOKEN` | Con qué cuenta entra la web | `demo` |

Ese archivo solo lo lee `npm run dev`: las pruebas y `vite build` no lo cargan.

## 5. Base de datos

| Tarea | Comando |
|---|---|
| Levantar o detener PostgreSQL y Redis | `make up` · `make down` |
| Aplicar las migraciones | `make migrar` (equivale a `python -m gepp_bd.migrar subir`) |
| Volver a una revisión | `uv run python -m gepp_bd.migrar bajar <revisión>` (sin revisión, a `base`) |
| Cargar un perfil de faena | `make semilla` (construcción) · `make semilla PERFIL=perfiles/otro.yaml`. Si la faena ya existe, solo suma las cuentas que falten |
| Regenerar `esquema.sql` y `diagrama-er.md` de la entrega | `uv run python scripts/exportar_esquema.py` (sale de las migraciones; no necesita PostgreSQL) |

Las migraciones están en `packages/gepp-bd/src/gepp_bd/migraciones/versions/`. El esquema, el
diagrama entidad-relación y los datos de ejemplo de la entrega están en `Fase 2/Evidencias
Proyecto/Evidencias de sistema/Base de datos/`. El modelo de datos está explicado en
`docs/arquitectura/01-modelo-de-datos.md`.

Los datos de PostgreSQL quedan en el volumen `pgdata` de Docker: `make down` no los borra.

### Respaldo y restauración

> **Pendiente (#40, Miguel).** Procedimiento con `pg_dump` y `pg_restore` probado de punta a punta,
> y `respaldo.dump` sintético en la carpeta Base de datos (#41).

## 6. El modelo

Los pesos **no están en el repositorio** (ADR-002). Se piden al equipo y se dejan fuera de él, con
su `.clases.json` al lado:

| Motor | Archivo | Dónde corre | Para qué |
|---|---|---|---|
| `onnx` | `.onnx` + `.clases.json` | CPU | Desarrollar y probar sin GPU |
| `rfdetr` | `.pth` + `.clases.json` | GPU (`make setup-gpu`) | Procesamiento en vivo y mediciones |

El modelo de la entrega es **epp-v3** (RF-DETR Small, 5 clases). El `.clases.json` lo genera
`scripts/exportar_onnx.py`: no se escribe a mano. Cómo se prueba un modelo con un video propio está
en [`modelo-onnx.md`](modelo-onnx.md).

**El mosaico.** En una cámara alta, los cascos del fondo miden pocos píxeles y el modelo no los ve
en el cuadro entero (#203). Si la cámara tiene una zona `mosaico`, el trabajador analiza solo esa
región, ampliada por partes. En CPU tarda segundos por cuadro: para tiempo real hace falta GPU.

## 7. Levantar el sistema

### 7.1 Todo de una vez

```bash
make demo-todo VIDEO=ruta/al/video.mp4 [MODELO=ruta/modelo.onnx] [FUENTE=2]
make demo-apagar
```

Recrea una base de demostración, procesa el video, levanta la API y la web y, si el `.env` tiene el
bot, también el despachador. Los registros quedan en `$TMPDIR/gepp-demo`. El paso a paso, con lo
que se ve en cada pantalla, está en [`recorrido-h2.md`](recorrido-h2.md).

### 7.2 Por partes

En terminales separadas, con el `.env` configurado:

```bash
make api                                   # API en http://127.0.0.1:8000
uv run --env-file .env python -m gepp_worker   # vigilante y trabajador
make despachador                           # avisos por Telegram (opcional)
cd apps/web && npm run dev                 # web en http://localhost:5173
```

El trabajador no arranca si faltan `GEPP_BD_URL`, `GEPP_REDIS_URL` o `GEPP_CARPETA_VIGILADA`.

### 7.3 Sin servidor: el servidor simulado

`make mock` sirve el contrato `contracts/openapi.yaml` en el puerto 4010. Con él, la web funciona
sin base, sin API y sin modelo. Cabecera: `Authorization: Bearer demo`.

### 7.4 Demostración en vivo

El sistema completo en contenedores, con el trabajador en GPU, la sala en vivo y un teléfono como
cámara, está en `despliegue/local/README.md` y `despliegue/celular/README.md`. El diseño, en
[`despliegue/spec-en-vivo.md`](despliegue/spec-en-vivo.md). Las alertas, en
[`alertas-telegram.md`](alertas-telegram.md).

## 8. Verificación

Antes de entregar o de abrir un pull request:

```bash
make up                                    # sin la base, se omiten sus pruebas
make lint && make tipos && make test       # ruff, mypy y pytest sin GPU
make contrato                              # la API sirve exactamente openapi.yaml

cd apps/web
npm run lint && npm run typecheck && npm test && npm run build
```

El CI (`.github/workflows/ci.yml`) corre lo mismo en cada cambio y además bloquea dependencias con
licencias prohibidas (ADR-002). El job «Todo en verde» decide si un cambio puede entrar.

## 9. Seguridad y privacidad

- **Las cuentas por defecto son públicas.** Sin `GEPP_API_TOKENS`, entran las cuentas de
  demostración, y sus tokens están en el repositorio. Fuera del equipo, defínela siempre. Definida
  pero vacía, no entra nadie (401).
- **Nunca al repositorio:** el `.env`, videos de obra, pesos, datasets, rostros sin difuminar,
  credenciales ni RUT.
- **La evidencia se guarda difuminada.** La vista en vivo es la única excepción: muestra rostros sin
  tapar, está apagada por defecto, vive en memoria y no se guarda (ADR-006).
- **Los reportes suprimen en el servidor** toda celda con menos de cinco casos.

Lo que el sistema nunca hace con personas está en `docs/producto/02-privacidad-y-cumplimiento.md`.

## 10. Problemas frecuentes

| Síntoma | Causa | Qué hacer |
|---|---|---|
| El sistema rechaza la carpeta de videos | Está bajo `/mnt/`: en WSL2, inotify no funciona ahí | Usa una carpeta del sistema de archivos de Linux (§4.1) |
| Después de un `make`, no se puede importar `rfdetr` | `uv run` sincronizó sin el extra `gpu` | `make setup-gpu` y `export UV_NO_SYNC=1` (§3.2) |
| Redis no arranca: «Can't handle RDB format version 12» | Un volumen viejo de Redis 7.4 | `docker compose -f docker/compose.yml up -d -V redis` |
| La web responde 401 | `VITE_API_TOKEN` no coincide con `GEPP_API_TOKENS` | Revisa las dos (§4) |
| «Procesar video» devuelve `409 entrada_no_configurada` | Falta `GEPP_CARPETA_ENTRADA` | Defínela en la API y en el trabajador, con la misma ruta |
| El trabajador se detiene al arrancar por `GEPP_MOSAICO_LADO` | El lado no coincide con la entrada del modelo | Déjalo vacío |
| La demo en Windows termina con `sin registrar` | `multiprocessing` en Windows (#225) | Córrela en WSL2 |
| Las pruebas de base de datos aparecen omitidas | PostgreSQL no está arriba | `make up` |
| El trabajador termina con «Faltan variables de entorno» | Se corrió sin `make` y sin `--env-file` | `uv run --env-file .env python -m gepp_worker` |
