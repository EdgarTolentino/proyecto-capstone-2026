# ADR-012 — Persistencia compartida en un quinto paquete: `gepp-bd`

**Estado:** propuesta · **Fecha:** 2026-09-07 · Se acepta al fusionar el PR que la introduce

## Contexto

ADR-007 fija cuatro paquetes y una regla de oro: `gepp-api` no importa `gepp-vision`; la API y
el trabajador "se comunican por la base de datos y la cola". Lo que no dice es **quién es dueño
del esquema**. El trabajador (`gepp-worker`) tiene que escribir `video`, `deteccion`, `hallazgo`,
`evidencia` y `notificacion`; la API tiene que leerlas todas y escribir `regla`,
`accion_correctiva` y `auditoria`. Sin decidirlo, el primer paquete de trabajo de la S5 (esquema y
migraciones) no puede empezar.

## Alternativas

| | Opción | A favor | En contra |
|---|---|---|---|
| A | Los modelos viven en `gepp-api` y el trabajador depende de `gepp-api` | Ningún paquete nuevo | El trabajador arrastra FastAPI; la frontera "API = HTTP" se disuelve y nada impide importar routers desde el trabajador |
| B | El trabajador no toca la base: envía resultados por HTTP a endpoints internos de la API | Un solo escritor; el trabajador es un cliente puro | Un segundo contrato que mantener; la ingesta depende de que la API esté arriba; autenticación entre procesos; el recálculo y la idempotencia quedan repartidos en dos lugares |
| **C** | **Quinto paquete `gepp-bd`**: modelos SQLAlchemy, migraciones Alembic y repositorios. Depende solo de `gepp-core`; `gepp-api` y `gepp-worker` dependen de él | Un dueño del esquema y sin HTTP interno; la regla de oro se conserva; las pruebas de persistencia se escriben una vez | Un paquete más en el espacio de trabajo y en `make tipos`; ADR-007 pasa a decir "cinco" |

## Decisión

Opción C.

```
gepp-core  <--  gepp-bd  <--  gepp-api
    ^              ^
    |              +------  gepp-worker  -->  gepp-vision  -->  gepp-core
```

Reglas:

- `gepp-bd` no importa `gepp-vision` ni FastAPI. Depende de `gepp-core`, SQLAlchemy, Alembic y el
  driver de PostgreSQL.
- Las migraciones viven en `gepp-bd/migraciones` y `make migrar` las aplica. Ningún módulo fuera
  de `gepp-bd` construye SQL.
- `deteccion` se inserta por lotes: una transacción por segundo de video, no por fila.
- `auditoria` se escribe solo a través de su repositorio, sin UPDATE ni DELETE.

## Consecuencias

- ADR-007 sigue vigente en su regla de oro; se anota que el espacio de trabajo tiene cinco
  paquetes y se actualiza la sección 4 de `00-arquitectura.md`.
- CI: `make tipos` y `pytest` incluyen el paquete; PostgreSQL entra como servicio de GitHub
  Actions para las pruebas marcadas `integration`.
- El recálculo sin GPU (ADR-004) queda en `gepp-api/servicios/recalculo.py`: lee `deteccion` a
  través de `gepp-bd` y usa el agregador de `gepp-core`, el mismo código que corre el trabajador.
