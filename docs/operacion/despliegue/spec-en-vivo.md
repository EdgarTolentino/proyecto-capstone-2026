# Spec — Guardián EPP en vivo para la presentación

**Estado:** aprobada por Edgar el 2026-11-03, con todas las recomendaciones de la sección 6 · **Fecha:** 2026-11-02 ·
**Revisión externa:** Codex `gpt-6-astra` (max) pidió cambios a la primera versión. Esta versión
los incorpora; el detalle está en la sección 9.

Este documento junta lo que tres tripulantes investigaron, prototiparon y verificaron de forma
cruzada para dejar el sistema y la alerta funcionando en vivo. Las cifras salen de corridas en
copias del repo sobre `239f3fc` (main de ese momento). Lo que nadie comprobó está en la sección 7.

## 1. Qué buscamos

Frente a los profesores, alguien aparece sin casco ante una cámara. El hallazgo entra al panel,
el proyector muestra la vista en vivo con la falta en rojo y la alerta llega por Telegram al
celular de los profesores, que se suman a un grupo. Alguien toca «Acuso recibo» y el acuse queda
en la base. Un comando arma la demo y otro la deja lista para repetirla.

## 2. Recomendación: un solo sistema, en el portátil

Todo corre en el portátil de Edgar con un `docker compose`: PostgreSQL, Redis, el trabajador con
GPU, la API, la web, el despachador y MediaMTX. Hay **una sola base de datos**, así que lo que ven
el proyector y los celulares es el mismo evento.

| Quién | Qué ve | Cómo |
|---|---|---|
| Proyector | Panel, bandeja y vista en vivo con las cajas | Navegador del portátil. La vista en vivo está permitida porque el cliente está dentro de la infraestructura controlada (condición 7) |
| Celulares de los profesores | **La alerta de Telegram** con el botón «Acuso recibo» | Telegram. No se publica ninguna URL del panel |
| Cámara | El celular de un integrante nombrado (E4), o un video de respaldo | Navegador → MediaMTX (sección 5) |

**Por qué no hay panel público.** Un panel abierto a los celulares de los profesores choca con
tres cosas a la vez:
- **No hay rol que sirva.** El administrador no ve la evidencia y puede editar reglas; el
  prevencionista puede procesar videos y triar hallazgos (`auth.py:18-30`).
- **El token queda en el JS público.**
- **La condición 7.** Si se expone el nginx completo, se exponen también los endpoints `/vivo`.

La alerta de Telegram ya pone el evento en el celular de cada profesor sin abrir nada de eso.

**GCP queda opcional** (decisión D1): una VM con un respaldo independiente, rotulado como tal,
con datos del lote 2 (sintético, permitido para demostración en `07-datasets.md`). Sirve para
mostrar que el sistema también se despliega en la nube y como plan B si el portátil falla. **No**
muestra el evento de la sala.

## 3. Lo que se verificó

