# Plan de trabajo — 18 semanas

> Insumo directo de las secciones 5, 7 y 8 de la Guía 1.5 (metodología, plan de trabajo y
> Carta Gantt). Las fechas calendario se completan cuando el equipo fije la S1 real.

## Principio que ordena todo el plan

**Integrar temprano, mejorar después.** El error clásico de un proyecto de visión con plazo fijo
es dedicar diez semanas al modelo y descubrir en la última que nada está conectado. Aquí el
recorrido completo —video entra por un extremo, alerta sale por el otro— tiene que estar vivo en
la **S9**, aunque el modelo sea malo. Desde ahí se mejora *un* eslabón por vez, con el sistema
siempre funcionando.

Corolario: **el primer modelo es deliberadamente mediocre y eso está bien.** Su función es
destrabar la integración, no impresionar a nadie.

## Reparto por persona

| Persona | Responsabilidad | Entregables de los que responde |
|---|---|---|
| **Edgar Tolentino** (líder) | Visión por computador, backend, datos, infraestructura, arquitectura | Modelo, pipeline de video, API, base de datos, CI, alertas |
| **Miguel Ortega** | Frontend | Bandeja de alertas, visor de evidencia, configuración de reglas |
| **Liân** | Frontend | Tablero de analítica, reportes, administración |

**El reparto no puede convertirse en dos proyectos paralelos que se encuentran en la S14.**
Lo que lo evita: el contrato de API se congela en la S5 y el frontend trabaja desde el primer
día contra un servidor simulado. Nadie espera a nadie.

## Fase 1 · Definición (S1–S4)

| Sem | Actividad | Responsable | Entregable |
|---|---|---|---|
| S1 | Descarte de propuestas de la Escuela; tres propuestas propias | Equipo | Documento de propuestas |
| S2 | Elección: Guardián EPP. Investigación del estado del arte | Equipo | Investigación técnica |
| S3 | Arquitectura, riesgos, repositorio, gobernanza | Edgar | `docs/` + repositorio configurado |
| S3 | Diseño de interfaz: bocetos de las pantallas | Frontend | Maqueta navegable |
| S4 | **Exposición grupal** + Guía 1.5 completa | Equipo | `Presentación Proyecto.pptx` |

## Fase 2 · Desarrollo (S5–S15)

| Sem | Actividad | Responsable | Hito |
|---|---|---|---|
| **S5** | Cimientos: esqueleto del repo, CI en verde, esquema de BD, **contrato de API congelado**, servidor simulado para el frontend | Edgar | 🔒 **El frontend puede avanzar sin el backend** |
| S6 | Recolección de video, definición de clases, protocolo de etiquetado, lote 1 | Edgar | Dataset v0.1 |
| S6 | Bandeja de alertas contra datos simulados | Frontend | Pantalla 1 |
| S7 | Ingesta por carpeta vigilada, cola de trabajos, persistencia | Edgar | Video entra al sistema |
| S7 | Visor de evidencia | Frontend | Pantalla 2 |
| S8 | **Primer modelo entrenado** (línea base) y su evaluación honesta | Edgar | Métrica base publicada |
| **S9** | **Integración extremo a extremo**: video → detección → seguimiento → evento → BD → web | Equipo | 🔒 **El recorrido completo funciona** |
| **S10** | **Evaluación de avance**: demo funcional + informe | Equipo | 🎓 Entrega S10 |
| S11 | Motor de reglas configurable por zona | Edgar | Reglas sin desplegar código |
| S11 | Pantalla de configuración de reglas | Frontend | Pantalla 3 |
| S12 | Alertas: canal, acuse de recibo, escalamiento, supresión de repetidos | Edgar | Alerta llega a un teléfono real |
| S12 | Modelo v2: aprendizaje activo sobre los fallos del v1 | Edgar | Métrica mejorada |
| S13 | Analítica: incumplimiento por EPP, zona, horario y tendencia | Edgar + Frontend | Pantalla 4 |
| S13 | Etapa 2: descripción selectiva con modelo de lenguaje visual | Edgar | Hallazgos descritos |
| S14 | Endurecimiento: pruebas, rendimiento, manual técnico, accesibilidad | Equipo | Plan de pruebas ejecutado |
| **S15** | **Congelar, etiquetar `v1.0.0`, informe final, presentación** | Equipo | 🎓 Entrega final |

