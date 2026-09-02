# ADR-001 — Arquitectura de dos etapas: el detector decide, el VLM describe

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

Un modelo de lenguaje visual (VLM) puede mirar un cuadro y decir "un trabajador sin casco junto a
un camión". Es tentador usarlo como clasificador de cumplimiento: elimina el etiquetado y el
entrenamiento. Pero cuesta 1–3 s por imagen y compite por los mismos 8 GB de VRAM que el detector.

## Decisión

Dos etapas con responsabilidades separadas:

- **Etapa 1** (barata, siempre encendida): detector afinado + seguidor + motor de reglas.
  **Produce el veredicto.**
- **Etapa 2** (cara, selectiva y asíncrona): el VLM redacta la descripción del hallazgo **ya
  confirmado**. Nunca crea, suprime ni cambia la severidad de un hallazgo.

## Por qué

- La medición disponible en 2026 es concluyente: un VLM pequeño con el detector como anclaje
  alcanza cerca de **F1 0,51** clasificando peligros de construcción, pero **BERTScore 0,82**
  describiéndolos. Sirve para redactar, no para decidir.
- Un sistema cuyas alertas dependen de un VLM no es **auditable**: no se puede explicar por qué
  se disparó. Un cliente minero lo va a exigir.
- Si el VLM está en la ruta crítica, cargarlo deja al detector sin VRAM justo en el momento en
  que hay un hallazgo — es decir, justo cuando el sistema no puede fallar.

## Consecuencias

El VLM es un consumidor más de la cola de eventos, con su propio presupuesto de memoria. La
alerta sale con la Etapa 1 en cientos de milisegundos; la descripción llega segundos después como
un `update` del hallazgo. Hay que medir la latencia real del VLM en la máquina del equipo antes
de comprometerlo en el alcance.
