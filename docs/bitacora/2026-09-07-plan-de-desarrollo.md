# Bitácora · 7 de septiembre de 2026 — Plan de desarrollo y lámina de arquitectura

Víspera de la exposición (martes 8, S4). Además de las correcciones de la Guía (#15, #20, #21) y
las revisiones del frontend (#16, #17), se cerró lo que faltaba para arrancar la S5 del lado de
visión y backend.

## 1. Lo que faltaba

Miguel tenía en #11 instrucciones completas para el frontend. Del lado de visión, ingesta, API y
datos había arquitectura (`00-arquitectura.md` y once ADR) y la suma de horas (V9), pero
**ninguna tarea de construcción tenía issue ni orden**: los issues de Edgar eran verificaciones
(#3, #6, #7, #10). `gepp-vision` tenía solo los puertos, `gepp-api` estaba vacío y nadie era dueño
del esquema de la base de datos.

## 2. Lo que se hizo

- `docs/producto/09-plan-de-desarrollo-vision.md`: 18 paquetes de trabajo entre la S5 y la S15
  con módulos, horas (las 184 de V9 sin cambiar el total), definición de terminado, calendario
  (Fiestas Patrias en la S5, feriado en la S9) y ruta crítica.
- ADR-012, en estado de propuesta: quinto paquete `gepp-bd` como dueño del esquema y de las
  migraciones. Se decide al fusionar el PR.
- Un issue por paquete de trabajo (#25 a #41), asignados a Edgar, y los hitos H2, H3 y H4 con fecha;
  #3, #7 y #10 entran al hito H2.
- Lámina 8 de la presentación rehecha: cuatro filas —entrada, visión, decisión y datos, servicios
  e interfaz— donde cada caja nombra la tecnología y dice en una frase qué hace, más una columna
  de ingeniería. Notas y guion de ensayo actualizados.
- PR #22 de Lian: quitó los marcadores "ajustar con tus palabras" de Miguel y de Lian editando el
  `.docx` en Word. El cambio se llevó a `contenido_fase1.py` y la Guía se regeneró desde el
  generador, que es la fuente; el PR queda para cerrar como reemplazado.

## 3. Pendiente

- Decidir ADR-012 al fusionar el PR del plan.
- Reunión del 8 de septiembre: autorización para grabar antes del 18, sesiones de etiquetado
  desde la S6, reparto de las cuatro pantallas restantes con Lian, `AGENTS.md` en la raíz.
- Dónde viven los clips de referencia del anillo 2 de pruebas (decisión de la S6).
