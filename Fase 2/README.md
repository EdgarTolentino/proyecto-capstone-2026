# Fase 2 — Desarrollo (S5–S15)

Evaluación de avance en **S10**. Entrega final en **S15**. Es la fase larga y la que pesa.

## Evidencias exigidas

### Individuales
| Archivo | Qué es |
|---|---|
| `Apellido_Nombre_2.1_APT122_DiarioReflexionFase2.docx` | Diario de reflexión |

### Grupales
| Archivo | Qué es |
|---|---|
| `2.4_GuiaEstudiante_Fase 2_DesarrolloProyecto APT (Español).docx` | Informe de avance (S10) |
| `2.6_GuiaEstudiante_Fase 2_Informe Final Proyecto APT (Español).docx` | Informe final (S15) |
| `PLANILLA DE EVALUACION AVANCE FASE 2.xlsx` | La envía el docente |
| `PLANILLA DE EVALUACION FINAL FASE 2.xlsx` | La envía el docente |

### Evidencias Proyecto
| Carpeta / archivo | Qué es |
|---|---|
| `Presentación Proyecto.pptx` | Presentación del sistema |
| `Evidencias de documentacion/` | Manuales, diseño de GUI, modelo de datos, plan de pruebas |
| `Evidencias de sistema/Aplicacion/` | El sistema — apunta a [`sistema/`](sistema/) |
| `Evidencias de sistema/Base de datos/` | Esquema, diagrama entidad-relación, respaldo y datos de ejemplo |

## Dónde vive el código

Todo el desarrollo está en **[`sistema/`](sistema/)**, no dentro de `Evidencias Proyecto/`.

*Por qué:* las herramientas del ecosistema Python y Node (contenedores, importaciones, CI,
rutas de configuración) se rompen o se vuelven frágiles con espacios y acentos en la ruta.
`Evidencias de sistema/Aplicacion/` contiene un README que apunta al código, la versión
entregada y su etiqueta de git. **Confirmar esta decisión con el docente en la S5.**
