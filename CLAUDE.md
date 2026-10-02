# Guardián EPP — instrucciones para Claude Code

Capstone APT122 (Duoc UC, 2026). Detección de uso de EPP y condiciones inseguras sobre video de
CCTV. Monorepo `uv` + React. El repositorio es **público**.

Las reglas de trabajo humano están en [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md) y las
decisiones de fondo en [`docs/arquitectura/adr/`](docs/arquitectura/adr/). Este archivo no las
repite: dice cómo trabaja un asistente de IA aquí y cómo se valida lo que produce.

Codex lee [`AGENTS.md`](AGENTS.md), no este archivo. Si cambias una regla que aplica a los dos,
cámbiala en ambos.

## Dónde está cada cosa

| Ruta | Qué es |
|---|---|
| `Fase 2/sistema/packages/` | `gepp-core`, `gepp-bd`, `gepp-api`, `gepp-vision`, `gepp-worker` |
| `Fase 2/sistema/apps/web/` | Frontend React + TS (Vite, Vitest, React Query) |
| `Fase 2/sistema/contracts/openapi.yaml` | Frontera backend ↔ frontend. **Congelado**: ver CONTRIBUTING |
| `docs/arquitectura/adr/` | ADR-001 a ADR-012 |
| `docs/producto/02-privacidad-y-cumplimiento.md` | Lo que el sistema nunca hace con personas |

## Comandos de verificación

La ruta tiene un espacio: siempre entre comillas.

```bash
cd "Fase 2/sistema"
make lint && make tipos && make test        # Python: ruff, mypy, pytest sin GPU
make contrato                               # la API sirve lo mismo que openapi.yaml

cd "Fase 2/sistema/apps/web"
npm run lint && npm run typecheck && npm test && npm run build
npm run generate:api                        # tras cambiar el contrato: regenera schema.d.ts
```

El CI (`.github/workflows/ci.yml`) corre lo mismo y además bloquea dependencias con licencia
prohibida (`ultralytics`, `boxmot`, `deimv2`, `super-gradients`). El job «Todo en verde» manda.

## Invariantes que no se negocian

Antes de proponer algo que choque con uno de estos, **decirlo de inmediato** y citar el ADR. No
buscar la forma de esquivarlo.

1. **Detector + reglas deciden; el VLM solo describe** (ADR-001).
2. **Nada AGPL ni propietario** en dependencias ni en pesos (ADR-002). RF-DETR, no YOLO.
3. **Sin `datetime.now()` en el dominio:** el tiempo sale de la fuente de video (ADR-005).
   Lo cuida `tests/test_reloj.py`. Los umbrales se expresan en segundos, nunca en cuadros.
4. **Sin identificación de personas:** `track_id` efímero, sin reconocimiento facial, sin
   inferir género, edad ni etnia, y el rostro se difumina antes de escribir el recorte (ADR-006).
5. **Fronteras del monorepo:** `gepp-api` no importa `gepp-vision`; `gepp-bd` no importa visión,
   trabajador ni web (`tests/bd/test_frontera.py`) (ADR-007).
6. **El dominio es configuración:** se evalúa en construcción; la minería es un perfil YAML
   (ADR-011).
7. **Agregados por dotación con supresión de celdas n < 5**, en el servidor.
8. **Nunca al repo:** video de obra, pesos, datasets, rostros sin difuminar, credenciales, RUT.

## Cómo se trabaja con un asistente aquí

**Explorar → planificar → implementar → verificar.** Si el cambio no se describe en una frase,
primero va un plan con los archivos que se tocan y cómo se comprobará. Un PR, una cosa, de menos
de 400 líneas (CONTRIBUTING). Si no cabe, se dice antes de abrirlo, no después.

**Antes de escribir:** si lo pedido choca con una regla, un ADR o un invariante, **se dice apenas
se ve**, con la cita, y decide un humano. No se intenta esquivar en silencio. Tres intentos para
esquivar una regla cuestan más que una pregunta.

### Las reglas

Cada una salió de un error real en este proyecto. La columna «Se cumple cuando» es lo que un
revisor puede comprobar.

