# Cómo trabajamos en este repositorio

Tres personas tocando el mismo repo durante once semanas. Estas reglas no son burocracia:
existen para que nadie pierda un día de trabajo por algo que otro subió.

## La regla de oro

**Nadie sube nada directo a `main`.** Está protegido y GitHub lo va a rechazar. Todo entra por
Pull Request, con el CI en verde.

## El ciclo completo

```bash
# 1. Partir siempre de un main actualizado
git checkout main
git pull

# 2. Rama nueva, una por tarea
git checkout -b feat/bandeja-de-hallazgos

# 3. Trabajar y confirmar en trozos pequeños
git add .
git commit -m "feat(web): tabla de hallazgos con filtros"

# 4. Subir
git push -u origin feat/bandeja-de-hallazgos

# 5. Abrir el PR
gh pr create --fill
```

Después: el CI corre solo, alguien revisa, y **quien revisa fusiona**. No te fusiones tu propio
PR salvo que sea trivial y esté aprobado.

## Nombres de rama

| Prefijo | Cuándo | Ejemplo |
|---|---|---|
| `feat/` | Funcionalidad nueva | `feat/visor-de-evidencia` |
| `fix/` | Corregir algo roto | `fix/filtro-de-severidad` |
| `docs/` | Solo documentación | `docs/manual-de-usuario` |
| `chore/` | Herramientas, configuración, dependencias | `chore/subir-vite-a-6` |

## Mensajes de commit

`tipo(ámbito): qué hace, en presente`

```
feat(web): bandeja de hallazgos con triage por teclado
fix(web): el filtro de severidad no limpiaba la selección
```

Ámbitos: `web`, `api`, `core`, `vision`, `worker`, `contracts`, `ci`, `docs`.

**El cuerpo del commit importa más que el título.** Explica *por qué*, no *qué* —el qué ya está
en el diff—. Si arreglaste algo, di qué estaba mal y cómo lo comprobaste.

## Antes de abrir el PR

```bash
cd "Fase 2/sistema"
make lint      # estilo
make tipos     # tipos
make test      # pruebas
```

Si el CI falla, **el PR no se fusiona**. No hay excepciones ni "lo arreglo después": el después
nunca llega y el siguiente que saque rama hereda el problema.

## Un PR, una cosa

Un PR que toca la bandeja, arregla un tipo y sube una dependencia es imposible de revisar y de
revertir. Si te das cuenta a mitad de camino de que son dos cosas, abre la segunda rama.

Tamaño sano: **menos de 400 líneas cambiadas**. Por encima de eso la revisión deja de encontrar
errores y pasa a ser un trámite.

## Revisar el trabajo del otro

Revisar no es dar el visto bueno. Es la última red antes de que algo roto llegue a `main`.

- Bájate la rama y **pruébala**, no la leas nomás.
- Si algo no se entiende, esa es una observación válida: el código lo vas a leer tú en la S15.
- Comenta sobre el código, no sobre la persona.
- Si está bien, aprueba y fusiona. No dejes un PR bueno esperando tres días.

`CODEOWNERS` pide revisión automática al dueño del área que tocaste.

## Las etiquetas

| Etiqueta | Para qué |
|---|---|
| `P0: critico` | Bloquea a alguien. Se atiende hoy |
| `P1: alto` | Esta semana |
| `P2: normal` | Cuando se pueda |
| `bloqueada` | No se puede avanzar. **Dilo en el grupo el mismo día** |
| `area: frontend` · `area: backend` · `area: vision` · `area: datos` | Quién lo toma |
| `fase 1` · `fase 2` · `fase 3` | Para armar las evidencias del portafolio |

## Cuando te bloqueas

Pon la etiqueta `bloqueada` en tu issue, escribe **en el issue** qué te frena, y dilo en el grupo
**el mismo día**. Un bloqueo callado de tres días es una semana perdida del proyecto: somos tres y
quedan once semanas.

## Lo que nunca se sube

`.gitignore` ya lo bloquea, pero conviene saber por qué:

- **Video de obra, pesos de modelos, datasets.** Pesan gigas y GitHub no es para eso.
- **Cualquier imagen con un rostro sin difuminar.** Es dato personal y el repo es público.
- **Credenciales**, tokens, `.env`. Si sube una, no basta con borrarla: hay que rotarla.

## El contrato

`Fase 2/sistema/contracts/openapi.yaml` es la frontera entre el backend y el frontend, y está
**congelado**. Eso no quiere decir intocable: quiere decir que **lo que rompe el trabajo del otro
se acuerda antes**. Añadir un campo opcional se hace y se avisa; renombrar o quitar uno se discute
en un PR aparte. Está todo en [`contracts/README.md`](../Fase%202/sistema/contracts/README.md).
