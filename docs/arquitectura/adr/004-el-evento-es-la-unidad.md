# ADR-004 — El evento es la unidad, y se persisten las detecciones crudas

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

Una hora de video a 5 fps son 18.000 cuadros. Si cada cuadro con un incumplimiento fuera un
registro, un turno de 8 horas produciría cientos de miles de filas y otras tantas alertas. El
prevencionista abandonaría la herramienta el primer día.

## Decisión

1. La unidad del sistema es el **hallazgo**: una persona (track efímero), un tipo de
   incumplimiento, una zona, un inicio y un fin.
2. Además del hallazgo, se persisten las **detecciones crudas por track**: cuadro, timestamp,
   clase, confianza, caja.

## Por qué persistir lo crudo

Son filas, no video: el costo es despreciable. Compra tres cosas:

- **Recalcular reglas sin GPU.** Con una sola máquina con GPU, reprocesar el corpus cada vez que
  se ajusta un umbral es la ruta crítica que mata el cronograma en las últimas semanas.
- **El simulador "¿y si…?"**: *"esta regla habría generado 47 hallazgos el mes pasado"*. Es lo que
  convierte el editor de reglas en producto y permite calibrar sin publicar.
- **Auditoría**: poder explicar, cuadro por cuadro, por qué se disparó un hallazgo.

## Consecuencias

El agregador (detección → evento) es lógica de dominio pura en `gepp-core`: se prueba en CI sin
GPU ni video, con detecciones sintéticas. Es la pieza más evaluable del proyecto y también la
más fácil de testear bien.
