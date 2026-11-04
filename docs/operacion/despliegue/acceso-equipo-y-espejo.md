# Guía: Miguel ve la demo desde su equipo, con su celular como cámara y el espejo en la página

**Estado:** guía con decisiones tomadas, 2026-11-03. Los comandos con `!` los corre Edgar; ninguno
se ejecutó al escribir esto (ni Docker ni Tailscale). Los marcadores `<…>` y `${…}` (equipo,
tailnet, IP, correo, token) **no se rellenan en el repositorio**. Se apoya en
[`spec-en-vivo.md`](spec-en-vivo.md) y en
[`02-privacidad-y-cumplimiento.md`](../../producto/02-privacidad-y-cumplimiento.md); las
condiciones de privacidad (vista en vivo, excepción del celular) viven allí y esta guía no las
reemplaza.

## Decisiones (aprobadas por Edgar el 2026-11-03)

| # | Decisión | Qué se hace |
|---|---|---|
| E1 | La tailnet del equipo cuenta como «infraestructura controlada» (condición 7) | Con condiciones escritas en `02-privacidad`: integrantes nombrados, ACL que limite quién llega al portátil, solo material de demostración, dispositivos propios sin compartir ni etiquetar |
| E2 | Rol de Miguel: `auditor` | Ve hallazgos, evidencia y la vista en vivo; no tria ni procesa. Se cambia **solo en la base de la demo** (paso 3) |
| E3 | Token por persona en nginx, no en el JS | `DEMO_IDENTIDADES` + cabecera de identidad de Tailscale |
| E4 | Celular de Miguel como cámara | Con autorización escrita y solo para un integrante nombrado |
| E5 | Espejo de la cámara en la página | `/espejo/` en el nginx, con la clave de MediaMTX que el navegador no ve |
| E6 | Pantalla «Sala en vivo» antes de los KPI | Sin tocar el contrato; ver «La pantalla» abajo |

## Cómo queda armado

| Pieza | Dónde escucha | Quién llega |
|---|---|---|
| nginx de la tailnet (web, `/api/`, `/espejo/`) | `127.0.0.1:18081` → `tailscale serve --https=8443` | Los de `DEMO_IDENTIDADES`; los demás, 403 |
| nginx del proyector | `127.0.0.1:18080` | Solo el portátil. **No se publica en Tailscale** |
| Publicar desde el celular (MediaMTX) | `127.0.0.1:18889` → `tailscale serve --https=443` | Quien tenga usuario `publicador` y `CAMARA_CLAVE` |
| Medios WebRTC (UDP/TCP) | `${TS_IP}:18189` y `127.0.0.1:18189` | La tailnet y el navegador del portátil, tras una señalización autenticada |

No se usa `tailscale funnel` (abre a internet). `serve` solo admite destinos en `127.0.0.1`.
Requisito de una vez: activar «HTTPS Certificates» en la consola de Tailscale.

## Pasos de Miguel, en orden

### 1. Autorización escrita

Antes de encender nada: Miguel y **quien aparezca frente a la cámara** firman la autorización de la
excepción del celular (finalidad, responsable, quién ve, qué queda, cómo retirarse; un aviso verbal
no basta; ver `despliegue/celular/README.md` del #254). Sin ella, plan B: un video ya autorizado
(`07-datasets.md`) por el mismo camino. Las condiciones de E1, E4 y E5 están en `02-privacidad`,
sección «Acceso de integrantes por la tailnet y espejo de la cámara».

### 2. Tailscale en su equipo y en su teléfono

Miguel instala Tailscale en su equipo **y** en su teléfono, entra con su cuenta y los deja
conectados. Edgar confirma en la consola de Tailscale (condiciones de E1):

- Dispositivos **propios de Miguel**, sin etiqueta (`tagged`: Tailscale no pone la cabecera de
  identidad en esos) y **sin compartir** con nadie ajeno al equipo.
- La ACL limita a Miguel y a Edgar el acceso al portátil (puertos 8443 y 443, y `18189` de su IP).

### 3. Qué le pide a Edgar

Miguel le entrega **el correo con que entra a Tailscale** (su «login»). Edgar hace tres cosas.

**a) Una identidad con token propio** (el token no va a ningún archivo ni al chat):

```
! export DEMO_IDENTIDADES="<correo-de-miguel>=$(openssl rand -hex 16)"   # más: ",otro-correo=otro-token"
```

Los mismos tokens entran solos a la API (`GEPP_API_TOKENS="token=correo"`): para la API el correo
**es** el login de Tailscale, así que debe existir en la tabla `usuario`. Sin cabecera, o con un
login que no está en la lista, el nginx responde **403** (probado, abajo). Edgar levanta la demo con
el override de la puerta (S1) y los de la cámara, con `CAMARA_CLAVE` y `ESPEJO_CLAVE` definidas.