| # | Regla | Se cumple cuando |
|---|---|---|
| 1 | **No afirmar lo que no se miró.** Repetir una afirmación no la verifica | Cada «funciona», «conserva» o «pasa» del PR, del commit o de un README trae su evidencia: comando y salida, test o captura. Lo probado solo contra el mock o con una muestra lo dice |
| 2 | **Las cifras se copian de una salida, no se calculan de memoria** | Cada número del PR (tests, imágenes, métricas) se puede rastrear hasta un comando corrido en ese commit. Se recalculan justo antes de publicar |
| 3 | **La suite completa va una vez, al final, antes de pedir revisión** | El PR pega la salida de esa corrida (`make lint tipos test` o `npm run lint typecheck test build`) |
| 4 | **Un test se valida inyectándole el defecto que dice cuidar** | Se rompió el código a propósito y el test cayó. Los tests de interfaz miran el estado visible, no solo la URL |
| 5 | **Toda función con umbral o centinela se prueba en sus dos extremos y con una entrada inválida** | Hay un caso justo en el umbral, uno a cada lado y uno inválido. Para umbrales en coma flotante, valores diádicos (0,25; 0,5; 0,75) que dan resultados exactos |
| 6 | **Una guarda que se dispara se entiende antes de tocarla** (tests de AST, CI de licencias, mypy, `CategoriaDesconocida`) | El commit explica por qué se disparó. Si molesta, lo normal es que el defecto sea propio |
| 7 | **El significado de un dato se comprueba con una ejecución real**, no con su nombre ni con la documentación | Ids de clase, unidades, zonas horarias y formatos de caja se verifican con datos de verdad. Ejemplo: en RF-DETR COCO, `class_names[1]` es `bicycle`, pero `predict` devuelve `1` para persona |
| 8 | **Antes de cambiar de dónde sale un dato, `grep` de quién lo consume** | El PR lista los consumidores revisados |
| 9 | **Dos intentos fallidos con el mismo enfoque: se para y se vuelve a explorar** | No hay un tercer parche sobre el mismo síntoma. Se relee el código o se abre una sesión limpia |
| 10 | **Un comando que reinstala o borra se lee antes de correrlo** | En la máquina con GPU, `make setup-gpu` y nunca un `uv sync` pelado, que desinstala `rfdetr` y `torch`. Se mira el destino antes de borrar o sobrescribir |

### Datos y modelos

- **Ningún dato entra a entrenar ni a evaluar sin una fila en `docs/producto/07-datasets.md`.**
- **Lo que se entrena no se evalúa.** El video de prueba nunca entra a entrenamiento, y la
  partición es por video y escena, nunca por cuadro (`dataset.verificar_particion`).
- **Las métricas de un modelo van con el commit, los datos y los pesos que las produjeron.**
  Sin eso no se pueden reproducir.

### Fechas

Se cortan en la zona horaria de la faena (`config.zona_horaria`), no en la del navegador. Los
rangos son semiabiertos: `[desde, hasta)`.

## Validación cruzada entre IA

El equipo usa más de un asistente: Claude Code y OpenAI Codex. **Quien escribe no se revisa a sí
mismo.** Un modelo, o una sesión, que no escribió el código revisa mejor que el autor pidiéndose
«revisa lo que hiciste». Los modelos tienden a dar por buena su propia salida.

| Paso | Quién | Qué |
|---|---|---|
| 1. Escribir | Asistente A, sesión 1 | Implementa y corre la suite |
| 2. Revisar | Asistente B, o A en una **sesión nueva** sin el contexto de 1 | Solo ve el diff, el issue y este archivo. Reporta defectos de corrección y de requisitos, no gustos |
| 3. Verificar | Quien revisa | Reproduce cada hallazgo (test ad hoc, inyección de defecto o lectura con archivo:línea) y marca **CONFIRMADO** o **PLAUSIBLE** |
| 4. Decidir | Un humano | Acepta, descarta o pide cambios. La IA no aprueba ni fusiona |

Reglas de la revisión:

- **Los hallazgos llevan escenario concreto:** entrada o pasos → resultado incorrecto. Sin
  escenario es opinión, no hallazgo.
- **Lo que el revisor no pudo comprobar se declara.** Nunca se presenta lo plausible como
  confirmado.
- **Todas las correcciones de una revisión van al mismo PR**, también las menores. Cada punto se
  cierra en la descripción con el commit que lo arregla y cómo se comprobó.
- **El revisor no cambia la rama del autor.** Lee, prueba en un worktree aparte y comenta.
- **Lo que una revisión encontró y debió saberse antes se agrega aquí**, en una línea.

En Claude Code: `/code-review <n° de PR>` para la revisión y un subagente para reproducir los
hallazgos. En Codex: su propio comando de revisión, con este mismo procedimiento.

## Git y PR

- Nunca a `main` directo; rama `feat/`, `fix/`, `docs/` o `chore/` (CONTRIBUTING).
- Commits `tipo(ámbito): qué hace`, y en el cuerpo el **porqué** y cómo se comprobó.
- **No fusionar sin permiso explícito del dueño del repo, cada vez.** El asistente no aprueba sus
  propios PR.
- La plantilla del PR se rellena de verdad: «Cómo lo verificaste» lleva comandos y salida.
- Si el commit o el PR lo redactó una IA, se dice en el cuerpo (`Co-Authored-By`).

## Idioma

Español de Chile en código de dominio, commits, PR, issues y documentos. Los identificadores
técnicos estándar (`useQuery`, `pushState`) quedan como están.
