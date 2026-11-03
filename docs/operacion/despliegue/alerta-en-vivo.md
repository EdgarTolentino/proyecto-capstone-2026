# Alerta en vivo — guion y decisiones (#36)

> Objetivo de la demo: un incumplimiento en el video dispara un aviso en un grupo de Telegram,
> alguien toca **Acuso recibo** y el acuse queda en la base. Puesta en marcha del bot:
> [`../alertas-telegram.md`](../alertas-telegram.md). Aquí solo lo que cambia para la presentación.

## Qué ya existe y qué falta (código de `main` 239f3fc)

| Pieza | Estado | Dónde |
|---|---|---|
| Outbox, reintentos, `SKIP LOCKED` | Hecho | `despachador.py`, `gepp_bd/repositorios/notificaciones.py` |
| Botón «Acuso recibo» → `callback_query` → `acusada` en la base | Hecho (por *long polling*) | `telegram.py` `acuses_recibidos`, `acusar_por_token` |
| Presupuesto 6/turno, esperas 10 min global y 30 min por cámara | Hecho, con tests en los bordes | `politica.py`, `tests/bd/test_despachador.py` |
| Que un fallo de `getUpdates` (webhook activo, token revocado) **no pase en silencio** | **Agregado aquí**: `CanalTelegram.ultimo_error` y línea en la terminal del despachador | `telegram.py`, `__main__.py` |
| Prueba de punta a punta con Telegram simulado (alerta → grupo → toque → `acusada`) | **Agregada aquí** | `tests/bd/test_notificaciones_telegram_e2e.py` |
| El despachador **no muere si la base se corta**: `ciclo()` anota `error_bd`, sigue en el ciclo siguiente y conserva los acuses que Telegram ya entregó (los da una sola vez) y, mientras haya alguno sin guardar, no pide updates nuevos: así no se confirman ante Telegram y un reinicio con la base caída los recibe de nuevo. Atrapa cualquier `SQLAlchemyError` (base caída, pool agotado, sesión inválida); un error de programación sigue tumbando el proceso | **Agregado** (PR 4) | `despachador.py`, `tests/bd/test_notificaciones_robustez.py` |
| Avisos que agotaron los 5 intentos: `python -m gepp_api.notificaciones --reintentar-agotados` los vuelve a `pendiente` (intentos en 0) y lo registra en `auditoria`. No toca los rechazos permanentes (token inválido, bot bloqueado): quedan marcados con el prefijo `rechazo_permanente: ` en `motivo`, sin cambiar el esquema | **Agregado** (PR 4) | `__main__.py`, `repositorios/notificaciones.py` |
| El texto cuenta **incumplimientos**, no personas («2 incumplimientos sin casco»): con un video partido en trozos la misma persona da dos hallazgos y `track_id` es efímero | **Cambiado** (PR 4) | `politica.texto_inmediato` |
| **El acuse visible en el panel web** | **Falta.** Ningún endpoint ni pantalla lee `notificacion` (solo `/metrics` cuenta por estado). Pide endpoint + `openapi.yaml` (congelado) | decide Edgar |
| Webhook (Cloud Run con escala a cero) | **No hecho.** Pide ruta en `gepp-api` y secreto | decide Edgar |
| «Alerta real en un teléfono» del #36 | **No comprobado**: no hay token y no se probó contra la red real | ensayo con Edgar |

## Telegram: webhook o *long polling*

| | Long polling (`getUpdates`, lo implementado) | Webhook (`setWebhook`) |
|---|---|---|
| Red | Solo sale hacia `api.telegram.org`. Sirve detrás de NAT, en el notebook | Necesita una URL HTTPS pública (Cloud Run la da) |
| Código | Hecho | Falta una ruta que reciba el `Update` y llame a `acusar_por_token` |
| Nube | Sirve en un proceso que **siempre** corra (VM chica, o Cloud Run con mínimo 1 instancia y CPU siempre asignada) | Sirve con escala a cero |
| Conflicto | **Un solo consumidor por token**: dos despachadores, o uno con webhook puesto, se pelean (HTTP 409) | Mientras haya webhook, `getUpdates` no funciona |

**Recomendación:** *long polling* para la presentación, en un solo lugar (el despachador donde
corra la base). Cero código nuevo y cero endpoint público. El webhook solo vale la pena si el
despachador debe escalar a cero, y hoy no hay razón.

Fuentes oficiales (leídas de memoria; **no las abrí en esta sesión**, confirmar antes de citar):
`https://core.telegram.org/bots/api#getupdates`, `#setwebhook`, `#answercallbackquery`,
`#callbackquery`, `#inlinekeyboardbutton` (`callback_data` de 1 a 64 bytes; el nuestro, `acuse:` +
22 caracteres, cabe) y `https://core.telegram.org/bots/webhooks`.

## Privacidad: qué lleva el mensaje

- **Hoy:** título (`área · turno`), cuántos incumplimientos, qué EPP, ventana de horas y la leyenda
  «Indicio automatizado…». Sin nombres, sin `track_id`, sin imagen (`politica.texto_inmediato`).
  Coincide con ADR-008 (al área y al turno) y con `alertas-telegram.md` §Privacidad.
- **La foto del recorte: no.** El rostro del recorte va difuminado en disco
  (`02-privacidad-y-cumplimiento.md`, medida «Anonimización por defecto», l.114), pero ese
  documento no autoriza sacar imágenes a un servicio de terceros, y `03-alertas.md` dice que la
  evidencia va por URL firmada con expiración, «nunca la imagen embebida». Si se quiere mostrar
  evidencia en la sala, que sea en el panel propio. Decisión de Edgar si cambia.