## Fase 3 · Cierre (S16–S18)

| Sem | Actividad | Responsable |
|---|---|---|
| S16 | Manual de usuario, documentos de cierre | Equipo |
| S17 | Preparación y ensayo de la defensa | Equipo |
| S18 | **Defensa y presentación final** | Equipo |

## Carta Gantt

```
Actividad                          │F1     │Fase 2                                     │F3
                                   │1 2 3 4│5 6 7 8 9 10 11 12 13 14 15               │16 17 18
───────────────────────────────────┼───────┼───────────────────────────────────────────┼────────
Definición y arquitectura          │████████                                          │
Repositorio, CI, contrato de API   │    ████████                                      │
Dataset y etiquetado               │        ██████████                                │
Entrenamiento y evaluación         │            ████████    ██████                    │
Pipeline de video y eventos        │          ████████████                            │
API, dominio y base de datos       │        ████████████                              │
Frontend                           │      ██  ██████████████████████████              │
Motor de reglas                    │                        ██████                    │
Alertas y escalamiento             │                          ██████                  │
Analítica y reportes               │                              ██████              │
Pruebas y endurecimiento           │                    ██          ████████          │
Documentación y entregables        │      ████        ████        ████████    ████████│████████
───────────────────────────────────┼───────┼───────────────────────────────────────────┼────────
HITOS                              │      ▲│        ▲    ▲                      ▲     │      ▲
                                   │     S4│       S9  S10                     S15    │    S18
```

## Cómo trabaja el equipo

Reglas cortas, porque las largas no se cumplen.

| Regla | Detalle |
|---|---|
| **Reunión semanal fija**, 45 minutos | Qué cerré, qué sigo, qué me bloquea. Si algo lleva dos semanas bloqueado, cambia de dueño. |
| **Nada entra a `main` sin Pull Request** | Aunque el PR lo revise una sola persona. Deja historia y obliga a explicar el cambio. |
| **Definición de terminado** | Pasa CI + tiene pruebas + está documentado + otro integrante lo pudo ejecutar en su máquina. |
| **Un issue por tarea, siempre** | Si no está en un issue, no existe y nadie lo va a recordar en la S14. |
| **El viernes se etiqueta** | Cada viernes sale una etiqueta `v0.x` con lo que hay. Obliga a que siempre haya algo ejecutable. |
| **Decisión técnica de fondo → ADR** | No se discute en el chat: se escribe en `docs/arquitectura/adr/` y se decide en el PR. |

## Riesgos del plan

| Riesgo | Probabilidad | Impacto | Mitigación | Cuándo se decide |
|---|---|---|---|---|
| **El video real de faena nunca llega** | Alta | Crítico | Plan B: dataset público + video grabado por el equipo simulando el escenario. La arquitectura no cambia. | **Antes de la S6** |
| El etiquetado se come el semestre | Alta | Alto | Pre-etiquetar con un modelo base y solo corregir; acotar a 4 clases en v1 | S6 |
| La única GPU se convierte en cuello de botella | Media | Medio | Entrenar en Kaggle/Colab (30 h/semana gratis); la GPU local solo para inferencia | S8 |
| El frontend queda esperando al backend | Media | Alto | Contrato de API congelado en S5 + servidor simulado | S5 |
| Un integrante se descuelga | Media | Alto | Reunión semanal + issues asignados; el trabajo se reasigna en la semana, no en la S14 | Continuo |
| Sobreajuste al alcance: querer las 8 clases de EPP | Alta | Medio | v1 cierra con casco y chaleco. Lo demás es extensión demostrada, no requisito. | S8 |
