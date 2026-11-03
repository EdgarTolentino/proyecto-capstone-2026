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
| Puertos (loopback) | web `18080` (proyector) y `18081` (tailnet) · API `18000` · PostgreSQL `15432` |
| Base / Redis | usuario y base `gepp` · `redis://redis:6379/0` |

## Variables

Nada va en archivos. La ruta del compose lleva un espacio: entre comillas.

| Variable | Obligatoria | Qué |
|---|---|---|
| `DEMO_PG_PASSWORD` | sí | contraseña de PostgreSQL |
| `DEMO_TOKEN` | sí | token de la API **y** token compilado en la web: cambiarlo y volver a `up --build` mantiene los dos iguales (si no, 401). Queda dentro del JS: es de demostración |
| `MODELO_PTH`, `MODELO_CLASES` | para GPU | ruta del checkpoint `.pth` y de su `.clases.json`. **Sin ellas el trabajador monta `/dev/null`, se cae al cargar el modelo y la demo parece arriba sin analizar nada**: comprobar que estén antes de levantar (lo hará `armar-demo.sh`) |
| `MODELO_ONNX`, `MODELO_CLASES` | para CPU | ruta del `.onnx` y de su `.clases.json`. Lo mismo: sin ellas no se analiza nada |
| `GEPP_TELEGRAM_TOKEN`, `GEPP_AVISO_DESTINATARIO` | no | bot y chat. Sin token, el despachador queda en espera (no muere) |
| `DEMO_IDENTIDADES` | no | `"correo=token,correo2=token2"`: quién entra por la puerta de la tailnet (abajo) y con qué token. Vacía o sin definir: esa puerta responde 403 a todo. Los mismos tokens entran a `GEPP_API_TOKENS` de la API (se suman a `DEMO_TOKEN`). El correo debe existir como usuario en la base **tal como está en la tabla `usuario`, en minúsculas** (el script lo pasa a minúsculas en nginx y en la API: la API busca el correo exacto). Ningún token puede ser `DEMO_TOKEN`. La lista mal formada (comillas, `$`, espacios, saltos de línea u otros caracteres de control, repetidos) **impide arrancar** `web` y `api` |

## Dos puertas (nginx)

| Puerta | Dónde | Quién entra |
|---|---|---|
| Local `127.0.0.1:18080` | proyector del portátil | cualquiera con acceso al portátil; la API recibe el token del bundle (`DEMO_TOKEN`) |
| Tailnet `127.0.0.1:18081` | `tailscale serve` | solo quien llegue con `Tailscale-User-Login` de `DEMO_IDENTIDADES`: otra cosa → **403 en todo** (web y `/api/`). La API recibe el token **de esa persona**, que pisa al del navegador; la cabecera de identidad no sigue hacia la API |

Son dos `server` separados a propósito: Tailscale Serve no pone la cabecera a los dispositivos con
etiqueta, y no puede existir una puerta en la que su falta deje pasar con el token del bundle. Lo corre
Edgar, no los scripts (no se tocó Tailscale):

```
! tailscale serve --bg --https=8443 http://127.0.0.1:18081     # deshacer: ! tailscale serve reset
export DEMO_IDENTIDADES="<correo-1>=$(openssl rand -hex 16),<correo-2>=$(openssl rand -hex 16)"
```

Límites: la cabecera es de confianza solo porque 18081 está en loopback; cualquier proceso local del
portátil podría escribirla. Los dispositivos con etiqueta no reciben la cabecera (403, a propósito).

## Levantar

```bash
export DEMO_PG_PASSWORD=$(openssl rand -hex 12) DEMO_TOKEN=$(openssl rand -hex 16)
export MODELO_PTH=/ruta/al/checkpoint.pth MODELO_CLASES=/ruta/al/modelo.clases.json
docker compose -p gepp-demo -f despliegue/local/compose.yml up -d --build --wait
# panel: http://127.0.0.1:18080  (token = $DEMO_TOKEN en Authorization: Bearer)

# dejar el video de demo en la carpeta vigilada (el trabajador lo procesa solo):
docker run --rm -v gepp-demo_vigilada:/v -v "$VIDEO":/in.mp4:ro --entrypoint cp gepp-api:demo /in.mp4 /v/demo.mp4

# sin GPU: --profile cpu y SOLO el trabajador-cpu. Si la GPU ya estaba arriba, detenerla antes:
# los dos trabajadores comparten la cola y el segundo vacía el anillo de la vista al arrancar.
docker compose -p gepp-demo -f despliegue/local/compose.yml stop trabajador
docker compose -p gepp-demo -f despliegue/local/compose.yml --profile cpu up -d --build \
  postgres redis preparar permisos api web despachador trabajador-cpu

# para volver a la GPU: detener antes el trabajador-cpu, por la misma razón
docker compose -p gepp-demo -f despliegue/local/compose.yml --profile cpu stop trabajador-cpu

# al terminar (con --profile cpu, para que también baje el trabajador-cpu y sus volúmenes):
docker compose -p gepp-demo -f despliegue/local/compose.yml --profile cpu down -v
```

Redis es la 7.2 (licencia BSD; la 7.4 es RSALv2/SSPL, ADR-002). Si alguna vez se levantó este proyecto
con otra versión de Redis, bajar antes con `down -v`: la 7.2 no lee el archivo de la 7.4.

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
