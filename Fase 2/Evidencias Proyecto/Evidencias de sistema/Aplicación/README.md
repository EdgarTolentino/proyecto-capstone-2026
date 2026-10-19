# Aplicación

El código fuente **no se duplica aquí**. Vive en [`Fase 2/sistema/`](../../../sistema/).

| Entrega | Etiqueta de git | Fecha | Nota |
|---|---|---|---|
| Avance S10 | `v0.1.0-avance` | 2026-10-13 | Evaluación de avance de la Fase 2: presentación, diario, capturas y datos de ejemplo |
| Final S15 | `v1.0.0` | _pendiente_ | |

Para reproducir la entrega de avance:

```bash
git clone https://github.com/EdgarTolentino/proyecto-capstone-2026.git
cd proyecto-capstone-2026
git checkout v0.1.0-avance
```

`v1.0.0` es la etiqueta de la entrega final de la S15; todavía no existe.

## Capturas

> **Menú y Guía: registros históricos.** Los informes del 18 y 19 de octubre muestran
> una interfaz anterior, con la Guía en el menú de usuario y un contacto ficticio ya retirado.
> No acreditan la versión corregida de #194 y #196, que ofrece Ayuda en «?» y acceso al PDF.

### Evidencia final pendiente

1. Integrar #194 y luego #196; registrar el commit resultante de main.
2. Actualizar la base de #195 a main y ejecutar la suite web completa sobre su último commit.
3. Repetir las capturas en escritorio y ventana estrecha desde Ayuda «?», incluyendo el PDF,
   las cuatro tarjetas, el foco y los cierres.
4. Repetir Hallazgos → cerrar visor → abrir Guía → Atrás: comprobar c/x sin triage,
   Tab dentro de la Guía y Escape cerrando solo la Guía.
5. Inspeccionar las imágenes, validar enlaces y publicar salidas sin rutas personales.

### Capturas históricas

La [prueba en Windows y Microsoft Edge del 19-oct-2026](2026-10-19-menu-guia-windows/verificacion.html)
incluye 18 pantallazos, cada uno con prueba, resultado esperado, resultado observado y estado,
además del guion reproducible y los resultados estructurados. Se realizó contra el **mock del
contrato**, en 1440 × 1000 y 390 × 844: el recorrido pasó, Tab alcanzó Guía rápida y Finalizar
mostró un contorno de foco sólido de 2 px. La salida de la suite web está adjunta al informe.

**Actualización de Safari (19-oct-2026):** el usuario confirmó que ya se contrastó y funcionó.
Se conserva lo observado en la sesión histórica de WebKit, pero el contraste con Safari ya no
está pendiente. La confirmación del usuario es independiente de la nueva prueba en Windows.

La [verificación del menú y Guía rápida del 18-oct-2026](2026-10-18-menu-guia/verificacion.html)
incluye 15 capturas con pasos, resultados y comentarios. Se ejecutó en WebKit de Playwright
contra la API real local con datos de demo, en 1440 × 1000 y 390 × 844. Registra las
observaciones de navegación con Tab/Option+Tab y del foco visual de Finalizar; no reemplaza
la revisión independiente del diff ni una prueba en la aplicación Safari del usuario.