| Hallazgo | Quién → verificó | Evidencia |
|---|---|---|
| El compose en una máquina (opción C) procesa el video de demo y la API sirve la foto de un hallazgo | Capitán → Osito Gamer | `GET /api/v1/evidencias/1` → `200 image/jpeg 21908 B`. Según el informe de Osito Gamer, se comprobaron 3 de los 11 (`/1`, `/5`, `/11`); las salidas no quedaron guardadas. Base: 238 cuadros, 11 hallazgos, 1519 detecciones |
| Con API y trabajador en máquinas distintas, la evidencia no llega: `Evidencia.ruta` es una ruta del disco del trabajador | Osito → Lucca | `hallazgos.py:86-97`: sin montaje, `404 evidencia_purgada`; con el directorio montado en la misma ruta, `200` |
| Con 100 ms de latencia por sentido, el guardado final pasa de 3,93 s a 110,4 s. Cortes de 10 a 60 s no perdieron hallazgos | Lucca | Proxy TCP. Las detecciones van en lotes de 2000 (`detecciones.py:14`); los hallazgos y la evidencia, con operaciones por hallazgo |
| Los hallazgos se escriben al final de cada video, no durante el análisis | Lucca, Osito, Codex | `trabajador.py:526-570`. ADR-012 pedía transacciones por segundo de video: es una diferencia que main ya tenía, no la crea este despliegue |
| El trabajador solo lee archivos; no hay fuente RTSP | Lucca → Osito | `fuente_archivo.py:136`. La base ya admite `rtsp` (`modelos.py:56`) |
| ONNX corre en CPU: `__main__.py:108` no pasa `proveedores`, y la dependencia es `onnxruntime`, no la variante GPU | Lucca → Osito → Codex | `onnx.py:37`, `gepp-vision/pyproject.toml:11`. Usar la GPU con ONNX pide otra dependencia; la GPU de hoy es el `.pth` |
| FPS en el portátil (i9-14900HX, RTX 4070): CPU ONNX 2,93; GPU `.pth` 18,2; los mismos 11 hallazgos | Lucca | Video vertical de 47,6 s y perfil de la semilla. No dice nada del lote 3, que necesita mosaico |
| `make demo` (cámara 2, severidad 4) da **1** alerta inmediata. El `levantar.sh` local de Edgar usa la cámara 1 (severidad 3) y da **0** | Teddy; Codex corrigió a quién se atribuía | `demo.py:126` (`FUENTE_POR_DEFECTO = 2`); `levantar.sh:25` (`GEPP_FUENTE_ID=1`) |
| Después de una alerta, la misma cámara espera 30 min por destinatario; lo demás va al resumen. Un ensayo gasta esa alerta | Teddy → Codex | `politica.py:109` |
| El despachador muere si la base se corta, y un aviso deja de reintentarse después de 5 fallos | Lucca → Codex | `despachador.py:77-91`, `notificaciones.py:101` |
| La web no se refresca sola: solo el estado consulta cada 5 s | Codex → Capitán | `App.tsx:43`. La bandeja abierta no muestra el hallazgo nuevo sin recargar |
| Repetir la demo no es «reiniciar la base»: Redis recuerda los videos terminados y no los vuelve a encolar | Codex → Capitán | `cola.py:90` |
| El acuse por Telegram existe y se guarda; la web no lo muestra | Teddy | `acusar_por_token`. Mostrarlo pide un endpoint, y el contrato está congelado |
| El token queda en el JS; `/metrics` responde sin auth; CORS solo admite `localhost:5173` y `127.0.0.1:5173` | Osito → Lucca | `grep "Bearer"` en los assets; `config.py:93` |

## 4. Las opciones comparadas

| | **Portátil solo** (recomendada) | A · Híbrido | B · GCP con GPU | C · VM de CPU |
|---|---|---|---|---|
| Muestra el evento de la sala | **Sí** | Sí, con montaje y latencia | Sí | No (respaldo) |
| Vista en vivo | **Sí** | Solo local | No (condición 7) | No |
| Evidencia en el panel | **Sí** | Solo con un bucket montado en la misma ruta, no probado | Con el compose corregido | Sí |
| Velocidad | 18,2 fps | 18,2 fps; guardado lento | Sin medir en una L4 | ~1-3 fps |
| Costo | 0 | ≈ 2-4 USD por semana | ≈ 1,05 USD/h; la cuenta de prueba no da GPU | Sin verificar |
| Internet en la sala | Solo para Telegram | Todo | Todo | Para abrirla |

## 5. El celular como cámara

El navegador del celular publica por WebRTC (WHIP) a MediaMTX, sin app. Una fuente RTSP real
(`RtspFrameSource`, la «v2» de ADR-005) choca con la regla del reloj (`test_reloj.py:21,70`) y
con un trabajador hecho para archivos completos (`trabajador.py:519,533,615`). Va para después
(D6).

