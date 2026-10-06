# Aplicación

El código fuente **no se duplica aquí**. Vive en [`Fase 2/sistema/`](../../../sistema/).

| Entrega | Etiqueta de git | Fecha | Nota |
|---|---|---|---|
| Avance S10 | `v0.1.0-avance` | _pendiente_ | |
| Final S15 | `v1.0.0` | _pendiente_ | |

Para reproducir una entrega exacta:

```bash
git clone https://github.com/EdgarTolentino/proyecto-capstone-2026.git
cd proyecto-capstone-2026
git checkout v1.0.0
```

## Capturas

| Archivo | Qué muestra |
|---|---|
| `2026-09-22-api-real-bandeja.png` | La bandeja de `apps/web` contra la **API real** (PT-09), con el hallazgo que produjo `make demo` sobre el video sintético CAM 03 |
| `2026-09-22-api-real-visor.png` | El visor del mismo hallazgo: recorte con la cabeza pixelada, línea de tiempo y botones de triage |
| `2026-09-28-iconos-epp-faltante.png` | La bandeja contra el mock del contrato, con iconos accesibles de EPP faltante y un hallazgo al que le faltan casco y chaleco |
| `2026-09-28-listado-reglas.png` | La pantalla de Reglas contra el mock del contrato, con filtro por área y el listado de nombre, área, estado y versión |
| `2026-10-01-panel-general-completo.png` | Panel general cargado contra el mock del contrato: indicadores, tendencia, ranking de EPP, críticos recientes, cobertura y filtros |
| `2026-10-01-panel-general-filtros.png` | Panel con obra, periodo del 1 al 30 de septiembre de 2026 y turno A seleccionados |
| `2026-10-01-navegacion-a-hallazgos.png` | Bandeja abierta desde un indicador; conserva fecha y turno, y no arrastra el filtro de obra que la bandeja no admite |
| `2026-10-06-cola-videos.png` | Cola de videos (#117) contra el mock del contrato: archivo, cámara, estado, intentos y motivo del error (solo en `error` y `reintentando`), con «Cargar más videos». El único video viene del ejemplo genérico de Prism |
| `2026-10-06-reprocesar-video.png` | Cola de videos (#118) con el permiso `editar_reglas`: columna «Acciones» y botón «Reprocesar» solo en el video en `error`; el `en_cola` muestra «—». Para la captura, un proxy local delante de Prism agregó `editar_reglas` a `/yo` (el ejemplo del contrato no lo trae) y una copia del video de ejemplo en estado `error`; el resto es Prism |

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
| Vitest (`npm test`) | 16 archivos y 71 pruebas aprobados |
| TypeScript (`npm run typecheck`) | Aprobado |
| ESLint (`npm run lint`) | Aprobado sin advertencias |
| Build de producción (`npm run build`) | Aprobado; Vite transformó 1958 módulos |
| Pruebas por mutación | Se inyectaron defectos temporales en navegación, fechas inválidas, límite exclusivo, rango por defecto, permisos 403, conservación de datos, roles accesibles y variación cero; cada test correspondiente falló. Se restauró el código y la corrida focalizada final aprobó 8 archivos y 40 pruebas |

La consola del navegador registró únicamente `404` para `/favicon.ico`; no impidió cargar ni
usar el panel. La comprobación visual usó el mock del contrato, por lo que no valida disponibilidad
del backend productivo. Los tests de integración verifican el estado visible de los filtros y la
consulta solicitada al volver al panel; la captura de navegación documenta el paso hacia Hallazgos.
