# El celular como cámara — comandos

Contexto, mediciones y riesgos: `docs/operacion/despliegue/celular-como-camara.md`. Esto se SUMA al compose de
la demo local (`despliegue/local/`): el orden de los `-f` importa (las rutas relativas salen de la carpeta del
primero). Desde `Fase 2/sistema` (ruta con espacio: entre comillas).

## Antes de usar la cámara (excepción D4, `02-privacidad-y-cumplimiento.md`)

Quien se pone frente a la cámara **firma antes una autorización por escrito** y se le lee el aviso completo:
**finalidad** solo académica (la presentación del capstone); **responsable** Edgar Tolentino, a quien se pide
todo; **quién ve**: el proyector y la vista en vivo muestran su cara **nítida** mientras dura la demo, y el video
crudo lo ven solo el proyector y los integrantes nombrados por el espejo, sin grabarse; **qué queda**: hallazgos y recortes con el rostro difuminado en la base de la demo, que se
borran con `rearmar-demo` y al terminar; **cómo retirarse**: avisa a Edgar y se borra lo suyo en ese momento. Un
aviso verbal no basta. Sin esto, plan B: un video ya autorizado (`07-datasets.md`) por el mismo camino.

## Tope de video que existe a la vez (nominal, no una garantía)

Los segmentos viven solo en memoria (tmpfs). **Tope declarado: 30 s (`recordDeleteAfter`) + 15 s (MediaMTX
limpia `en-curso` cada ~15 s; medido: 6–13 s en 4 pruebas) + 60 s (`TTL_SEGMENTO_S`) + 2 s (barrido del borrador)
+ 3 s (presupuesto TOTAL de consultas a la base por barrido) = 110 s**; en el camino normal, ~67 s. El
presupuesto de 3 s es de TODO el barrido (no por archivo) y el vencimiento se reevalúa antes de cada consulta y al
final, así que una base lenta no alarga el tope más que eso. No es una garantía: un segmento abierto sin cuadro
clave puede durar más de los 5 s pedidos (no medido con un celular real) y tmpfs puede ir a swap. **El atraso es
descarte**: un segmento que vence sin procesarse se borra; no se sube el TTL por una cola atrasada. El borrado no
depende de PostgreSQL (probado con la base detenida y trabada).

## Levantar

```bash
export DEMO_PG_PASSWORD=$(openssl rand -hex 12) DEMO_TOKEN=$(openssl rand -hex 16)
export CAMARA_CLAVE=$(openssl rand -hex 12)    # clave de `publicador` (solo publica `camara`): obligatoria y no vacía
export ESPEJO_CLAVE=$(openssl rand -hex 12)    # clave de `lector` (solo lee `camara`): obligatoria; la usa nginx, no el navegador
export MODELO_PTH=... MODELO_CLASES=...        # ver despliegue/local/README.md
C="docker compose -p gepp-demo -f despliegue/local/compose.yml -f despliegue/celular/compose.yml"
TS_IP=<IP de Tailscale del portátil> SEGMENTO=5s $C up -d --build --wait
# plan B, sin celular: ffmpeg publica un video autorizado a la misma ruta (red interna, rtsp://mediamtx:8554/camara)
VIDEO=<ruta al video> BUCLE=0 $C --profile plan-b up -d captura     # BUCLE=-1 (defecto) repite sin fin
$C --profile plan-b down -v                    # al terminar
```

Servicios que agrega: `mediamtx`, `borrador`, `captura` (perfil `plan-b`, con el ffmpeg de la propia imagen de
MediaMTX: no depende de la imagen del trabajador); el override cambia el volumen `vigilada` a **tmpfs**. `mediamtx`
y los trabajadores esperan a que el `borrador` esté **sano** (su latido al día: con un TTL inválido el borrador cae y
MediaMTX NO arranca) y el `borrador` no espera a PostgreSQL. Si la demo ya estaba levantada sin cámara, `down -v` primero. Sin `TS_IP`, los medios WebRTC quedan en
loopback. **RTSP no se publica al host.**

## Espejo en la página (`/espejo/`)

nginx (`despliegue/local/`) publica `POST /espejo/camara/whep` (WHEP, `Content-Type: application/sdp`) hacia
MediaMTX en las dos puertas; en la de la tailnet solo para quien esté en `DEMO_IDENTIDADES`. nginx entra como
`lector`, que **solo lee `camara`** (restringido a redes privadas con `ips:`: rechaza IP públicas y de la
tailnet, pero NO aísla a nginx de otro contenedor ni de loopback, por eso la clave es obligatoria). El `Location`
del 201 vuelve como `/espejo/camara/whep/<id>` (relativo), y el `DELETE` de ese Location cierra la sesión.
**No se graba**: `record` es solo de los trozos del trabajador; HLS, RTMP y SRT siguen apagados. Sin este
override, `/espejo/` responde 503 «cámara apagada» y nginx arranca igual.

## Sin celular: Chromium headless con cámara falsa

`publicar_headless.mjs` abre `http://localhost:8889/camara/publish` con el usuario `publicador` y `CAMARA_CLAVE`,
elige H264 y pulsa «publish». Corre en un contenedor desechable que comparte la red de MediaMTX (así `localhost` es
contexto seguro); `playwright` se instala solo ahí:

```bash
docker run --rm -e CAMARA_CLAVE --network container:gepp-demo-mediamtx-1 \
  -v "$PWD/despliegue/celular/publicar_headless.mjs:/s/publicar_headless.mjs:ro" \
  --entrypoint bash mcr.microsoft.com/playwright:v1.62.1-noble -c \
  'mkdir -p /tmp/pw && cd /tmp/pw && npm init -y >/dev/null && npm i --silent playwright@1.62.1 \
   && cp /s/publicar_headless.mjs . && node publicar_headless.mjs http://localhost:8889/camara/publish 25'
```

## Con el teléfono (lo corre Edgar; los scripts no tocan Tailscale)

1. En la consola de Tailscale, activar **HTTPS Certificates** del tailnet.
2. Publicar la página por HTTPS dentro del tailnet (el celular exige contexto seguro para la cámara):
   `! tailscale serve --bg --https=443 http://127.0.0.1:18889` (se deshace con `! tailscale serve reset`).
3. Levantar con `TS_IP=$(tailscale ip -4)` como arriba: los puertos 18189 UDP/TCP se abren SOLO en esa IP.
4. En el teléfono (con la app de Tailscale en el mismo tailnet) abrir
   `https://<portátil>.<tailnet>.ts.net/camara/publish`. El navegador pide **usuario `publicador` y la clave**
   (`CAMARA_CLAVE`). Dejar el códec en **H264**, poner **«audio device: none»** (la página de MediaMTX v1.21.3 elige el primer
   micrófono por defecto y elegir H264 no lo apaga), «publish» y permitir la cámara. Ese URL es el QR (sin la clave).
5. Con la autorización firmada, pararse sin casco frente a la cámara; el hallazgo aparece a los ~8-11 s (5 s de
   segmento, GPU).

Un teléfono fuera del tailnet no llega a esa IP (ver «Riesgos» en el doc).
