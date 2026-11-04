# El celular como cámara en vivo — prueba corta

Estado: **probado en local, sin celular real**; nada de GCP. 2026-11-02/03. Se suma al compose de la demo
local (`despliegue/local/`, PR 1) con `despliegue/celular/compose.yml`; comandos en `despliegue/celular/README.md`.

## 1. Lo que se hizo y por qué no es un `RtspFrameSource`

El encargo pedía una fuente RTSP en el trabajador. **Se paró** por dos bloqueantes (§7) y, con el
visto bueno de Nikola Tesla, se probó otra vía que no toca `gepp-worker` ni `test_reloj.py`:
MediaMTX graba la cámara en **segmentos MP4 cortos** y el vigilante, que ya existe, los procesa
como archivos.

```
celular (navegador, WHIP/WebRTC H264) ─▶ MediaMTX ─▶ RTSP :8554 (re-servido)
                                            │ graba (tmpfs)  en-curso/…mp4
                                            ▼ al cerrar el segmento: mv atómico
                              /grabaciones (= la vigilada) ─▶ vigilante ─▶ Redis ─▶ trabajador (GPU/CPU)
                                       ▲                                        │ hallazgo+evidencia
                                  borrador (borra al quedar listo/error)       ▼ (+ vista en vivo, en memoria)
                                                                       PostgreSQL ─▶ API ─▶ web (nginx)
```

## 2. Qué se comprobó (comando → salida)

| # | Prueba | Resultado |
|---|---|---|
| 1 | MediaMTX v1.21.3 (`bluenviron/mediamtx:latest-ffmpeg`) acepta RTSP de ffmpeg | `[path camara] stream is available and online, 1 track (H264)`; segmentos en `/grabaciones` |
| 2 | Acepta WHIP/WebRTC desde Chromium headless (`publicar_headless.mjs`, `--use-fake-device-for-media-stream`) | `[WebRTC] peer connection established … is publishing to path 'camara'`, `recording 2 tracks (Opus, H264)` |
| 3 | …y lo re-sirve por RTSP | `ffprobe rtsp://mediamtx:8554/camara` → `opus,0/0` y `h264,640,480,20/1` |
| 4 | Contexto seguro | Chromium en `http://mediamtx:8889` (no localhost): `secure_context=false`, la página dice «can't access webcams or microphones. Make sure that WebRTC encryption is enabled.» En `http://localhost:8889`: `secure_context=true`. **Por eso el celular necesita HTTPS** |
| 5 | Punta a punta con ffmpeg (video de demo, una pasada) | 10 s en GPU: 14 hallazgos; 5 s: 18. Evidencia por nginx `GET /api/v1/evidencias/{1,8,17}` → `200 image/jpeg` (volumen compartido y mismo usuario 1000) |
| 6 | Vista en vivo (local, condición 7) mientras un segmento está `procesando` | `GET :18080/api/v1/videos/11/vivo` → `200 image/jpeg 122899` (3 de 3 intentos) |
| 7 | Borrado | Con el trabajador vivo: cada segmento se borra al quedar `listo` (los 5 videos, tmpfs vacío al final). Con el trabajador CAÍDO y TTL 20 s: `borrado … vencido (20 s)`; `notas.txt` y `ajeno.mp4` (nombre ajeno) **se dejan** y se avisa: `no reconozco notas.txt: se deja` |

Fuentes MediaMTX: `mediamtx.yml` v1.21.3 en GitHub (<https://raw.githubusercontent.com/bluenviron/mediamtx/v1.21.3/mediamtx.yml>,
consultado 2026-11-02; mediamtx.org no respondió desde esta red). De ahí: `webrtc`, `webrtcAddress :8889`,
`recordPath`, `recordFormat fmp4`, `recordSegmentDuration` («Minimum duration of each segment»),
`recordDeleteAfter`, `runOnRecordSegmentComplete`, `webrtcAdditionalHosts`.

