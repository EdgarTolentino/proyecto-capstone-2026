# Guardián EPP — instrucciones para Claude Code

Capstone APT122 (Duoc UC, 2026). Detección de uso de EPP y condiciones inseguras sobre video de
CCTV. Monorepo `uv` + React. El repositorio es **público**.

Las reglas de trabajo humano están en [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md) y las
decisiones de fondo en [`docs/arquitectura/adr/`](docs/arquitectura/adr/). Este archivo no las
repite: dice cómo trabaja un asistente de IA aquí y cómo se valida lo que produce.

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
primero un plan con los archivos que se tocan y cómo se comprobará. Un PR, una cosa, de menos de
400 líneas.

Las reglas siguientes salieron de errores reales en este proyecto:

1. **No afirmar lo que no se miró.** Si el PR, el commit o un README dice que algo «funciona» o
   «conserva» algo, se comprobó en la app o con un test, y se dice cómo. Repetir una afirmación
   no la verifica.
2. **Evidencia antes que afirmación.** «Pasa» significa: este comando, en este commit, con esta
   salida. Toda cifra que entra a un PR (tests, módulos, métricas) se recalcula en el momento.
3. **La suite completa va una vez, al final, antes de pedir revisión**, no después.
4. **Un test se prueba inyectándole el defecto que dice cuidar.** Si no cae, no protege nada. Los
   tests de navegación y filtros revisan el **estado** visible, no solo la URL.
5. **Antes de cambiar de dónde sale un dato, `grep` de quién lo consume.**
6. **Toda función con centinela o con límites** (fechas, ventanas, paginación, umbrales) se
   prueba en sus dos extremos y con una entrada inválida.
7. **Una guarda que se dispara** (test de AST, CI de licencias, mypy) **se entiende antes de
   tocarla.** Si molesta, lo normal es que el defecto sea propio.
8. **Fechas:** se cortan en la zona horaria de la faena (`config.zona_horaria`), no en la del
   navegador. Los rangos son semiabiertos `[desde, hasta)`.

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
