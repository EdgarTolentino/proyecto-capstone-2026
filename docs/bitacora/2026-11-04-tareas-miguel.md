# Miguel: el ensayo de hoy y lo que viene hasta H4

**Fecha:** 2026-11-04. Lo pidió Edgar. Si trabajas con un asistente de IA (Claude Code, Codex),
pásale este archivo junto con [`CLAUDE.md`](../../CLAUDE.md) (o [`AGENTS.md`](../../AGENTS.md)): aquí
está **qué** hacer, y ahí **cómo** se trabaja en el repo.

| # | Qué | Cuándo | Bloquea a |
|---|---|---|---|
| 1 | Ensayo de la demo con tu celular | **Hoy, 14:00**, con Edgar | La presentación |
| 2 | La tasa por dotación en pantalla (KPI 7) | Desde hoy, antes del 13-nov | H4 (16-20 nov) |
| 3 | Revisar los PR que tocan `contracts/` o `apps/web/` | Cuando GitHub te pida revisión | Que Edgar pueda fusionar sin `--admin` |
| 4 | Corregir tus tareas del lote 5 en CVAT (jobs 11 y 13) | Esta semana | Entrenar `epp-v4` |
| 5 | KPI 8 y 9 en el panel (opcionales) | Solo si sobra tiempo y Edgar ya hizo la API | — |

---

## 1. Ensayo de hoy (14:00)

Guía completa, con el porqué de cada paso:
[`docs/operacion/despliegue/acceso-equipo-y-espejo.md`](../operacion/despliegue/acceso-equipo-y-espejo.md).
La demo corre en el portátil de Edgar; tú entras por Tailscale.

### Antes de las 14:00 (te toma 10 minutos)

1. **Instala Tailscale** en tu computador **y** en tu teléfono, y entra con tu cuenta.
   - Acepta la invitación de Edgar a su tailnet.
   - Tienen que ser dispositivos tuyos: sin etiqueta y sin compartirlos con nadie más.
2. **Mándale a Edgar, por mensaje privado, el correo con que entraste a Tailscale.** Con ese correo
   te da acceso y te deja como `auditor` en la base de la demo: puedes ver hallazgos, evidencia y la
   vista en vivo, pero no triar ni procesar.
3. **Firma la autorización escrita** de la cámara. Si alguien más va a aparecer frente a la cámara,
   también firma. Sin autorización no se graba a nadie (excepción D4 de
   [`02-privacidad`](../producto/02-privacidad-y-cumplimiento.md)).

### Durante el ensayo

Edgar levanta todo y te pasa por privado dos direcciones y una clave.

1. **En tu computador**, abre `https://<portátil>.<tailnet>.ts.net:8443/sala`.
   - Entras sin escribir token: el nginx te reconoce por Tailscale.
   - Si ves **403**: tu correo no quedó en la lista. Avísale a Edgar.
   - Si la API da **401**: tu usuario no está en la base. Avísale a Edgar.
2. **En tu teléfono**, con Tailscale conectado, abre `https://<portátil>.<tailnet>.ts.net/camara/publish`.
   - Usuario `publicador`, y la clave que te pasó Edgar.
   - **Códec: H264.** Con AV1, el trabajador no procesa nada.
   - **«audio device»: `none`.** La página elige el micrófono por defecto, y no queremos audio de la sala.
   - Toca «publish» y permite **solo** la cámara.
3. **Mira la «Sala en vivo»** en tu computador:
   - «Cámara en vivo»: tu teléfono, casi sin atraso.
   - «Vista procesada (≈ 10 s de retraso)»: lo que ve el modelo, trozo por trozo.
   - «Hallazgos recientes»: si te paras sin casco frente a la cámara, debería aparecer un hallazgo
     unos 8 a 11 s después.
4. **Anota esto para Edgar.** Es lo que nadie ha podido probar todavía:
   - ¿El teléfono conectó a la primera? ¿En qué navegador y en qué sistema (Android o iPhone)?
   - ¿Cuántos segundos de atraso tiene la «Cámara en vivo»?
   - ¿Cuánto tarda en aparecer el hallazgo desde que te paras sin casco?
   - ¿Se cortó algo? ¿Qué decía la pantalla?
5. **Al terminar**, detén la publicación en el teléfono. Edgar cierra todo y comprueba que no quedó
   video.

---

## 2. KPI 7: la tasa por dotación en pantalla