## 3. Mediciones (este portátil, RTX 4070 Laptop libre al empezar: 226 MiB, 0 %)

Video de demo 47,6 s (720×1280, 25 fps), re-codificado por ffmpeg con un cuadro clave por segundo y
sin B-frames (como un celular), una pasada. Modelo `rfdetr-s-epp-v3`, cámara 2 del perfil construcción,
5 cuadros/s analizados. «Latencia» = `hallazgo.creado_en − hallazgo.ts_inicio` (desde que la persona
queda sin EPP en el video hasta la fila en la base); incluye los 2 s de confirmación.

| Segmento | Motor | Vista en vivo | Hallazgos | Σ duración | fps (cuadros / proceso_ms) | Latencia |
|---|---|---|---|---|---|---|
| 60 s (= 1 segmento, la referencia) | GPU | no | 11 | 89,4 s | 24,7 | 19–61 s (espera todo el video) |
| 10 s | GPU | no | 14 | 80,4 s | 19,2 | 9,4–17,1 s |
| 10 s | GPU | **sí** | 14 | 80,4 s | 12,5 | 10,7–18,2 s |
| 5 s | GPU | no | 18 | 69,4 s | 17,7 | 6,9–9,8 s |
| 5 s | GPU | **sí** | 18 | 69,4 s | 11,3 | 7,5–10,7 s |
| 5 s | CPU, `--cpus 4` | no | 18 | 69,4 s | **3,33** | 15,3–34,1 s, **y crece** |
| 10 s | CPU, `--cpus 4` | no | 14 | 80,4 s | 1,5–2,9 por segmento | 42–90 s, **crece** (carga del equipo ~8-12) |

Desglose de un segmento de 10 s en GPU (video 2 de la corrida con vista): cierra a 55:39,3 → registrado
(hook + 2 sondeos del vigilante + hash) 55:42 → `proceso_ms` 3,4 s → hallazgo en la base ~55:46.
**≈ 6,7 s tras el cierre del segmento, más hasta 10 s de espera del propio segmento, más 2 s de
confirmación: 11–18 s.** Con 5 s: 7–11 s. Los «10-15 s» que se supuso al principio no valían para
los 10 s con vista (18,2 s medidos).

**CPU no alcanza.** Con 4 CPU el modelo analiza 3,3 cuadros/s y la fuente entrega 5: la cola crece
(latencia 15 → 34 s en 47 s de video) y nunca se recupera. Las corridas de CPU se hicieron con el
equipo cargado por otras sesiones (load 4–12); el orden de magnitud es el que importa.

## 4. Efecto del corte en las reglas (medido)

Cada segmento es un «video»: seguidor, agregador y confirmación nacen de cero (`trabajador.py:490`
crea el muestreador; el pipeline se arma en `_analizar`, `:445-:520`).

| Referencia vs segmentos | Hallazgos | Σ duración | Lectura |
|---|---|---|---|
| 1 segmento (47,6 s) | 11 | 89,4 s | la verdad |
| 10 s | 14 (+3) | 80,4 s (−9,0 s, −10 %) | un incumplimiento que cruza el borde **se parte en dos** hallazgos con `track_id` distintos (ids 5-7 acaban a las 55:49,1 y 8-10 empiezan a las 55:49,3) |
| 5 s | 18 (+7) | 69,4 s (−20,0 s, −22 %) | más partidos y **tiempo perdido**: nada se alarma hasta acumular 2 s dentro de un mismo segmento |

- **Se parte, no desaparece, si cada lado llega a 2 s** (`confirmacion_segundos: 2.0`,
  `perfiles/construccion.yaml:74,84`). **Se pierde** si cada lado queda bajo 2 s: un incumplimiento
  de 3 s repartido 1,5 + 1,5 s no confirma ninguna regla. Esto se deduce de la regla y de la pérdida
  medida (−9 y −20 s); no armé un video que lo provoque a propósito.
