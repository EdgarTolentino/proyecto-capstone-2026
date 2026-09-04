# Evidencias de documentación

| Documento | Origen |
|---|---|
| Especificación de arquitectura | [`docs/arquitectura/`](../../../docs/arquitectura/) |
| Diseño de interfaz (GUI) | **Depositado** — ver abajo |
| Modelo de datos | [`docs/arquitectura/`](../../../docs/arquitectura/) |
| Plan de pruebas y resultados | `docs/operacion/` |
| Manual de usuario | Se redacta en la Fase 3 |
| Manual técnico / despliegue | `docs/operacion/` |

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

**Verificaciones hechas sobre estas capturas:**

- **Prueba de daltonismo: pasa.** Desaturada la bandeja, los cuatro niveles de severidad se
  distinguen por forma —rombo, triángulo, círculo, anillo— más la palabra, sin depender del color.
- **Coherencia con el contrato:** los 16 hallazgos cumplen `cuadros_confirmados ≈ duracion_s × 5`,
  la cadencia de muestreo del sistema. Revisar el diseño contra el contrato destapó un hueco
  —`GET /estado`, que alimenta la cabecera— y un error de escala que venía del propio contrato.
- **Reglas de privacidad:** ninguna columna con nombre, RUT ni foto de trabajador; el difuminado
  de rostro aparece activado y etiquetado como obligatorio; el aviso *"Indicio automatizado.
  Requiere validación humana"* está presente en las dos pantallas.