- **Grupo con profesores:** el mensaje no tiene datos personales, así que el texto no es problema.
  Lo que hay que saber: (1) los miembros del grupo ven los nombres de los demás en Telegram;
  (2) Telegram le entrega al bot quién tocó el botón (`callback_query.from`). **El código lo
  descarta**: guarda `acusada_en` y deja `acusada_por` vacío (probado en
  `test_el_toque_de_un_grupo_acusa_sin_llevar_quien_toco` y en el e2e). Un acuse es del turno, no
  de una persona. (3) El bot solo debe estar en ese grupo y no recibir mensajes de él: no se lee
  nada del chat salvo los toques del botón (`allowed_updates=["callback_query"]`).
- Que los profesores se sumen por enlace de invitación; el grupo se borra después de la demo y
  el token se revoca con `/revoke` en @BotFather.

## Plan B: sin red en el teléfono

| Falla | Qué se hace |
|---|---|
| El teléfono no tiene datos | Segundo teléfono con hotspot, o el notebook con Telegram Web/Desktop en el mismo grupo: el botón se toca desde ahí |
| Telegram no responde | El despachador reintenta solo con espera, hasta 5 intentos; después el aviso queda `fallida` y NO sale solo: `python -m gepp_api.notificaciones --reintentar-agotados` lo vuelve a `pendiente`. Se ve en su terminal. No hay que repetir el video |
| Se quiere mostrar el acuse sin Telegram | Pantalla secundaria con la consulta de abajo, cada 2 s |
| «Toast en el panel web» | **No existe hoy** y pide endpoint + contrato (congelado). No se hizo; lo decide Edgar. Con la consulta de abajo en una terminal grande el efecto es el mismo |

```bash
watch -n2 'docker exec gepp-demo-postgres-1 psql -U gepp -d gepp -c \
  "select id, estado, enviada_en, acusada_en from notificacion order by id desc limit 5"'
```

## Guion del momento en vivo

**Antes (el día anterior y 30 min antes)**

1. Ensayo completo con **otro** grupo o base limpia. Un ensayo gasta la espera global (10 min) y
   la de cámara (30 min) del destinatario y suma al presupuesto: en la presentación el aviso
   quedaría «esperando» o bajaría al resumen. Para la demo: una base de
   demo vacía, o un `chat_id` nuevo.
2. Un solo despachador corriendo. Apagar cualquier otro (el de otra máquina) o aparece el 409,
   que ahora se imprime como `[despachador] acuses: 409: Conflict…`.
3. Confirmar que el video elegido produce un hallazgo **grave** (severidad crítica o más de 120 s):
   con `FUENTE=2` en `alertas-telegram.md` §3. Lo corriente no avisa; eso es ADR-008, no un fallo.
4. Profesores en el grupo; el bot ya está en él y `GEPP_AVISO_DESTINATARIO` es el `chat_id`
   negativo del grupo.

**En vivo**

| # | Quién | Acción | Se ve |
|---|---|---|---|
| 1 | Presentador | Muestra el video corriendo y el despachador en la terminal | `[despachador] Telegram, cada 5 s` |
| 2 | Sistema | El video llega al incumplimiento grave | Fila `notificacion` en `pendiente` |
| 3 | Despachador | Próximo ciclo (ver latencia abajo) | `enviados=1` y el mensaje suena en los teléfonos |
| 4 | Profesor/a | Toca **✅ Acuso recibo** | El botón desaparece para todo el grupo |
| 5 | Despachador | Próximo ciclo (ver latencia abajo) | `acusados=1` |
| 6 | Presentador | Muestra la consulta de Plan B | `estado = acusada`, `acusada_en` con hora |

Latencia del aviso y del acuse: **no hay una cota fija**. Cada ciclo hace sus llamadas a
Telegram y a la base y DESPUÉS espera `GEPP_DESPACHO_INTERVALO_S` (5 s por defecto): son
5 s más lo que tarden esas llamadas. `timeout=15` de httpx limita cada fase de la llamada
(conectar, escribir, leer), no la respuesta completa: una llamada lenta puede tardar más. No está
medida contra Telegram real: medirla en el ensayo.

## Garantía de entrega: «al menos una vez»

El despachador prefiere repetir un aviso a perderlo. Casos conocidos, no corregidos aquí:

- Telegram acepta el mensaje y la transacción que lo registra revierte (la base se corta justo
  ahí): al recuperarse se reenvía con **otro** token, y el acuse del primer mensaje no encuentra
  fila y se descarta. Quedan dos mensajes y solo vale el segundo.
- `--reintentar-agotados` puede **duplicar** un aviso: si el 5.º intento terminó en un
  `ReadTimeout`, Telegram pudo haberlo entregado aunque la base lo marcó `fallida`. Antes de usarlo
  en la presentación, mirar en el grupo qué llegó.
- Un 403 tras 4 fallos transitorios cuenta 5 intentos, pero el prefijo del motivo evita que el
  comando lo reviva.

## Qué NO se comprobó

- Nada contra la API real de Telegram: los tests usan un servidor simulado (`httpx.MockTransport`),
  así que los códigos de error (409 con webhook activo, 429, 403) son lo que la documentación dice,
  no lo que se vio.
- Que el mensaje se vea y suene bien en un teléfono, y el comportamiento de un grupo real.
- Ejecución en Google Cloud (no se corrió ningún `gcloud`).
