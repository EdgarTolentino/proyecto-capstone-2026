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

## Validación del panel general · 1 de octubre de 2026

Las capturas se tomaron en Windows con la web local y Prism sirviendo ejemplos del contrato
OpenAPI en `http://127.0.0.1:4010`. Son datos de demostración y no representan datos de una
obra real ni de la API productiva.

| Prueba | Resultado |
|---|---|
| Abrir `/` y cargar el panel con indicadores, tendencia, ranking, críticos recientes y cobertura | Correcta; contenido del mock visible |
| Filtrar por obra, desde, hasta y turno A | Correcta; controles seleccionados y URL con `obra_id`, `desde`, `hasta` y `turno` |
| Navegar desde «Hallazgos abiertos» a la bandeja | Correcta; conserva `desde`, `hasta` y `turno`, y omite `obra_id` |
| Volver al panel desde la navegación principal | Correcta; mantiene seleccionados los filtros del panel |
| Vitest | 15 archivos y 59 pruebas aprobados |
| TypeScript (`npm run typecheck`) | Aprobado |
| ESLint (`npm run lint`) | Aprobado sin advertencias |
| Build de producción (`npm run build`) | Aprobado; Vite transformó 1957 módulos |

La consola del navegador registró únicamente `404` para `/favicon.ico`; no impidió cargar ni
usar el panel. La comprobación visual usó el mock del contrato, por lo que no valida disponibilidad
del backend productivo.

El video de esas capturas es **sintético (generado con IA)** y las detecciones vienen de un
guion (detector simulado): ver `docs/producto/07-datasets.md`.