**b) El rol `auditor`.** La semilla (`perfiles/construccion.yaml`, comprobada en `origin/main`) ya
trae a Miguel con su correo de la universidad como **`administrador`**, que **no** tiene
`ver_evidencia` (403 en la vista en vivo). Se cambia solo en la base de la demo (servicio
`postgres`, usuario y base `gepp`, tabla `usuario`):

```
! C="docker compose -p gepp-demo -f despliegue/local/compose.yml -f despliegue/celular/compose.yml"
! $C exec postgres psql -U gepp -d gepp -c "UPDATE usuario SET rol='auditor' WHERE email='<correo-de-miguel>' RETURNING email, rol;"
```

Debe mostrar una fila con `auditor` y `UPDATE 1`. Con `UPDATE 0` no existe ese correo (por ejemplo,
su login de Tailscale no es el de la semilla): se crea con el mismo correo de `DEMO_IDENTIDADES`:

```
! $C exec postgres psql -U gepp -d gepp -c "INSERT INTO usuario (email, nombre, rol) VALUES ('<correo-de-miguel>', 'Miguel', 'auditor');"
```

El rol se lee en cada petición: no hace falta reiniciar la API. **Se repite** después de
`rearmar-demo` o de `down -v`, que recrean la base: la semilla vuelve a dejar `administrador`.
Mientras no se repita, Miguel no ve ni la vista en vivo ni el espejo: el nginx pregunta a la API
por `ver_evidencia` antes de entregar el espejo (S1).

**c) Publicar las dos puertas** (`! tailscale serve status` debe listar solo estas dos):

```
! tailscale serve --bg --https=8443 http://127.0.0.1:18081
! tailscale serve --bg --https=443  http://127.0.0.1:18889
```

Se deshace con `! tailscale serve reset`.

### 4. Abrir la demo

Con Tailscale conectado en su equipo: `https://<portátil>.<tailnet>.ts.net:8443`. Entra sin
escribir token (el nginx pone el suyo según la cabecera) y ve la web con el rol `auditor`, sin
botones de triage ni de procesar. Si ve 403: su login no está en `DEMO_IDENTIDADES`. Si la API da
401: ese correo no existe en `usuario`.

### 5. Publicar desde el celular, en H264

Con la demo levantada por Edgar con `TS_IP=$(tailscale ip -4)` (sin ella el teléfono no conecta):

1. En el teléfono, con Tailscale conectado: `https://<portátil>.<tailnet>.ts.net/camara/publish`.
2. Usuario `publicador` (el iPhone pone la primera letra en mayúscula: corrígela) y la clave
   `CAMARA_CLAVE`, **pegada**, que Edgar le pasa por un canal privado. Ábrelo en una **pestaña
   privada** de Safari: si el usuario se escribe mal una vez, Safari lo guarda y ya no vuelve a
   preguntar (pasó en el ensayo del 2026-11-04).
3. Códec **H264** (con AV1 el trabajador no decodifica y el PR 7 deja ese video en `error`).
4. **«audio device»: `none`.** La página de MediaMTX elige el primer micrófono por defecto, y
   elegir H264 no lo apaga. Sin este paso, el trozo graba audio de la sala.
5. «publish» y permitir solo la cámara. **Pantalla encendida y Safari en primer plano**: iOS corta
   la cámara si se cambia de app o se bloquea el teléfono.

### 6. Ver la Sala en vivo

En su equipo, la pantalla «Sala en vivo» (S2, Teddy) le muestra el espejo de la cámara, la vista
procesada y los hallazgos recientes; el espejo entra por `/espejo/camara/whep`. El hallazgo aparece
≈ 8 a 11 s después de la imagen (trozos de 5 s con GPU, spec §5).

### 7. Cerrar y comprobar el borrado

1. Miguel detiene la publicación en el teléfono.
2. Edgar espera **más de 2 minutos** (tope nominal de borrado: 110 s, README del celular) y mira
   que no quede video de la cámara:
   `! docker run --rm -v gepp-demo_vigilada:/v --entrypoint ls gepp-api:demo -la /v /v/en-curso`
3. `! $C --profile cpu down -v`, y `! docker volume ls | grep gepp-demo` sin salida.
4. `! tailscale serve reset`. Los tokens de `DEMO_IDENTIDADES` se descartan: uno nuevo por demo.
5. Si Miguel quiere retirarse, Edgar borra lo suyo en ese momento (autorización del paso 1).

## La pantalla

«Sala en vivo» (S2, Teddy) es donde Miguel verá el espejo, la vista procesada y los hallazgos; la
interfaz no se detalla aquí. Rótulos obligatorios: «Cámara en vivo» y «Vista procesada (≈ 10 s de
retraso)», para que nadie crea que ambas muestran el mismo instante.