Para la demo, MediaMTX graba **trozos** en memoria (tmpfs). Cuando un trozo se cierra, un hook lo
mueve con un rename atómico a la carpeta vigilada, y el trabajador lo procesa como un video más.
Lo probó Osito Gamer en el portátil, sin celular real: ffmpeg y un Chromium con cámara falsa
hicieron de cámara.

**Mediciones** (RTX 4070 libre, video de demo de 47,6 s). La latencia va desde que la persona
aparece en el video (`ts_inicio` del hallazgo) hasta que se escribe (`creado_en`). Como
`creado_en` marca el inicio de la transacción y no su commit, la cifra no incluye lo que tarde el
guardado. Los 2 s de confirmación pasan dentro del trozo. Se midió con ffmpeg como emisor: no es
una cota para el teléfono.

| Trozo | Motor | Vista en vivo | Hallazgos | fps | Latencia |
|---|---|---|---|---|---|
| Un solo trozo (referencia) | GPU | no | 11 | 24,7 | 19-61 s |
| 10 s | GPU | sí | 14 | 12,5 | 10,7-18,2 s |
| **5 s** | **GPU** | **sí** | **18** | **11,3** | **7,5-10,7 s** |
| 5 s | CPU (4 núcleos) | no | 18 | 3,33 | 15→34 s, **y crece**: no da abasto |

Desglose con trozos de 10 s: hasta 10 s de espera a que el trozo se cierre (5 s es un mínimo:
el corte espera al siguiente cuadro clave), unos 2,7 s del hook y el vigilante, y unos 3,4 s de
proceso.

**Recomendación:** trozos de 5 s, GPU y vista en vivo encendida.

**Lo que cuesta el atajo:**
- **Hallazgos partidos.** Un incumplimiento que cruza el borde de un trozo se parte en dos
  hallazgos con tracks distintos: con 5 s salen 18 hallazgos en vez de 11, y se detecta un 22 %
  menos de duración. Si cada lado queda bajo los 2 s de confirmación, se pierde (deducido, no
  provocado a propósito).
- **Reglas largas.** Ninguna regla de más de 120 s puede dispararse.
- **Conteos inflados en la alerta.** Si el despachador agrupa dos trozos de la misma persona, el
  mensaje dice «2 personas sin casco» (`politica.py:156`), porque cuenta hallazgos y no personas.
  Se corrige el texto o se declara la limitación (PR 1).
- **Privacidad.** Los trozos van en tmpfs. MediaMTX está configurado para borrar los que están en
  curso al minuto, pero por limpieza periódica, así que el plazo no es exacto. Un borrador elimina
  los vigilados cuando su video queda `listo` o `error`, o a los 180 s aunque el trabajador esté
  caído (probado con el trabajador detenido). **Si PostgreSQL cae, hoy el borrador se detiene y
  no limpia** (hallazgo de Codex, se corrige en el PR 5). El borrador consulta por la API de
  `gepp-bd` (`videos.por_hash`), sin SQL propio. Aun así es **video nuevo de personas en la sala**:
  necesita la excepción D4.
- **Fallo silencioso con AV1.** Si el navegador elige AV1, el trabajador no lo decodifica y deja
  el trozo `listo` con **0 cuadros, sin error**: el panel diría que todo está bien sin haber
  mirado nada. En el celular hay que elegir H264. Que el trabajador falle con 0 cuadros es un
  arreglo aparte (PR 7).
- **Solo el celular de un integrante nombrado** (E4). El HTTPS y el video van por Tailscale, así que solo llega un
  teléfono dentro del tailnet. El de un profesor no conecta.

**Lo que Edgar tiene que hacer una vez:**
1. Activar «HTTPS Certificates» en la consola de Tailscale (hoy `CertDomains: null`). Al levantar
   la demo, exportar `TS_IP` con la IP del portátil en Tailscale: sin ella, el video queda en
   loopback y el teléfono no conecta.
2. Correr `! tailscale serve --bg --https=443 http://127.0.0.1:18889`. Se deshace con
   `! tailscale serve reset`.
