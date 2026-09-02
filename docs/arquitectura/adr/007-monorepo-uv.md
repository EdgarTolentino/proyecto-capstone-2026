# ADR-007 — Monorepo con espacio de trabajo `uv` y cuatro paquetes

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

Solo una de las tres máquinas tiene GPU. Las otras dos no pueden descargar 3 GB de CUDA para
levantar una API que no ejecuta ningún modelo.

## Decisión

Monorepo con espacio de trabajo `uv` y un único `uv.lock` versionado:

```
packages/gepp-core     dominio puro — sin torch, sin cv2
packages/gepp-vision   detector, seguidor, VLM      → depende de core
packages/gepp-api      FastAPI + SQLAlchemy         → depende de core, NO de vision
packages/gepp-worker   ingesta (carpeta v1 / RTSP v2) → depende de core + vision
apps/web               React + Vite
```

`torch` se declara como extras en conflicto: `uv sync --extra cpu` en las máquinas sin GPU y en
CI, `uv sync --extra cu126` en la máquina con GPU. **Mismo lockfile.**

## La regla de oro

**`gepp-api` no importa `gepp-vision`.** Se comunican por la base de datos y la cola.

Eso es lo que permite (a) que los dos portátiles sin GPU levanten la API completa, (b) que CI
corra sin GPU en segundos, y (c) que la v2 sea cambiar `gepp-worker` sin tocar nada más.

## Consecuencias

Más ceremonia inicial que un solo `requirements.txt`. A cambio, la frontera entre dominio,
visión y web queda impuesta por el gestor de dependencias y no por la buena voluntad: si alguien
importa `gepp_vision` desde `gepp_api`, la instalación falla.