## Evidencia (lo medido; sin Tailscale real ni teléfono)

**Identidad por persona en nginx** (API `gepp-api:proto`, nginx:alpine con la plantilla, correos
`.invalid`, cabecera enviada a mano):

| Entrada | Resultado |
|---|---|
| Sin `Tailscale-User-Login` | 403 |
| Login desconocido | 403 |
| Login de la persona A + `Authorization: Bearer demo` (el relleno del bundle) | 200, `rol: auditor`, permisos `ver_hallazgos, ver_evidencia, ver_reportes, ver_auditoria` |
| Login de la persona B | 200, `rol: prevencionista` |

**Roles contra la API:** `administrador` recibe `403 El rol administrador no tiene el permiso
ver_evidencia` en `/videos/1/vivo`; `auditor` pasa ese permiso y en `POST /videos` recibe
`403 … procesar_videos`. El triage en lote del auditor sale de `PERMISOS` en `auth.py`, no de una
ejecución.

**MediaMTX v1.21.3, usuarios internos** (`publicador` solo publica, `lector` solo lee): publicar con
clave equivocada, sin credenciales o con `lector` → 401 las tres; leer por RTSP o por la página
WebRTC sin credenciales, con clave equivocada o con el usuario que solo publica → 401;
`POST /camara/whep` sin credenciales → 401; con `lector` → 200 y el video se reproduce.

**Latencia del espejo crudo** (ffmpeg con el reloj dibujado, VP8, mismo equipo, Chromium headless;
error ± 0,3 s): ≈ 0,13 s y ≈ 0,15 s en dos capturas. El hallazgo procesado tarda 7,5 a 10,7 s: el
espejo es unas 50 a 70 veces más rápido.

## Privacidad del espejo (resumen; el texto vigente está en `02-privacidad`)

Es video **crudo y nítido**: solo roles con `ver_evidencia` (por eso `auditor` y no
`administrador`), solo dentro de la tailnet de E1, sin grabar (WebRTC en vivo; lo único que se
guarda son los trozos en memoria del paso 7), sin audio, apagado salvo que la demo se arme con
cámara, y con aviso a quien se pare frente a ella. La clave de `lector` (`ESPEJO_CLAVE`) vive solo
en el entorno del nginx: quien la conozca ve el video sin pasar por `ver_evidencia`.

## Ensayo real (2026-11-04, Edgar y Miguel)

Con el iPhone de Miguel por la tailnet: 25 trozos procesados con la GPU y 23 hallazgos. Miguel vio
cada hallazgo en la Sala en vivo **unos 4 a 5 s** después de pararse sin casco (medido a ojo). Al
cerrar quedaban 0 trozos. Lo que dejó:

- El espejo no conectaba en el navegador del portátil: MediaMTX anunciaba solo la IP de Tailscale.
  Corregido: también se anuncia y se publica `127.0.0.1` (comprobado en Chrome de Windows con el
  video de respaldo).
- El iPhone llegó por un relé de Tailscale (DERP) y perdió paquetes. La grabación se recuperó sola.
  En la sala, con el teléfono y el portátil en la misma red, debería conectar directo: **comprobarlo
  antes de presentar**.
- Telegram no se probó en este ensayo.

## Lo que no pude comprobar

- Nada con Tailscale real: ni `serve`, ni la cabecera llegando al nginx, ni una ACL sobre `18189`.
  El nginx debe escuchar solo en `127.0.0.1`: si alguien llegara al puerto directo podría escribir
  la cabecera (condición de la documentación de Tailscale).
- Los nombres de S1 (puerta `18081`, `DEMO_IDENTIDADES`, `/espejo/`, usuario `lector`,
  `ESPEJO_CLAVE`): salen del encargo del capitán, no de un PR. Hoy `mediamtx.yml` del #254 solo trae
  `publicador`. Contrastar con el PR de S1 cuando exista.
- Los `psql` (no corrí Docker): `UPDATE` e `INSERT` salen de `modelos.py` (tabla `usuario`, columnas
  `email, nombre, rol`, `activo` verdadero por defecto) y del compose del #246 (`postgres`, `gepp`).
- Un teléfono real, H264 en el espejo, la ruta de medios por la tailnet (directa o con relé) y la
  latencia con red real. El Chromium de Playwright no decodifica H264: el espejo se midió con VP8.
- `ips:` en `authInternalUsers` para limitar `lector` a la red del nginx, y el `proxy_pass` a WHEP
  desde el nginx junto con la identidad (probé las dos partes por separado).
- Qué puertos admite `tailscale serve` más allá de 443 y 8443.
