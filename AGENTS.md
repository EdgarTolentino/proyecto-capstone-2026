# Guardián EPP — instrucciones para agentes de código

Capstone APT122 (Duoc UC, 2026). Detección de uso de EPP sobre video de CCTV. Monorepo `uv`
(Python) + React/TS. El repositorio es **público**.

Reglas del equipo: [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md). Decisiones de fondo:
[`docs/arquitectura/adr/`](docs/arquitectura/adr/). Este archivo dice cómo trabajar aquí y qué
significa «terminado».

## Dónde está cada cosa

| Ruta | Qué es |
|---|---|
| `Fase 2/sistema/apps/web/` | Frontend: React + TS, Vite, Vitest, React Query |
| `Fase 2/sistema/apps/web/src/hooks/` | Navegación (`useAppNavigation`) y filtros en la URL |
| `Fase 2/sistema/apps/web/src/api/` | Cliente tipado; `schema.d.ts` se **genera** desde el contrato |
| `Fase 2/sistema/contracts/openapi.yaml` | Frontera backend ↔ frontend. **Congelado** |
| `Fase 2/sistema/packages/` | Backend Python: `gepp-core`, `gepp-bd`, `gepp-api`, `gepp-vision`, `gepp-worker` |

## Comandos

La ruta tiene un espacio: siempre entre comillas.

```bash
cd "Fase 2/sistema/apps/web"
npm run lint && npm run typecheck && npm test && npm run build
npm run generate:api        # solo si cambió contracts/openapi.yaml; no editar schema.d.ts a mano

cd "Fase 2/sistema"
make lint && make tipos && make test
make mock                   # API simulada del contrato en :4010 (cabecera Authorization: Bearer demo)
```

## Qué significa «terminado»

Un cambio está terminado cuando se cumplen las cinco condiciones:

1. **La suite completa pasa en el último commit**, corrida una vez al final. Las cifras que van
   al PR (archivos, pruebas, módulos) salen de esa corrida, copiadas de la salida.
2. **Cada afirmación del PR o del README de evidencias se comprobó.** Si dice «conserva los
   filtros», hay un test o un recorrido que lo demuestra, y se explica cuál. Si algo se probó
   solo contra el mock, se dice.
3. **Cada test nuevo cae si se rompe lo que cuida.** Se comprueba rompiendo el código a
   propósito un momento y viendo el test en rojo.
4. **Los casos límite tienen test:** entrada vacía, entrada inválida (`2026-13-01`), primer y
   último elemento, valor cero.
5. **La plantilla del PR está completa:** «Cómo lo verificaste» lleva comandos y salida.

## Hábitos que evitan errores

- **Si la tarea choca con una regla de este archivo o con un ADR, se avisa antes de escribir
  código**, citando la regla. No se busca la forma de esquivarla.
- **Las cifras se copian de una salida, no se calculan de memoria.** Antes de publicar, se
  recalculan.
- **El significado de un dato se comprueba con una ejecución real**, no con su nombre: qué id
  es cada clase, en qué unidad viene un número, en qué zona horaria está una fecha.
- **Dos intentos fallidos con el mismo enfoque: se para.** Se relee el código o se empieza
  limpio, en vez de un tercer parche sobre el mismo síntoma.
- **Antes de cambiar de dónde sale un dato, se busca quién lo consume** (`grep`).
- **Un comando que reinstala o borra se lee antes de correrlo.** En la máquina con GPU se usa
  `make setup-gpu`, nunca un `uv sync` pelado: desinstala `rfdetr` y `torch`. Antes de borrar
  o sobrescribir, se mira qué hay.

## Datos y modelos

- **Ningún dato entra a entrenar ni a evaluar sin una fila en
  `docs/producto/07-datasets.md`.**
- **Lo que se entrena no se evalúa.** El video de prueba nunca entra a entrenamiento, y la
  partición es por video y escena, nunca por cuadro (`dataset.verificar_particion`).
- **Las métricas de un modelo van con el commit, los datos y los pesos que las produjeron.**
  Sin eso no se pueden reproducir.

## Frontend: errores que ya ocurrieron aquí

- **La URL y el estado deben coincidir siempre.** Si un filtro vive en la URL, el estado se
  relee de la URL en **toda** navegación: `pushState` no dispara `popstate`. Los tests de ida y
  vuelta entre secciones revisan el **estado visible** (lo que muestra el selector, la query que
  se pidió), no solo `window.location`.
- **Un enlace de una tarjeta a una lista debe mostrar los mismos datos que la tarjeta.** Si el
  backend aplica una ventana por defecto (el panel usa 7 días), el enlace la manda explícita.
  Antes de enlazar, revisar en `openapi.yaml` qué filtros acepta el destino.
- **Fechas:** los días se cortan en la zona horaria de la faena (`config.zona_horaria`), no en
  la del navegador. Los rangos son semiabiertos: `desde` incluido y `hasta` excluido (el día
  siguiente a las 00:00, no `23:59:59`). Validar que la fecha exista, no solo su formato.
- **Estados de una consulta:** carga, error, reintento, vacío y **sin permiso** (401/403) son
  estados distintos. Al cambiar un filtro, mantener los datos previos mientras carga
  (`placeholderData: keepPreviousData`) para que la pantalla no parpadee.
- **Accesibilidad:** `aria-label` solo sirve en elementos con rol. Un grupo de controles va en
  `<fieldset>` o con `role="group"`.
- **Las capturas de evidencia deben verse correctas** para quien no conoce el mock. Si el mock
  da datos raros, ajustar el ejemplo o explicarlo.

## Invariantes del proyecto

Si una tarea choca con uno de estos, **detenerse y avisar** citando el ADR. No esquivarlo.

- Sin identificación de personas: sin reconocimiento facial, sin inferir género, edad ni etnia
  (ADR-006).
- El contrato no se rompe en silencio: un campo opcional se agrega y se avisa; renombrar o
  quitar algo va en un PR aparte, acordado con el equipo.
- Nada AGPL ni propietario en dependencias (ADR-002).
- Nunca al repo: video de obra, pesos, datasets, rostros sin difuminar, credenciales, RUT.

## Revisión

- Quien escribió el código no es quien lo revisa. Antes de pedir revisión, revisar el diff
  **en una sesión nueva**, sin el contexto de la que lo escribió, con esta pregunta: «¿qué
  escenario concreto hace fallar este cambio?».
- **Cuando llega una revisión, todos sus puntos se corrigen en el mismo PR**, también los
  menores. En la descripción va una línea por punto: commit que lo arregla y cómo se comprobó.
- Si un punto de la revisión parece equivocado, se responde con evidencia en el hilo; no se
  ignora.

## Git

- Nunca a `main` directo. Ramas `feat/`, `fix/`, `docs/` o `chore/`.
- Commits `tipo(ámbito): qué hace`, y en el cuerpo el **porqué** y cómo se comprobó.
- Un PR, una cosa, menos de 400 líneas cambiadas.
- Español de Chile en commits, PR y textos de interfaz.