Contexto y reparto: [issue #38](https://github.com/EdgarTolentino/proyecto-capstone-2026/issues/38).
Liân hace la página «Reportes» (KPI 3 a 6). **Tú haces la parte de la dotación** como un componente
propio, que Liân monta en su página. Pónganse de acuerdo en el nombre y en dónde va, para no
pisarse los archivos.

**La API ya existe en `main`** (#265, #266): `GET /reportes/dotacion?segmentacion=turno&desde=…&hasta=…&area_id=…`.
Los tipos están en `apps/web/src/api/schema.d.ts`. **No toques `contracts/openapi.yaml`**: está
congelado (CONTRIBUTING). Necesitas el permiso `ver_reportes`, que tienen `prevencionista` y `auditor`.

Cada fila trae:

| Campo | Qué es | Cómo se muestra |
|---|---|---|
| `etiqueta` | «Área · Turno» | Tal cual |
| `valor` | Incumplimientos por cada 100 trabajadores | Con un decimal. Si viene `null`, el texto de `razon` (abajo), **nunca 0** |
| `n` | Incumplimientos, **ya redondeado** a múltiplos de 5 | Como «≈ 20». No es el número exacto, y la interfaz no tiene que hacerlo parecer exacto |
| `datos_insuficientes` | `true` si se suprimió la celda | «Datos insuficientes» |
| `razon` | Por qué no hay tasa | `n_insuficiente` → «Menos de 5 incumplimientos»; `sin_dotacion` → «Sin dotación registrada»; `dotacion_insuficiente` → «Dotación menor a 5 personas»; `dotacion_incompleta` → «Faltan días de dotación en el período» |
| `dotacion.total` | Dotación promedio del período | «22 personas», o «—» si es `null` |
| `dotacion.hombres`, `.mujeres`, `.otro` | Composición | **Llegan los tres o ninguno.** Si vienen `null`: «No se muestra para proteger a grupos de menos de 5 personas» |

Reglas que no se negocian (invariante 7 y [`02-privacidad` §4](../producto/02-privacidad-y-cumplimiento.md)):

- La supresión es del servidor. **Nunca** calcules en el navegador un conteo oculto, ni el total
  menos los otros, ni nada parecido.
- Esto es **dato administrativo**. No es «género de las personas detectadas». El rótulo lo dice:
  «Dotación del turno (dato de RR. HH., no se infiere de la imagen)».
- Los datos de la demo son **sintéticos**. Ponlo en la pantalla mientras sea así.

**Terminado cuando:**
- `npm run lint && npm run typecheck && npm test && npm run build` pasan en verde.
- Hay tests de interfaz que miran lo visible: una fila con tasa, una fila por cada `razon`, la
  composición nula con su mensaje, y la composición completa.
- Cada test cae si le inyectas su defecto. Por ejemplo, mostrar 0 en vez de la `razon`.
- El PR tiene menos de 400 líneas y la plantilla rellena con la salida de la suite.

## 3. Revisar PR como dueño de código

Eres dueño de código de `apps/web/` y de `contracts/` (`.github/CODEOWNERS`), junto con Liân.
Cuando un PR toque esas carpetas, GitHub te pide la revisión. Sin la de uno de ustedes, Edgar tiene
que fusionar con `--admin`.

- Mira el diff de tu área y la sección «Cómo lo verificaste».
- Aprueba si se entiende y no rompe nada que tú uses.
- Si algo no cuadra, comenta con un escenario concreto: «con X pasa Y».

## 4. Lote 5 en CVAT

Tus tareas son los **jobs 11 y 13** del lote 5 (video público CC BY, solo para entrenar).
- CVAT corre en la máquina de Edgar: pídele que lo prenda y entra por Tailscale.
- Reglas: [`docs/datos/guia-etiquetado.md`](../datos/guia-etiquetado.md), §9. Lo importante es
  marcar `cabeza` cuando se ve la cabeza sin casco.
- Avísale a Edgar al terminar: con el lote completo se entrena `epp-v4`.

## 5. KPI 8 y 9 (opcionales)

La tasa de falsos positivos y el tiempo hasta revisar un crítico, como tarjetas en el panel.
**Todavía no hay API.** No empieces hasta que Edgar te avise que existe.

---

## Cómo se trabaja (resumen; manda `CLAUDE.md`)

- Rama `feat/…` o `fix/…`, nunca a `main` directo. Un PR, una cosa, de menos de 400 líneas.
- La suite completa corre antes de pedir revisión, y su salida va en el PR.
- Repo **público**: nada de correos reales, tokens, hostnames `ts.net`, IPs 100.x ni capturas con
  caras.
- Si el commit lo redactó una IA, se dice (`Co-Authored-By`).
- Si algo choca con una regla o un ADR, se dice antes de empezar, no después.
