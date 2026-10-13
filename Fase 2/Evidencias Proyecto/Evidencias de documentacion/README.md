# Evidencias de documentación

| Documento | Dónde está |
|---|---|
| Especificación de arquitectura | [`docs/arquitectura/00-arquitectura.md`](../../../docs/arquitectura/00-arquitectura.md) y las decisiones en [`docs/arquitectura/adr/`](../../../docs/arquitectura/adr/) |
| Diseño de interfaz (GUI) | **Depositado** aquí: `GUI-01` a `GUI-05` — ver abajo |
| Modelo de datos | [`docs/arquitectura/01-modelo-de-datos.md`](../../../docs/arquitectura/01-modelo-de-datos.md); esquema y diagrama en [`Evidencias de sistema/Base de datos`](../Evidencias%20de%20sistema/Base%20de%20datos/) |
| Plan de evaluación del modelo | [`docs/arquitectura/02-plan-de-evaluacion.md`](../../../docs/arquitectura/02-plan-de-evaluacion.md) |
| Informe de pruebas manuales de la web | **Depositado** aquí: `Pruebas/Reporte_Pruebas_Guardian_EPP_05_10_2026` (`.docx` y `.pdf`, #96 y #132) |
| Manual de usuario | **Depositado** aquí: `Manual de Usuario` (`.docx` y `.pdf`, #91) |
| Guía de etiquetado | [`docs/datos/guia-etiquetado.md`](../../../docs/datos/guia-etiquetado.md) |
| Manual técnico / despliegue | [`docs/operacion/`](../../../docs/operacion/): recorrido del video a la bandeja, modelo ONNX en CPU y alertas |

Los documentos vivos se versionan en `docs/`. Aquí se depositan las **versiones congeladas**
que se entregan al docente, en PDF y con número de versión.

## Diseño de interfaz — depositado el 2026-09-04

Las dos pantallas que definen el producto. Generadas con el prompt versionado en
[`apps/web/PROMPT-DISENO.md`](../../sistema/apps/web/PROMPT-DISENO.md), en tres iteraciones
registradas ahí mismo, y contrastadas contra
[`contracts/openapi.yaml`](../../sistema/contracts/openapi.yaml).

| Archivo | Pantalla |
|---|---|
| `GUI-01-bandeja-de-hallazgos.png` | Bandeja de triage — la principal |
| `GUI-02-visor-recorte-y-cajas.png` | Visor de evidencia, parte superior: recorte con cajas, rostro difuminado, línea de tiempo |
| `GUI-03-visor-por-que-se-disparo.png` | Visor de evidencia, parte inferior: descripción automática y bloque de auditoría |
| `GUI-04-bandeja-implementada.png` | Bandeja implementada a 1280×800 con datos servidos por Prism |
| `GUI-05-visor-implementado.png` | Visor implementado a 1280×800 con el estado de evidencia no disponible |

**Verificaciones hechas sobre estas capturas:**

- **Prueba de daltonismo: pasa.** Desaturada la bandeja, los cuatro niveles de severidad se
  distinguen por forma —rombo, triángulo, círculo, anillo— más la palabra, sin depender del color.
- **Coherencia con el contrato:** los 16 hallazgos cumplen `cuadros_confirmados ≈ duracion_s × 5`,
  la cadencia de muestreo del sistema. Revisar el diseño contra el contrato destapó un hueco
  —`GET /estado`, que alimenta la cabecera— y un error de escala que venía del propio contrato.
- **Reglas de privacidad:** ninguna columna con nombre, RUT ni foto de trabajador; el difuminado
  de rostro aparece activado y etiquetado como obligatorio; el aviso *"Indicio automatizado.
  Requiere validación humana"* está presente en las dos pantallas.
