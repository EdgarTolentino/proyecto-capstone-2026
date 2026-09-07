# V9 · Las horas de Edgar contra las once semanas

> Cierra el issue #6. Se suma la carga de Edgar entre la S5 y la S15 y se decide el alcance
> comprometido de la v1 **antes** de escribir la Guía 1.5. Estimación clásica, sin descontar
> la asistencia de herramientas; al final se dice qué parte se comprime y qué parte no.

## 1. Lo que ya no cuenta

Hecho en S3-S4, fuera de la suma: repositorio y gobernanza, CI con matriz e higiene de
licencias, 11 ADR, `gepp-core` con 24 pruebas y 96,7 % de cobertura, contrato OpenAPI congelado
con servidor simulado, diseño de interfaz aprobado con tokens extraídos.

## 2. La suma, tal como estaba planificado

Horas base de Edgar, por semana del plan. Entre paréntesis lo que fundamenta cada número.

| Sem | Tarea | Horas |
|---|---|---|
| S5 | Esquema de base de datos, migraciones y modelos (el modelo ya está diseñado en `01-modelo-de-datos.md`) | 10 |
| S5 | Autorización de la obra, consentimientos y grabación de 20-30 min (una tarde más el papeleo) | 6 |
| S6 | Definición de clases, protocolo de etiquetado y herramienta | 6 |
| S6-S8 | **Etiquetado**: 2.500 imágenes en tres rondas. Con pre-etiquetado automático y solo corrección, ~15 s por imagen → 10,5 h por ronda | 31 |
| S7 | Ingesta: carpeta vigilada, cola de trabajos, persistencia de detecciones crudas | 16 |
| S8 | Afinado de RF-DETR y arnés de evaluación a nivel de evento | 20 |
| S9 | Integración extremo a extremo | 20 |
| S10 | Evaluación de avance: demo e informe (parte de Edgar) | 8 |
| S11 | Motor de reglas: persistencia, versionado, zonas y API (el núcleo ya existe) | 12 |
| S12 | Alertas: canal, acuse de recibo, escalamiento y supresión de repetidos | 16 |
| S12 | Modelo v2: aprendizaje activo sobre los fallos del v1 | 12 |
| S13 | Analítica: consultas agregadas y endpoints | 10 |
| S13 | Etapa 2: descripción con modelo de lenguaje visual | 14 |
| S14 | Endurecimiento: pruebas, rendimiento, manual técnico | 16 |
| S15 | Congelar, informe final y presentación (parte de Edgar) | 12 |
| S5-S15 | Transversal: reunión semanal, revisión de PR del frontend, gestión de issues (3 h/sem) | 33 |
| | **Base** | **242** |
| | **Con holgura del 20 %** | **290** |

**290 h en 11 semanas son 26 h por semana**, encima de un trabajo de 40 h. No cuadra. La
respuesta no es "echarle más horas": es cambiar el alcance con números en la mano.

## 3. Las palancas, en el orden del issue

| # | Palanca | Ahorro base | Qué cambia |
|---|---|---|---|
| 1 | **La v1 cierra con casco y chaleco.** Ya era restricción dura en la arquitectura; ahora es compromiso escrito | 11 h | Menos clases que corregir en el etiquetado y una evaluación más simple |
| 2 | **Etiquetado entre los tres integrantes**, en sesiones conjuntas con protocolo escrito | 15 h | Edgar queda con un tercio de las rondas |
| 3 | **La Etapa 2 (VLM) sale del alcance comprometido** y queda como extensión demostrada; el modelo v2 se reduce a una ronda de corrección | 20 h | Nada del sistema depende del VLM: por diseño describe, no decide |
| 4 | *(adicional)* Alertas de v1 por un solo canal, con acuse y supresión; el escalamiento multinivel queda diseñado. Las consultas de analítica las construye quien hace el tablero | 12 h | Se evita duplicar trabajo entre backend y frontend |

| Escenario | Base | Con holgura | Por semana |
|---|---|---|---|
| Plan original | 242 | 290 | 26,4 |
| Palancas 1-3 | 196 | 235 | 21,4 |
| Palancas 1-4 | 184 | 221 | **20,1** |

## 4. Lo que se comprime y lo que no

La estimación es clásica. Con las herramientas con que se trabaja este repositorio, lo que es
código (base de datos, ingesta, API, alertas, analítica, documentación) históricamente va dos o
tres veces más rápido. Lo que **no** se comprime, porque depende de datos, de GPU o de personas:

| Piso incompresible | Horas |
|---|---|
| Grabación y papeles | 6 |
| Etiquetado (un tercio) | 8 |
| Entrenamiento y evaluación honesta | 20 |
| Integración extremo a extremo y depuración | 20 |
| Pruebas y endurecimiento | 16 |
| **Total** | **70** |

Con todo lo demás comprimido a la mitad, la carga realista queda entre **12 y 15 h por
semana**. Es exigente pero posible, y solo si las palancas 1-3 se adoptan hoy.

## 5. Decisión

- **Alcance comprometido de v1: casco y chaleco.** Arnés, guantes y lentes son extensión
  demostrada si el dataset alcanza.
- **El etiquetado es tarea de equipo**, con sesiones fijadas en el calendario desde la S6.
- **El VLM no es requisito.** Se demuestra en S13 si hay holgura; si no, se presenta como diseño.
- **Alertas v1: un canal, acuse y supresión.** Escalamiento multinivel documentado, no construido.
- Las horas semanales reales de Edgar se registran en el issue #6 al cerrarlo, y el plan se
  revisa en la reunión de la S6 con el primer lote etiquetado medido.
