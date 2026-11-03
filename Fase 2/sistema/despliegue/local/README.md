# Demo local: un solo sistema en el portátil

Spec: `docs/operacion/despliegue/spec-en-vivo.md` (§2). Un `docker compose` con PostgreSQL, Redis,
trabajador con GPU, API, web y despachador de Telegram. Una sola base: lo que ve el proyector es
el mismo evento que dispara la alerta. Los scripts `armar-demo.sh` y `rearmar-demo.sh` (otro PR)
viven en esta carpeta y usan los nombres de abajo.

## Nombres (contrato con los scripts)

| Qué | Nombre |
|---|---|
| Proyecto | `gepp-demo` (`-p gepp-demo`; el compose trae `name: gepp-demo`) |
| Servicios | `postgres`, `redis`, `preparar` (una vez), `permisos` (una vez), `trabajador` (GPU), `trabajador-cpu` (perfil `cpu`), `api`, `web`, `despachador` |
| Contenedores | `gepp-demo-<servicio>-1` |
| Volúmenes | `gepp-demo_pgdata`, `gepp-demo_evidencia`, `gepp-demo_vigilada`, `gepp-demo_vivo` (tmpfs) |
| Imágenes | `gepp-api:demo`, `gepp-web:demo`, `gepp-worker:demo-gpu`, `gepp-worker:demo-cpu` |
| Puertos (loopback) | web `18080` · API `18000` · PostgreSQL `15432` |
| Base / Redis | usuario y base `gepp` · `redis://redis:6379/0` |

## Variables

Nada va en archivos. La ruta del compose lleva un espacio: entre comillas.

| Variable | Obligatoria | Qué |
|---|---|---|
| `DEMO_PG_PASSWORD` | sí | contraseña de PostgreSQL |
| `DEMO_TOKEN` | sí | token de la API **y** token compilado en la web: cambiarlo y volver a `up --build` mantiene los dos iguales (si no, 401). Queda dentro del JS: es de demostración |
| `MODELO_PTH`, `MODELO_CLASES` | para GPU | ruta del checkpoint `.pth` y de su `.clases.json` |
| `MODELO_ONNX`, `MODELO_CLASES` | para CPU | ruta del `.onnx` y de su `.clases.json` |
| `GEPP_TELEGRAM_TOKEN`, `GEPP_AVISO_DESTINATARIO` | no | bot y chat. Sin token, el despachador queda en espera (no muere) |

## Levantar

```bash
export DEMO_PG_PASSWORD=$(openssl rand -hex 12) DEMO_TOKEN=$(openssl rand -hex 16)
export MODELO_PTH=/ruta/al/checkpoint.pth MODELO_CLASES=/ruta/al/modelo.clases.json
docker compose -p gepp-demo -f despliegue/local/compose.yml up -d --build --wait
# panel: http://127.0.0.1:18080  (token = $DEMO_TOKEN en Authorization: Bearer)

# dejar el video de demo en la carpeta vigilada (el trabajador lo procesa solo):
docker run --rm -v gepp-demo_vigilada:/v -v "$VIDEO":/in.mp4:ro --entrypoint cp gepp-api:demo /in.mp4 /v/demo.mp4

# sin GPU: --profile cpu y el servicio trabajador-cpu (NO el trabajador GPU)
docker compose -p gepp-demo -f despliegue/local/compose.yml --profile cpu up -d --build \
  postgres redis preparar permisos api web despachador trabajador-cpu
docker compose -p gepp-demo -f despliegue/local/compose.yml down -v        # al terminar
```

Con la GPU: comprobar antes que esté libre (`nvidia-smi`) y no entrenar mientras tanto (ADR-010).

## Decisiones

- **Un usuario (1000) para el trabajador y la API.** Cada subcarpeta del anillo de la vista es 0700
  (`vivo.py`); la API solo la lee si es el mismo usuario. El dueño del tmpfs `vivo` va en la opción de
  montaje (`uid=1000`): un `chown` sobre tmpfs se pierde al salir el último contenedor.
- **Evidencia compartida** (`evidencia`): `Evidencia.ruta` es una ruta del trabajador y la API la abre
  tal cual; el mismo volumen en la misma ruta la hace llegar. `permisos` la entrega al usuario 1000.
- **Vista en vivo encendida** en trabajador y API (condición 7: el cliente está en este portátil).
- **Cámara 2** de la semilla (`GEPP_FUENTE_ID=2`, severidad 4, D5).
- **Despachador** con `restart: unless-stopped`: si la base se corta, vuelve. Es el ÚNICO consumidor del
  bot (`getUpdates` admite uno); no correr otro (`make despachador`) a la vez.
- **Web compilada con el token de la API**: `web` toma `DEMO_TOKEN` como argumento de compilación.
