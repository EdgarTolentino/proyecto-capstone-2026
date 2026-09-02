# Guardián EPP — Problema, visión y alcance

> Documento raíz del producto. Todo lo demás (arquitectura, plan, reglas de negocio) se justifica
> contra este texto. Si algo que construimos no aparece aquí, sobra.

## 1. El problema

En una faena minera el uso de Elementos de Protección Personal es obligatorio y su
incumplimiento es causa directa de lesiones. Hoy la fiscalización de ese uso descansa en la
**observación humana**: el prevencionista recorre el área, mira, y anota en una planilla.

Ese método tiene cuatro fallas estructurales, y ninguna se arregla contratando más
prevencionistas:

| Falla | Consecuencia |
|---|---|
| **Es muestral.** Un prevencionista cubre una fracción del área durante una fracción del turno. | Lo que no se observó, no existe. |
| **Es reactivo.** El video del CCTV ya instalado solo se revisa *después* de un accidente. | La cámara sirve para explicar la lesión, no para evitarla. |
| **No deja dato analizable.** La observación termina en una planilla o en papel. | Nadie puede responder "¿qué EPP se incumple más y dónde?". |
| **No es trazable.** No queda registro de que alguien haya actuado sobre el hallazgo. | El ciclo de mejora nunca se cierra. |

Al mismo tiempo, la faena **ya tiene cámaras instaladas y grabando**. La infraestructura de
observación continua existe: lo que falta es alguien que mire.

## 2. La idea

Usar el video que la faena ya produce para convertir la observación **muestral y humana** en
observación **continua y automática**, y convertir cada incumplimiento en un **evento
estructurado** que dispara una alerta y alimenta una analítica.

El desplazamiento que buscamos es este:

```
   HOY                                  CON GUARDIÁN EPP
   ───                                  ────────────────
   Cámara → (nada) → accidente          Cámara → detección → evento → alerta → acción → dato
            └ se revisa el video                                                  └ tendencia
              después                                                               y prioridad
```

## 3. Qué NO es este proyecto

Delimitarlo importa tanto como definirlo:

- **No es un sistema de vigilancia individual.** No identifica personas, no lleva un registro por
  trabajador y no alimenta procesos disciplinarios. Es una herramienta de gestión preventiva por
  área. Esta restricción es legal, ética y de diseño — está en [`docs/producto/02-privacidad.md`](02-privacidad.md).
- **No es un detector de objetos.** El detector es una pieza; el proyecto es la plataforma que
  convierte detecciones en decisiones. Un modelo sin gestión de hallazgos no le sirve a nadie.
- **No reemplaza al prevencionista.** Le devuelve el tiempo que hoy gasta recorriendo para
  encontrar lo que ya ocurrió, y le dice dónde mirar.

## 4. A quién sirve

| Usuario | Qué necesita del sistema | Cómo lo mide |
|---|---|---|
| **Prevencionista de riesgos** | Enterarse del incumplimiento el mismo turno, no la semana siguiente | Tiempo entre el hecho y el aviso |
| **Supervisor de área / jefe de turno** | Una alerta corta, con la imagen, de *su* área, que pueda accionar en minutos | Alertas atendidas / recibidas |
| **Jefatura SSO** | Saber dónde concentrar el esfuerzo: qué EPP, qué zona, qué horario | Tendencia mensual de incumplimiento |
| **Administrador** | Configurar zonas, reglas y destinatarios sin pedirle nada a un programador | Cambios de regla sin despliegue |

## 5. Objetivo general

> Desarrollar una plataforma web que detecte automáticamente, sobre video de faena, el
> incumplimiento en el uso de elementos de protección personal, y que convierta cada detección
> en un evento gestionable —con alerta al responsable, evidencia asociada y analítica de
> tendencia— con el fin de anticipar condiciones inseguras en lugar de documentarlas después
> del accidente.

## 6. Objetivos específicos

1. **Construir un conjunto de datos etiquetado propio**, representativo de las condiciones reales
   de la faena (iluminación, distancia, polvo, oclusión), con las clases de EPP que exige la
   normativa aplicable.
2. **Entrenar y evaluar un modelo de detección** de EPP, midiendo su desempeño no solo por cuadro
   sino **a nivel de evento y de alerta**, que es el nivel al que el usuario lo percibe.
3. **Convertir detecciones en eventos**: agrupar detecciones sucesivas de la misma persona en un
   único hallazgo con inicio, término y evidencia, en lugar de miles de cuadros sueltos.
4. **Implementar un motor de reglas configurable** que determine qué constituye incumplimiento
   según el área, el turno y la severidad, **sin reglas escritas en el código**.
5. **Entregar la alerta al responsable** por un canal que efectivamente lea, con acuse de recibo,
   escalamiento si nadie responde, y supresión de repetidos para evitar la fatiga de alertas.
6. **Construir la plataforma web** de gestión de hallazgos y el tablero de analítica que responda
   qué EPP se incumple más, en qué zona, en qué horario y con qué tendencia.
7. **Diseñar la arquitectura para que la ingesta en vivo (RTSP) sea una extensión aditiva** y no
   una reescritura del núcleo.
8. **Validar el sistema** con un plan de pruebas formal, un conjunto de video de referencia y
   métricas de aceptación acordadas antes de medir.

## 7. Alcance por versión

| | v1 — lo que se entrega en S15 | v2 — lo que queda diseñado, no construido |
|---|---|---|
| **Ingesta** | Archivos de video en carpeta vigilada | Cámara RTSP en vivo |
| **Latencia** | Minutos u horas tras el turno | Segundos |
| **Detección** | Modelo propio afinado, en lote | El mismo modelo, en flujo continuo |
| **Alertas** | Al cerrar el procesamiento del video | En el momento del hecho |
| **Analítica** | Completa | La misma |

La v1 no es una maqueta de la v2: es el mismo sistema con otra fuente de video. Esa es
justamente la apuesta de arquitectura, y está detallada en
[`docs/arquitectura/`](../arquitectura/).

## 8. Qué hace que esto no sea un trabajo escolar

Tres cosas, y conviene poder decirlas en una frase cada una en la defensa:

1. **El dato es propio.** El modelo se entrena con un conjunto etiquetado por nosotros para el
   dominio minero chileno. Un detector descargado con clases genéricas no distingue un casco de
   seguridad de un gorro, ni un chaleco reflectante de una polera naranja.
2. **El incumplimiento es un evento, no un cuadro.** El salto difícil no es detectar un casco:
   es decidir que *esta persona*, durante *estos 40 segundos*, en *esta zona*, estuvo sin él —
   y que eso es un solo hallazgo, no 200 alertas.
3. **La alerta cierra el ciclo.** Emitir la alerta es la mitad; la otra mitad es registrar que
   alguien la recibió, la atendió y qué hizo. Sin eso el sistema produce ruido, no seguridad.
