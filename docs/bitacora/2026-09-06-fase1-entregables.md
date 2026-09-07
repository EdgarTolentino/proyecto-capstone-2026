# Bitácora · 6 de septiembre de 2026 — V9 decidida y entregables de la Fase 1

La exposición grupal es el **martes 8 de septiembre (S4)**. Hoy se cerró el alcance con números
y se produjeron todos los entregables de la Fase 1.

## 1. V9: las horas contra las once semanas

Se sumó la carga de Edgar entre la S5 y la S15: **290 h con holgura, 26 h por semana**, encima
de un trabajo de 40 h. No cabía. Se adoptaron las tres palancas del issue #6 más una cuarta:

| Palanca | Decisión |
|---|---|
| Clases | La v1 compromete **casco y chaleco**. Arnés, guantes y lentes son extensión demostrada |
| Etiquetado | Tarea de los tres integrantes, en sesiones conjuntas desde la S6 |
| VLM | Fuera del alcance comprometido; se demuestra en S13 si hay holgura |
| Alertas y analítica | Un canal con acuse y supresión; el escalamiento multinivel queda diseñado. Las consultas de analítica las construye quien hace el tablero |

Con eso la carga baja a **221 h**, y descontando lo que las herramientas comprimen, a **12-15 h
semanales**. El piso incompresible son 70 h: grabación, etiquetado, entrenamiento, integración y
pruebas. Detalle en `docs/producto/08-verificacion-v9-horas.md`.

## 2. Lo que exige la pauta 1.6 y que no estaba a la vista

- Las **cuatro competencias del perfil de egreso** vienen literales en la pauta: desarrollar
  software, construir modelos de datos, pruebas de certificación y gestionar proyectos. Los
  indicadores de calidad 1.1 a 4.3 son lo que el docente marca para el IL 1.5 (20 %).
- La Guía 1.5 debe ir en **formato de informe técnico**: portada, índice, abstract en español e
  inglés, desarrollo, conclusiones individuales en inglés, reflexión en inglés, bibliografía.
- La exposición dura **15 minutos**, es grupal y se evalúa la participación equitativa (10 %).

## 3. Entregables producidos

| Archivo | Dónde | Estado |
|---|---|---|
| Guía 1.5 (16 páginas, sobre la plantilla del docente) | `Fase 1/Evidencias Grupales/` | Lista salvo marcadores amarillos |
| Presentación Proyecto.pptx (8 láminas, notas con guion y tiempos) | `Fase 1/Evidencias Grupales/` | Lista |
| 1.1, 1.2 y 1.3 de Edgar | `Fase 1/Evidencias Individuales/` | Borradores para ajustar |
| V9 | `docs/producto/08-verificacion-v9-horas.md` | Cerrada, falta registrar las horas reales en #6 |

Los generadores viven fuera del repositorio, en `~/proyectos/edgar_duoc/_generadores/`
(`contenido_fase1.py` es la única fuente de los textos; `guia_1_5.py` y `presentacion_fase1.py`
rellenan las plantillas).

**Regla decidida el 6-sep: los RUT no entran al repositorio**, que es público. En el repo los
documentos llevan el marcador `[[RUT]]`; la copia con RUT para la plataforma del docente se
genera fuera del repo con `_generadores/entrega_con_rut.py`, leyendo `_generadores/privado.py`.

**Marcadores pendientes en los documentos:** apellido de Liân, RUT de los tres, sede, docente,
año de ingreso, y los párrafos de intereses profesionales y conclusiones de Miguel y Liân, que
están redactados como borrador para que cada uno los haga suyos.

## 4. Estado del equipo en GitHub

Ambos compañeros aceptaron la invitación con permiso de escritura. **Ninguno ha tocado el
repositorio**: el issue #11 no tiene comentarios ni ramas desde que se asignó el 4-sep.

## 5. Lo que queda, en orden

| | Qué | Quién | Cuándo |
|---|---|---|---|
| 🔴 | Completar marcadores y ensayar la exposición (15 min, tres voces) | Equipo | Antes del martes |
| 🔴 | Miguel y Liân: sus 1.1, 1.2 y 1.3, y personalizar sus párrafos de la Guía | Miguel, Liân | Antes del martes |
| 🟠 | Registrar las horas semanales reales en #6 y cerrarlo | Edgar | S4 |
| 🟠 | Presentar ADR-011, el contrato y el reparto de etiquetado al equipo | Equipo | Reunión de la S4 |
| 🔴 | Autorización, consentimientos y grabación de 20-30 min | Equipo | S5 |
| 🟠 | #7 reescrito para construcción: pedir la matriz de EPP por área a la obra | Edgar | S5 |
| 🟠 | V2 con la cámara real de la obra | Edgar | S5 |
