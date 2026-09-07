# apps/web — Interfaz de Guardián EPP

Responsables: **@miguelOrtega33** y **@laincs**.

## Estado

🟢 La bandeja de hallazgos y el visor de evidencia de la issue #11 están implementados con
React, Vite y TypeScript. El diseño aprobado sigue disponible en [`diseno/`](diseno/).

## Cómo trabajar sin esperar al backend

Esta es la razón de que el proyecto esté organizado así: **el frontend no depende de que el
modelo de visión funcione.**

1. El contrato de la API está congelado y vive en
   [`../../contracts/openapi.yaml`](../../contracts/openapi.yaml).
2. Se levanta Prism desde el contrato y se construye contra él.
3. Cuando el backend esté listo, se cambia la URL base. Nada más.

Si en algún momento el frontend está bloqueado esperando al backend, **algo se hizo mal** y hay
que avisarlo en la reunión semanal, no aguantarlo.

## Ejecutar el frontend

En una terminal, desde `Fase 2/sistema`:

```powershell
make mock
```

En otra terminal:

```powershell
cd apps/web
npm install
npm run dev
```

La interfaz queda en `http://127.0.0.1:5173` y el mock en `http://127.0.0.1:4010`.

## Pila utilizada

| | | Por qué |
|---|---|---|
| React + Vite | Base | Rápido, estándar, buena documentación |
| TypeScript | Tipos | El contrato OpenAPI genera los tipos automáticamente |
| CSS + `tokens.css` | Estilo | Respeta exactamente los tokens del diseño aprobado |
| TanStack Query | Datos | Caché, reintentos y estados de carga resueltos |
| TanStack Virtual | Tabla | Mantiene fluida la bandeja con muchos hallazgos |
| Vitest + Testing Library | Pruebas | Valida filtros, accesibilidad y atajos |

La pila final la decide el equipo de frontend. Lo que **no** es negociable son las reglas de
[`docs/producto/05-diseno-interfaz.md`](../../../../docs/producto/05-diseno-interfaz.md):
severidad con triple codificación, filtros en la URL, tabla virtualizada y sin muro de gráficos.

## Comprobar antes de abrir un PR

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
```

## Límites del contrato para la revisión

- Las evidencias del mock son imágenes sintéticas anonimizadas, no grabaciones reales.
- «Asignar» queda desactivado porque no existe un catálogo de responsables.
- No se dibujan cajas sobre la imagen: el contrato no entrega sus coordenadas.
- «Descartados» agrupa falso positivo y duplicado en el cliente, hasta los
  primeros 200 resultados. Para paginar esa vista falta un filtro agrupado en la API.
- La issue permanece abierta hasta que el compañero revise y apruebe el PR.