- **Una regla de más de ~120 s (ADR-008) no puede dispararse nunca**: el máximo observable por
  hallazgo es el largo del segmento (10 s ⇒ 9,8 s medidos). Teddy mide qué alertas salen en la demo;
  este dato es el tope.
- El reincidente y los resúmenes por turno cuentan hallazgos partidos como varios: inflan la cuenta.

## 5. Privacidad (excepción D4 de `02-privacidad-y-cumplimiento.md`, «cámara de demostración en la sala»)

Esta cámara **no se usa** sin la autorización escrita de cada persona que se pare frente a ella y sin leerle el
aviso completo (condición 2). Lo de abajo es lo técnico; no lo reemplaza.

**Autorización y aviso (condición 2).** Antes de ponerse frente a la cámara, quien participa **firma** una
autorización breve. Se le dice: **finalidad** solo académica (la presentación del capstone); **responsable**
Edgar Tolentino, a quien se pide todo; **quién ve**: el proyector y la vista en vivo muestran su cara **nítida** a
los asistentes mientras dura la demo, y el video crudo lo ven solo el proyector y los integrantes nombrados por el
espejo, sin grabarse; **qué queda**: hallazgos y recortes con
el rostro difuminado en la base de la demo, que se borran con `rearmar-demo` y al terminar; y **cómo retirarse**:
avisa a Edgar y se borra lo suyo en ese momento. Un aviso verbal no basta.

**Dónde vive el video (condición 3).** Los segmentos están solo en el volumen **tmpfs** `vigilada` (memoria):
`en-curso/` mientras MediaMTX los graba y, al cerrarse, el hook los mueve a la raíz, que es la carpeta vigilada.
Nada toca disco persistente. `down -v` o un reinicio vacían el volumen.

**Borrado aunque algo falle (condición 4).** El `borrador` (`despliegue/celular/borrador.py`) hace dos pasos por
barrido (cada 2 s), **en este orden**:
1. **Vencimiento, sin base.** Borra todo segmento con más de `TTL_SEGMENTO_S` (60 s). No consulta nada.
2. **Terminados.** Para lo que no venció, busca su video por SHA-256 con `gepp_bd.repositorios.videos.por_hash`
   (sin SQL propio, ADR-012) y borra si está `listo` o `error`. Esta consulta tiene un **límite duro** de 3 s en un
   hilo aparte (más `PGCONNECT_TIMEOUT=3` y `statement_timeout=3000` en el servidor): una consulta trabada se
   abandona y no detiene nada; no se lanza otra mientras la anterior siga colgada.

**El atraso es descarte.** Un segmento que vence sin procesarse **se borra igual**. No hay que subir el TTL «por si
la cola va atrasada»: con la cola atrasada se pierden segmentos, y es lo que dice la condición 4. Con la GPU, del
cierre del segmento a `listo` pasan ~7 s (medido); con CPU la cola no da abasto, por eso la cámara usa la GPU.

**La cámara no arranca sin quien borra.** `mediamtx` depende de que el `borrador` esté arriba, y el `borrador` NO
depende de PostgreSQL ni de `preparar`: si la base falla al arrancar, igual se aplica el TTL.

### Tope de video que existe a la vez (condición 5) — nominal, NO una garantía

| Tramo | Valor | De dónde |
|---|---|---|
| Segmento abierto en `en-curso/` (graba) | ≥ 5 s: el corte espera al siguiente cuadro clave | `recordSegmentDuration` (un mínimo) |
| Un segmento que el hook no movió | `recordDeleteAfter` 30 s + hasta ~15 s hasta que MediaMTX limpia = ~45 s | `mediamtx.yml`; la limpieza se midió: un archivo viejo en `en-curso` desapareció a los 6, 7, 8 y 13 s |
| En la carpeta vigilada | `TTL_SEGMENTO_S` 60 s + barrido 2 s + presupuesto de consultas 3 s = 65 s | `compose.yml`, `borrador.py` |
| **Tope nominal declarado** | 30 + 15 + 60 + 2 + 3 = **110 s** | suma conservadora de las dos esperas más el TTL; en el camino normal, ~67 s |

