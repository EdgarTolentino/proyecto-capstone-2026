# ADR-003 — FastAPI + React en lugar de Django + HTMX

**Estado:** aceptada · **Fecha:** 2026-09-02 · **Revierte** la propuesta inicial del anteproyecto

## Contexto

La propuesta original planteaba Django con HTMX: un solo proceso, menos piezas, más rápido para
una persona sola. Es la elección correcta… para una persona sola.

Aquí hay **tres**, y dos de ellas se dedican exclusivamente al frontend.

## Decisión

**Backend:** FastAPI + SQLAlchemy + PostgreSQL, con OpenAPI generado.
**Frontend:** React + Vite en `apps/web`, construido contra el contrato y un servidor simulado.

## Por qué

El criterio que decide no es técnico sino **organizacional**: con Django + HTMX las plantillas
viven dentro del backend, de modo que los dos compañeros de frontend no pueden avanzar hasta que
Edgar tenga vistas funcionando. En un proyecto de 18 semanas con dependencia de un modelo que
tarda semanas en existir, eso es fatal.

Con un contrato OpenAPI congelado en la S5 y un servidor simulado, el frontend construye las ocho
pantallas del alcance mínimo desde la S6, en máquinas sin GPU, sin esperar a nadie.

Beneficio adicional: un trabajo de CI exporta `openapi.json` desde FastAPI y **falla si difiere
del contrato versionado**. El contrato deja de ser un acuerdo verbal.

## Consecuencias

Más piezas que un monolito y dos ecosistemas de dependencias. Se acepta porque compra
paralelismo, que es el recurso escaso del proyecto. Requiere disciplina: cambiar el contrato es
un PR que rompe CI a propósito y obliga a avisar al equipo web.