3. En el celular, con Tailscale conectado, abrir `https://<nombre del portátil>.<tailnet>.ts.net/camara/publish`,
   elegir **H264** y publicar.

**Plan B:** si el celular falla en la sala, se reproduce en vivo un video de prueba autorizado,
publicado a MediaMTX con ffmpeg. Es el mismo camino, sin cámara.

## 6. Decisiones de Edgar

| # | Decisión | Recomendación |
|---|---|---|
| D1 | **¿Se monta un respaldo en GCP?** Si va, ¿con qué cuenta? La configurada en `gcloud` es la corporativa de SETRAM | Solo si la demo local ya funciona, con datos del lote 2 y una cuenta personal (la prueba de 300 USD pide tarjeta). Nunca la de SETRAM |
| D2 | **¿Hay panel abierto a los celulares de los profesores?** | No: ven la alerta de Telegram. Si se quiere, hace falta un rol nuevo de solo lectura y una entrada que no reenvíe `/vivo`. Es código, y se decide aparte |
| D3 | **Ventana exclusiva de la GPU**: no entrenar desde el ensayo hasta el final de la presentación (ADR-010) | Sí |
| D4 | **Excepción de privacidad para la cámara en la sala**: captura consentida (aviso a quien se pare frente a la cámara), trozos solo en memoria, borrados también si el trabajador falla, y un tope de cuánto video existe a la vez | Sí, escrita en `02-privacidad` antes de usarla. Si no, plan B: video ya autorizado |
| D5 | **Qué dispara la alerta**: la cámara de severidad 4 en el armado de la demo | Sí. No toca la política de ADR-008 |
| D6 | **`RtspFrameSource` real y escritura incremental** (más de 400 líneas, toca la regla del reloj) | Después de la presentación |
| D7 | **Mostrar el acuse en la web** (endpoint nuevo; contrato congelado) | No por ahora: se ve en Telegram y queda en la base |

Segunda ronda, aprobada por Edgar el 2026-11-03 («sí a todo»). Detalle y pasos en
[`acceso-equipo-y-espejo.md`](acceso-equipo-y-espejo.md); condiciones en `02-privacidad`, sección
«Acceso de integrantes por la tailnet y espejo de la cámara».

| # | Decisión | Queda así |
|---|---|---|
| E1 | ¿La tailnet del equipo es «infraestructura controlada»? | Sí, con integrantes nombrados, una ACL que limita el portátil, solo material de demostración y dispositivos propios |
| E2 | Rol de Miguel en la demo | `auditor`, asignado solo en la base de la demo |
| E3 | Cómo entra cada integrante sin token en el JavaScript | Una puerta del nginx para la tailnet traduce la identidad de Tailscale a un token por persona; sin identidad, 403 |
| E4 | Celular de otro integrante como cámara | Sí: D4 vale para los integrantes nombrados y para los ensayos |
| E5 | Espejo de la cámara en la página | Sí, por el nginx y con la misma identidad, sin grabarse |
| E6 | Pantalla «Sala en vivo» antes de los KPI | Sí: espejo, vista procesada y hallazgos recientes, sin tocar el contrato. Las alertas con su acuse siguen en D7 |

## 7. Lo que nadie comprobó

- **GCP real:** ningún tripulante corrió `gcloud`, así que no hay VM, cuota ni precio de VM
  verificados.
- **Telegram real:** no hay token.
- **El celular real**, tanto en Android como en iPhone, `tailscale serve` y el video por la IP
  100.x; tampoco una pausa larga del emisor con el hook.
- **La latencia hasta la alerta en Telegram**: lo medido llega hasta el hallazgo en la base.
- **Una persona real sin casco** frente a la cámara: hicieron de cámara el video de demo y un
  Chromium con cámara falsa.
- **Si el panel muestra vacío el respaldo precargado** cuando sus eventos quedan fuera de los
  últimos 7 días (`panel.py:41`).

## 8. Trabajo, una vez decidido (un PR por fila, menos de 400 líneas cada uno)