No es una garantía: un segmento abierto **sin cuadro clave** podría durar más de los 5 s pedidos (con la cámara de
prueba salieron de 5,0 a 6,1 s; con un celular real no está medido: PLAUSIBLE); el reloj del vencimiento es la fecha
de modificación del archivo; y tmpfs puede ir a swap (los segmentos no están pixelados).

**El borrador se sabe sano.** Escribe un latido (`/tmp/latido`) en cada barrido y su `healthcheck` mira que tenga
menos de 15 s. `mediamtx` y los trabajadores dependen de `borrador: service_healthy`: con un TTL inválido
(`TTL_SEGMENTO_S=0`) el borrador cae (`ValueError: TTL inválido`, 7 reinicios en 12 s), `up -d mediamtx` sale con
código 1 («dependency failed to start: container … is unhealthy») y **MediaMTX no se crea ni arranca**. Si el bucle
se cuelga con MediaMTX ya grabando, Docker lo marca `unhealthy` pero no lo reinicia ni detiene la grabación: ese
caso no está cubierto (el latido solo gobierna el arranque).

**Presupuesto total de consultas.** El paso 2 tiene 3 s para TODO el barrido (cada consulta, además, tope de 3 s y
solo lo que quede del presupuesto) y el vencimiento se reevalúa con la hora de ahora antes de cada consulta y al
final: antes, 4 consultas de 0,8 s tardaban 3,2 s y dejaban archivos de 63 s con TTL 60 (simulado por Codex).

**Probado (compose real, TTL 20 s para acortar):** con el trabajador **y PostgreSQL detenidos**: 11 segmentos
borrados por vencimiento, a los 20–24 s, y al final solo queda `en-curso/`; con PostgreSQL **trabado**
(`docker pause`: la conexión sigue viva y no responde): 10 segmentos más, también a los 22–24 s; con la base
caída al arrancar (`up -d mediamtx`: sube el borrador y luego MediaMTX, sin PostgreSQL). `restart: unless-stopped`:
con un fallo de proceso (TTL inválido a propósito) reinicia (`reinicios=7`); `docker kill` no lo reinicia (Docker
lo trata como parada manual). **Un TTL inválido no borra nada**: el proceso cae a la vista; se prefiere fallar fuerte.

**Nombre reconocido.** Solo `camara-AAAA-MM-DD_HH-MM-SS-micros.mp4` con una fecha real; `respaldo-2026-13-99_…`,
el 30 de febrero, la hora 24 y los `.part` se dejan y se avisa una vez (`GEPP_RUTA_CAMARA` cambia el prefijo).

**Tests** (`tests/test_borrador_celular.py`, 42): TTL justo en 60 s (no vence), a cada lado (59,75 y 60,25) y TTL
inválido (0, −1, NaN, ∞); el vencimiento ocurre **antes** de la consulta; una consulta trabada no detiene los
borrados; presupuesto total (6 consultas de 0,8 s se detienen tras 4) y cada consulta usa lo que queda; lo que
vence durante las consultas se borra en el mismo barrido y no gasta una consulta; no se apilan hilos; fechas
imposibles y otra ruta. 15 defectos inyectados (`>`→`>=`, sin vencimiento previo, sin límite duro, sin cortar el
paso 2, sin validar fechas, cualquier prefijo, TTL sin validar, no borrar listo/error, apilar consultas, no
ignorar `en-curso`, límite por archivo, ignorar lo que queda del presupuesto, sin reevaluar antes de cada
consulta, sin reevaluar al final, hora del inicio): cada uno hace caer al menos un test.

### Quién puede publicar o leer (MediaMTX, `authInternalUsers`)

