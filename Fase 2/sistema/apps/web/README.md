# apps/web — Interfaz de Guardián EPP

Responsables: **@miguelOrtega33** y **@laincs**.

## Estado

🟡 Carpeta preparada, sin código todavía. El diseño se genera primero (ver
[`PROMPT-DISENO.md`](PROMPT-DISENO.md)), se valida con el equipo, y recién entonces se
implementa.

## Cómo trabajar sin esperar al backend

Esta es la razón de que el proyecto esté organizado así: **el frontend no depende de que el
modelo de visión funcione.**

1. El contrato de la API se congela en la **S5** y vive en
   [`../../contracts/openapi.json`](../../contracts/).
2. Se levanta un servidor simulado contra ese contrato (Prism o MSW) y se construye contra él.
3. Cuando el backend esté listo, se cambia la URL base. Nada más.

Si en algún momento el frontend está bloqueado esperando al backend, **algo se hizo mal** y hay
que avisarlo en la reunión semanal, no aguantarlo.

## Pila propuesta

| | | Por qué |
|---|---|---|
| React + Vite | Base | Rápido, estándar, buena documentación |
| TypeScript | Tipos | El contrato OpenAPI genera los tipos automáticamente |
| Tailwind + shadcn/ui | Estilo | Componentes accesibles sin reinventar tablas ni diálogos |
| TanStack Query | Datos | Caché, reintentos y estados de carga resueltos |
| TanStack Table | Tablas | Virtualización, que la bandeja necesita sí o sí |
| Recharts | Gráficos | Suficiente para líneas, barras y minigráficos |

La pila final la decide el equipo de frontend. Lo que **no** es negociable son las reglas de
[`docs/producto/05-diseno-interfaz.md`](../../../../docs/producto/05-diseno-interfaz.md):
severidad con triple codificación, filtros en la URL, tabla virtualizada y sin muro de gráficos.

## Primeros pasos, en orden

1. Leer [`docs/producto/05-diseno-interfaz.md`](../../../../docs/producto/05-diseno-interfaz.md).
2. Generar el diseño con [`PROMPT-DISENO.md`](PROMPT-DISENO.md) y revisarlo en equipo.
3. Montar el proyecto Vite y el servidor simulado.
4. Construir en este orden: **bandeja → visor → ingesta → panel → reglas**.