| Archivo | Qué muestra |
|---|---|
| [01-menu-escritorio.png](2026-10-18-menu-guia/output/playwright/01-menu-escritorio.png) | **01. Menú de usuario en escritorio**. Prueba: Pulsar el botón de usuario. Esperado: Nombre, rol y Guía rápida visibles. Observado: Se muestran Prevencionista de turno, rol prevencionista y el acceso a la guía. Estado: Pasó |
| [02-escritorio-paso-1.png](2026-10-18-menu-guia/output/playwright/02-escritorio-paso-1.png) | **02. Abrir la guía**. Prueba: Pulsar Guía rápida. Esperado: Primera tarjeta, contador 1 de 4 y Anterior deshabilitado. Observado: Se presenta Procesa un video y el botón Anterior está deshabilitado. Estado: Pasó |
| [03-escritorio-paso-2.png](2026-10-18-menu-guia/output/playwright/03-escritorio-paso-2.png) | **03. Segunda tarjeta**. Prueba: Pulsar Siguiente desde la primera tarjeta. Esperado: Revisa los hallazgos, 2 de 4. Observado: Texto y contador correctos, sin cambiar de sección ni URL. Estado: Pasó |
| [04-escritorio-anterior.png](2026-10-18-menu-guia/output/playwright/04-escritorio-anterior.png) | **04. Retroceso**. Prueba: Pulsar Anterior desde la segunda tarjeta. Esperado: Volver a 1 de 4. Observado: Regresa a Procesa un video y Anterior vuelve a quedar deshabilitado. Estado: Pasó |
| [05-escritorio-paso-3.png](2026-10-18-menu-guia/output/playwright/05-escritorio-paso-3.png) | **05. Tercera tarjeta**. Prueba: Avanzar hasta la tercera tarjeta. Esperado: Valida la evidencia, 3 de 4. Observado: Se explica el permiso de evidencia y la necesidad de validación humana. Estado: Pasó |
| [06-escritorio-paso-4.png](2026-10-18-menu-guia/output/playwright/06-escritorio-paso-4.png) | **06. Última tarjeta**. Prueba: Pulsar Siguiente desde la tercera tarjeta. Esperado: Contacto de demostración, 4 de 4 y Finalizar. Observado: Se ve el teléfono con XXXX, la nota Número ficticio y Finalizar. Siguiente no está presente. Estado: Pasó |
| [07-teclado-foco.png](2026-10-18-menu-guia/output/playwright/07-teclado-foco.png) | **07. Foco dentro del diálogo**. Prueba: Enfocar Cerrar y pulsar Shift+Tab; después Tab. Esperado: El foco debe permanecer dentro del diálogo y ser reconocible visualmente. Observado: Shift+Tab lleva el foco DOM a Finalizar y Tab vuelve a Cerrar. En esta sesión WebKit, Finalizar tiene focusVisible=false y outline sin estilo: la captura no muestra un indicador de foco distinguible. Estado: Observación histórica; contraste con Safari confirmado por el usuario el 19-oct-2026 |
| [08-cierre-escape.png](2026-10-18-menu-guia/output/playwright/08-cierre-escape.png) | **08. Cerrar con Escape**. Prueba: Pulsar Escape con el diálogo abierto. Esperado: Cerrar el diálogo y devolver el foco al botón de usuario. Observado: Se comprobó la desaparición del diálogo y document.activeElement en el botón de usuario. La imagen muestra el panel tras cerrar. Estado: Pasó |
| [09-reapertura.png](2026-10-18-menu-guia/output/playwright/09-reapertura.png) | **09. Reabrir con teclado**. Prueba: Abrir el menú, usar Option+Tab y Enter. Esperado: Abrir nuevamente en 1 de 4. Observado: Option+Tab llegó a Guía rápida y Enter abrió la primera tarjeta. Tab solo había omitido los botones y cerrado el menú al mover el foco al filtro Obra. Estado: Pasó con condición de teclado |
| [10-cierre-finalizar.png](2026-10-18-menu-guia/output/playwright/10-cierre-finalizar.png) | **10. Finalizar el recorrido**. Prueba: Avanzar hasta 4 de 4 y pulsar Finalizar. Esperado: Cerrar y devolver el foco al usuario. Observado: El diálogo desaparece y el foco DOM vuelve al botón de usuario. Estado: Pasó |
| [11-menu-estrecho.png](2026-10-18-menu-guia/output/playwright/11-menu-estrecho.png) | **11. Menú en ventana estrecha**. Prueba: Cambiar a 390 × 844 y abrir el menú. Esperado: Acceso legible y dentro del ancho visible. Observado: Nombre, rol y Guía rápida se ven dentro del panel; la cabecera usa avatar compacto. Estado: Pasó |
| [12-estrecho-paso-1.png](2026-10-18-menu-guia/output/playwright/12-estrecho-paso-1.png) | **12. Primera tarjeta estrecha**. Prueba: Abrir Guía rápida en 390 × 844. Esperado: 1 de 4 y controles completos sin desborde del diálogo. Observado: Texto y botones se ven completos. Diálogo entre x=16 y x=374; scrollWidth=clientWidth=356. Estado: Pasó |
| [13-estrecho-paso-2.png](2026-10-18-menu-guia/output/playwright/13-estrecho-paso-2.png) | **13. Segunda tarjeta estrecha**. Prueba: Pulsar Siguiente. Esperado: 2 de 4 y texto legible. Observado: Contenido dentro del viewport y sin desborde horizontal del diálogo. Estado: Pasó |
| [14-estrecho-paso-3.png](2026-10-18-menu-guia/output/playwright/14-estrecho-paso-3.png) | **14. Tercera tarjeta estrecha**. Prueba: Pulsar Siguiente. Esperado: 3 de 4 y texto legible. Observado: Mensaje de validación humana y ambos controles visibles, sin desborde horizontal del diálogo. Estado: Pasó |
| [15-estrecho-paso-4.png](2026-10-18-menu-guia/output/playwright/15-estrecho-paso-4.png) | **15. Última tarjeta estrecha**. Prueba: Pulsar Siguiente. Esperado: 4 de 4, contacto ficticio y Finalizar visibles. Observado: Contenido dentro del viewport. Después se pulsó Cerrar y se comprobó el retorno del foco al usuario. Estado: Pasó |
| `2026-09-22-api-real-bandeja.png` | La bandeja de `apps/web` contra la **API real** (PT-09), con el hallazgo que produjo `make demo` sobre el video sintético CAM 03 |
| `2026-09-22-api-real-visor.png` | El visor del mismo hallazgo: recorte con la cabeza pixelada, línea de tiempo y botones de triage |
| `2026-09-28-iconos-epp-faltante.png` | La bandeja contra el mock del contrato, con iconos accesibles de EPP faltante y un hallazgo al que le faltan casco y chaleco |
| `2026-09-28-listado-reglas.png` | La pantalla de Reglas contra el mock del contrato, con filtro por área y el listado de nombre, área, estado y versión |
| `2026-10-01-panel-general-completo.png` | Panel general cargado contra el mock del contrato: indicadores, tendencia, ranking de EPP, críticos recientes, cobertura y filtros |
| `2026-10-01-panel-general-filtros.png` | Panel con obra, periodo del 1 al 30 de septiembre de 2026 y turno A seleccionados |
| `2026-10-01-navegacion-a-hallazgos.png` | Bandeja abierta desde un indicador; conserva fecha y turno, y no arrastra el filtro de obra que la bandeja no admite |
| `2026-10-06-cola-videos.png` | Cola de videos (#117) contra el mock del contrato: archivo, cámara, estado, intentos y motivo del error (solo en `error` y `reintentando`), con «Cargar más videos». El único video viene del ejemplo genérico de Prism |
| `2026-10-06-reprocesar-video.png` | Cola de videos (#118) con el permiso `editar_reglas`: columna «Acciones» y botón «Reprocesar» solo en el video en `error`; el `en_cola` muestra «—». Para la captura, un proxy local delante de Prism agregó `editar_reglas` a `/yo` (el ejemplo del contrato no lo trae) y una copia del video de ejemplo en estado `error`; el resto es Prism |
| `2026-10-12-pedido-procesando-con-avance.png` | Cola de videos contra la **API real** y el modelo entrenado: un video pedido desde la web (#154-#162) en estado «Procesando», con barra de avance, velocidad, conteo del cuadro actual y la vista en vivo del modelo (en esta captura se ve pixelada) |
| `2026-10-12-vista-en-vivo-modelo.png` | La vista en vivo del modelo: cajas de persona (amarillo) y casco (verde) sobre el video de prueba. Los rostros están tapados y el nombre de la empresa en el chaleco se pixeló para esta captura |

### Nota sobre los datos del mock de Prism

`2026-10-01-panel-general-completo.png` y `2026-10-01-panel-general-filtros.png` muestran la
respuesta simulada por Prism desde el contrato OpenAPI; no muestran datos del backend productivo.
En esa muestra, «Hallazgos abiertos» aparece como `0 %` y «Hallazgos críticos recientes» incluye
un hallazgo de severidad «Baja». Son inconsistencias del mock generado: el ejemplo genérico de
`unidad` es `%` aunque «Hallazgos abiertos» sea un conteo, y Prism no ejecuta la lógica que
relaciona los campos ni la regla del endpoint. Por eso estos valores no deben interpretarse como
una medición real ni como el comportamiento esperado del backend.

En el backend, `/panel` construye `criticos_recientes` solo con hallazgos de severidad 4. Esto se
comprueba en `Fase 2/sistema/packages/gepp-api/src/gepp_api/servicios/panel.py` y en
`test_el_panel_cumple_el_contrato_y_cuadra_con_los_datos`, que verifica que todos los elementos
devueltos tengan severidad 4. Se conserva la captura para dejar constancia del recorrido visual
contra el mock y de sus límites, no como evidencia de datos productivos.

### Origen del video

La referencia a video sintético aplica únicamente a `2026-09-22-api-real-bandeja.png` y
`2026-09-22-api-real-visor.png`: esas capturas muestran el hallazgo creado por `make demo` a partir
del video sintético CAM 03, con detector simulado. Las capturas del 28 de septiembre usan el mock
del contrato y las del panel del 1 de octubre usan Prism; estas últimas no provienen de ese video.
El detalle del dataset está en `docs/producto/07-datasets.md`.

Las dos capturas del 12 de octubre muestran el **video de prueba** (lote 3 de
`07-datasets.md`), publicado en YouTube el 2018-09-18 por el canal de un vendedor de cámaras de
seguridad: <https://www.youtube.com/watch?v=GPCHfE_-XQE>. El video no declara licencia de reutilización:
no está en el repositorio y estos dos cuadros se citan con fines académicos, como evidencia del
procesamiento. No se usa para entrenar.

## Validación del panel general · 2 de octubre de 2026

Las capturas se tomaron en Windows con la web local y Prism sirviendo ejemplos del contrato
OpenAPI en `http://127.0.0.1:4010`. Son datos de demostración y no representan datos de una
obra real ni de la API productiva.

| Prueba | Resultado |
|---|---|
| Abrir `/` y cargar el panel con indicadores, tendencia, ranking, críticos recientes y cobertura | Correcta; contenido del mock visible |
| Filtrar por obra, desde, hasta y turno A | Correcta; controles seleccionados y URL con `obra_id`, `desde`, `hasta` y `turno` |
| Navegar desde «Hallazgos abiertos» a la bandeja | Correcta; conserva `desde`, `hasta` y `turno`, y omite `obra_id` |
| Volver al panel desde la navegación principal | Correcta; el selector de obra, las fechas y el turno vuelven a mostrar sus valores, y `/panel` se consulta con los mismos filtros. Comprobado por `usa la raíz como panel general y permite volver a la bandeja` en `src/App.test.tsx` |
| Vitest (`npm test`) | 16 archivos y 71 pruebas aprobados al 2-oct; al 13-oct: 23 archivos y 337 pruebas |
| TypeScript (`npm run typecheck`) | Aprobado |
| ESLint (`npm run lint`) | Aprobado sin advertencias |
| Build de producción (`npm run build`) | Aprobado; Vite transformó 1958 módulos al 2-oct; al 13-oct: 1969 módulos |
| Pruebas por mutación | Se inyectaron defectos temporales en navegación, fechas inválidas, límite exclusivo, rango por defecto, permisos 403, conservación de datos, roles accesibles y variación cero; cada test correspondiente falló. Se restauró el código y la corrida focalizada final aprobó 8 archivos y 40 pruebas |

La consola del navegador registró únicamente `404` para `/favicon.ico`; no impidió cargar ni
usar el panel. La comprobación visual usó el mock del contrato, por lo que no valida disponibilidad
del backend productivo. Los tests de integración verifican el estado visible de los filtros y la
consulta solicitada al volver al panel; la captura de navegación documenta el paso hacia Hallazgos.