`mediamtx.yml` quita el usuario anónimo que trae MediaMTX y deja **un solo usuario**, `publicador`, que **solo
publica en la ruta `camara`**; no hay usuario que lea. La clave entra por `CAMARA_CLAVE` →
`MTX_AUTHINTERNALUSERS_0_PASS` (obligatoria y no vacía en el compose: probado que **con la clave vacía MediaMTX acepta
al usuario sin contraseña**). RTSP (8554) **no se publica al host**: el plan B entra por la red interna de compose.
Probado: publicar por RTSP sin credenciales, con clave mala y en otra ruta (`/otra`) → ffmpeg sale con error (1);
con la clave y en `camara` → entra; leer `camara` por RTSP sin credenciales y con la del publicador → `401`;
página `/camara/publish` sin credenciales o con clave mala → `401`, con la correcta → `200`; WHEP con la clave
del publicador → `401`. En el celular, el navegador pide usuario y clave al abrir la página (`publicador` y la
clave). Los medios WebRTC (`${TS_IP}:18189`, y `127.0.0.1:18189` para el navegador del propio portátil) los alcanza quien esté en la tailnet, pero solo se establecen tras
una señalización autenticada. La ACL de la tailnet sobre ese puerto no se probó.

## 6. Hallazgos que cambian cómo se opera