| PR | Contenido |
|---|---|
| 1 | Compose de la demo local: imágenes, la evidencia y el anillo de la vista compartidos entre trabajador y API, y la vista encendida. El despachador, con reinicio automático y un solo consumidor del bot, más un comando para volver a `pendiente` los avisos que agotaron sus 5 intentos. El destinatario de Telegram, por variable (hoy fijo en `prevencionista-demo`). El token de la web, en tiempo de ejecución o compilado con el mismo de la API (si no, 401). El texto de la alerta no cuenta como personas los hallazgos partidos |
| 2 | `armar-demo` y `rearmar-demo`: detener la captura y el hook, vaciar `en-curso` y la carpeta vigilada, y después PostgreSQL, Redis, evidencia y outbox, de forma coordinada. La alerta queda sin gastar. Se arma después de encuadrar la cámara, para que un trozo del encuadre no la consuma |
| 3 | Web: refresco periódico de la bandeja, el panel y la lista de videos, también con la lista vacía o ya terminada, para descubrir videos nuevos y mostrar lo que entra después del guardado final. No toca el contrato |
| 4 | Diagnóstico de errores de Telegram, ya hecho por Teddy |
| 5 | Celular como cámara, según D4. El vencimiento a 180 s del borrador no puede depender de la base, y el borrador se reinicia solo |
| 6 | Docs: `02-privacidad` (D4) y el guion de la presentación con su plan B |
| 7 | El trabajador marca `error`, no `listo`, un video del que no pudo leer ningún cuadro (caso AV1) |
| S1 | nginx: puerta de la tailnet con token por persona y `/espejo/` hacia MediaMTX con un usuario de solo lectura (E1, E3, E5) |
| S2 | Web: página «Sala en vivo» con el espejo, la vista procesada con un cartel entre trozos y los hallazgos recientes (E6) |

## 9. Qué cambió con la revisión de Codex

**Segunda ronda** (`gpt-6-astra`, max): quedan **cerrados en el diseño** los puntos 1, 2, 4, 6 y
10 de la tabla que sigue. Los puntos **3, 5, 7, 8 y 9 quedan abiertos hasta implementarse**; sus
pendientes concretos están en los PRs 1, 2, 3 y 5 y en D4. También quedan abiertos el respaldo con
datos de más de 7 días, si se monta (D1), y las fotos comprobadas (3 de 11, sin salida guardada).
Los cuatro hallazgos nuevos (el borrador depende de la base, el token de la web, el destinatario
fijo y los conteos inflados) entraron en los PRs 1 y 5. Las precisiones de la sección 5 (qué mide
la latencia, la confirmación contada dos veces, el plazo de MediaMTX, el cuadro clave y `TS_IP`)
están aplicadas.

**Primera ronda:**

| Hallazgo de Codex | Cambio |
|---|---|
| El panel en GCP no muestra el evento de la sala: son dos bases | La recomendación pasa a un solo sistema en el portátil, y GCP queda como respaldo opcional (D1) |
| No hay rol para un panel público | Sin panel público; los profesores ven la alerta (D2) |
| Los trozos de MediaMTX no están cubiertos por la excepción de privacidad | D4 y plan B |
| D2 y D3 de la versión anterior suponían que el lote 3 se podía subir a la nube | Retirado: el respaldo usa el lote 2, que es sintético |
| La web no se refresca sola | PR 3 |
| «Reiniciar la base» no rearma la demo | PR 2 |
| El despachador cae y deja de reintentar a los 5 fallos | PR 1 |
| Red de WebRTC y HTTPS del celular | Sección 5 y encargo a Osito |
| Cada trozo reinicia el seguimiento | Sección 5 |
| Correcciones a la tabla de la sección 3 (fotos comprobadas, lotes, ONNX y GPU, cámara del `levantar.sh`, la espera de 30 min, el despachador en el perfil `alertas`, el borrador no es «sin código») | Aplicadas |
| Faltaban la ventana de la GPU y la discrepancia con ADR-012 | D3 y sección 3 |
