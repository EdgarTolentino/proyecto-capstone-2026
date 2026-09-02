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

## Nota de conciliación (2026-09-02)

La investigación arrojó dos posturas opuestas sobre el papel del modelo de lenguaje visual. Una
sostiene que solo debe **describir** (evidencia: F1 en torno a 0,51 clasificando peligros incluso
con el detector como anclaje, frente a BERTScore 0,82 describiéndolos; y mediciones de recall
68-89 % con precisión de apenas 2,7-20,4 % en inspección de seguridad en obra). La otra propone
usarlo como **verificador adversarial** sobre hallazgos dudosos, para reducir falsos positivos.

**Resolución:** el rol por defecto es **describir**, y esta decisión no cambia. La verificación
sobre hallazgos dudosos —confianza entre 0,35 y 0,65— entra como **experimento medido en la
S13**, no como parte del camino crítico. Si en el conjunto de validación mejora la precisión sin
bajar el recall, se activa como **señal sugerente** ("revisar con prioridad"), nunca como
supresor automático de hallazgos.

Así se aprovecha la idea sin romper la auditabilidad: **ningún hallazgo desaparece porque un
modelo generativo lo haya decidido.**