1. **AV1 ⇒ video «listo» con 0 cuadros, sin error.** Chromium ofrece AV1, VP9, VP8, H264 y toma AV1
   por defecto; OpenCV del trabajador no lo decodifica (`Your platform doesn't support hardware
   accelerated AV1 decoding`) y los segmentos quedaron `listo` con `cuadros_analizados = 0`. **Fallo
   silencioso**: el panel mostraría «todo bien» sin haber mirado nada. En el celular hay que elegir
   **H264** en la página (el script de prueba lo hace). Que el trabajador falle fuerte con 0
   cuadros ya está en main (#243).
   **Y «audio device: none»:** la página elige el primer micrófono por defecto y el trozo graba
   audio (prueba 2: `recording 2 tracks (Opus, H264)`). El trabajador no lo usa y se borra con el
   trozo, pero la excepción pide que no se capte (`02-privacidad`, condición 6 del acceso por la tailnet).
2. **MediaMTX no usa shell** en los hooks: un `&&` llegó como argumento de `mkdir`. Se pide `/bin/sh -c '…'`;
   la imagen básica no trae ni `mv`: hace falta `latest-ffmpeg`.
3. **Volumen tmpfs de Docker**: se monta por contenedor y se destruye al salir el último, así que un
   `chown` desde un contenedor de inicio se pierde: el dueño va en la opción de montaje (`uid=1000`).
   La vista en vivo exige carpeta propia 0700 del mismo usuario que escribe, así que API y trabajador
   corren con el mismo uid.
4. **Segmento incompleto**: el vigilante solo mira tamaño/mtime (`vigilante.py:82`); una pausa del emisor
   podría hacer parecer estable un MP4 abierto. Por eso MediaMTX graba en `en-curso` y el hook mueve al
   cerrar (rename dentro del mismo tmpfs: atómico). No probé una pausa larga del emisor.
5. `webrtcLocalUDPAddress` se mantiene en 18189 dentro y fuera: ICE anuncia el puerto, remapearlo
   (8189→18189) rompería la conexión.

6. **El vigilante moría en silencio si el borrador le quitaba un archivo.** Entre `is_file()` y `stat()` (o entre
   la estabilidad y el hash) un `FileNotFoundError` salía de `Vigilante.correr`; el proceso padre
   (`__main__.py`) queda esperando al trabajador sin reiniciar el vigilante, y la ingesta moría sin ruido. Se arregló
   en un PR propio (`vigilante.py`: un archivo que desaparece a mitad de sondeo se salta; un fallo transitorio de E/S
   no mata el bucle; un defecto de código sigue cayendo). El padre sigue sin reiniciar un vigilante que muera por
   otra causa: no se tocó.

## 7. Camino a un `RtspFrameSource` real (decide Edgar)

**Bloqueante 1 — el reloj.** `tests/test_reloj.py:21` vigila `gepp-core`, `gepp-worker` y `gepp-vision` y
`:70` prohíbe `now/utcnow/today` (AST). Una fuente en vivo necesita la hora de recepción como `capture_ts`
(ADR-005 decisión 2 y `fuente.py:84`: «el llamador pasa el reloj de recepción como `inicio_captura`»), pero
el ADR no dice dónde se lee y todo `gepp-worker` está vigilado. Esquivarlo con `time.time()` +
`fromtimestamp` cumpliría el test y violaría su intención (regla 6). Opciones:

| Opción | Qué es | Costo |
|---|---|---|
| A | Excepción explícita y acotada en el test para `fuente_rtsp.py`, con su propio test del borde | Edgar enmienda ADR-005 y el test |
| B | Reloj inyectado desde fuera de los paquetes vigilados (p. ej. un módulo `gepp-vivo` o el `__main__`) | un paquete/módulo nuevo y su regla |
| C | Reloj de MediaMTX (`pts` + hora de la sesión RTSP/RTCP) sin leer el del sistema | depende de RTCP; más frágil |

**Bloqueante 2 — el trabajador es por archivo.** `trabajador.py:519` `procesar_todo(cuadros())` acumula
todo hasta el fin de la fuente; `:615` `_escribir_evidencias` **relee el archivo** para los recortes; `:533`
una sola `transaccion` escribe detecciones, hallazgos, evidencia y `listo` (`:560`). Una cámara no termina,
no hay archivo que releer y los hallazgos nunca llegarían. Hace falta pipeline incremental, evidencia desde
memoria, hallazgos cerrados escritos al vuelo y una fila `video` de duración abierta: bastante más de
400 líneas y toca los reintentos (#29). Esquema y contrato alcanzan (`fuente.uri`, `tipo='rtsp'`).

## 8. Riesgos

| Riesgo | Detalle |
|---|---|
| **Teléfono de un profesor fuera del tailnet** | `tailscale serve` da HTTPS solo dentro del tailnet y los medios WebRTC van por UDP/TCP a `${TS_IP}:18189` (la IP de Tailscale del portátil): un teléfono sin Tailscale no llega. Con Funnel solo pasaría el HTTP, no los medios. Para teléfonos ajenos haría falta una IP pública/TURN: **no probado** y expone el portátil |
| Red de la sala | WebRTC sobre UDP por Tailscale puede ir por relevo (DERP) y subir la latencia; sin pruebas con teléfono |
| HTTPS certificates | `tailscale status --json` dio `CertDomains: null`: probablemente hay que activarlos en la consola |
| Batería/pantalla | La página debe quedar abierta y el teléfono despierto; no medido |
| GPU vs vista en vivo | Con la vista encendida el trabajador cae de ~19 a ~12 fps (sigue sobre los 5 que entran) |
| CPU | No sostiene 5 cuadros/s (3,3): usar `GEPP_FPS_OBJETIVO` 2 o la GPU |
| Cámara real | El celular no manda cuadro clave cada 1 s; el segmento será más largo que el pedido (mínimo, no máximo). Con la cámara de prueba, 5 s y 6,1 s |

## 9. Lo que no pude comprobar

- Un teléfono real, `tailscale serve` y los medios por la IP 100.x (no toqué Tailscale).
- Que el hook `mv` sobreviva a una pausa del emisor; el reloj de un segmento cuyo `creation_time` falte
  (se usó `mtime − duración`, origen `mtime`: coincidió con la hora real al décimo de segundo).
- Alertas de Telegram (sin token) y el acuse.
- Persona real sin casco ante la cámara (el video de demo hizo de cámara y Chromium de cámara falsa).
- Latencia de red del teléfono: las cifras son de red local.
