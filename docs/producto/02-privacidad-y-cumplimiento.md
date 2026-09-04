# Privacidad y cumplimiento

> **Fecha de corte: 2 de septiembre de 2026.** El marco legal chileno está en movimiento
> (ver §7). Todo lo que sigue debe reverificarse antes de la entrega final; ese chequeo es
> parte del entregable, no una nota al pie.

Este documento no es relleno para el informe. Es la parte del diseño que decide si el sistema
puede instalarse en una faena real o no, y varias de sus reglas están traducidas a columnas de
la base de datos y a tests.

## 1. La pregunta que hay que responder bien

**¿Guardián EPP trata datos biométricos?** De la respuesta depende todo el régimen aplicable.

La imagen de un trabajador es un **dato personal**, pero **no** un dato biométrico mientras el
sistema no haga tratamiento técnico dirigido a **identificar de forma única** a una persona. Esa
distinción es la línea de diseño de todo el proyecto.

Por eso el sistema:

| Hace | No hace |
|---|---|
| Detecta objetos: persona, casco, chaleco | Reconocimiento facial |
| Asigna un identificador temporal dentro de un video | Re-identificación entre cámaras o entre días |
| Reporta por área y turno | Reportes por trabajador |
| Guarda recortes con el rostro difuminado | Guarda el cuadro original |

Los `track_id` son **efímeros**: se destruyen al cerrar el video y nunca se persisten como
identidad. Sin persistencia de identidad no hay tratamiento biométrico, y sin tratamiento
biométrico el sistema no cae en el régimen reforzado de datos sensibles.

## 2. Base de licitud: por qué NO se pide consentimiento

Parece lo natural: pedirle al trabajador que firme. **Es un error.**

La ley presume que el consentimiento **no fue libremente otorgado** cuando existe subordinación
laboral, y además es revocable en cualquier momento sin expresar causa. Un sistema cuya legalidad
depende de una firma que cualquier trabajador puede retirar mañana no es un sistema: es un pasivo.

Las bases correctas son otras dos, y se declaran **por regla** en la base de datos:

| Base | Cuándo aplica | Norma que la funda |
|---|---|---|
| **Obligación legal** | El empleador debe fiscalizar el uso de EPP | Ley 16.744 art. 68 · DS 44 art. 13 · **DS 594 art. 53** (dominio evaluado: obra) · DS 132 art. 32 (perfil minero) |
| **Interés legítimo** | Prevención de accidentes en zona de riesgo | Requiere test de proporcionalidad escrito |

Por eso la tabla `regla` lleva `base_licitud`, `norma_fundante`, `finalidad_declarada` y
`retencion_dias`: la trazabilidad jurídica se audita con un `SELECT`, no con un PDF que nadie
actualiza.

## 3. Lo que exige la Dirección del Trabajo

La doctrina es constante desde 2002 y se mantiene en los pronunciamientos recientes. El control
audiovisual del trabajador es lícito solo si es **general e impersonal**, y la vigilancia de la
actividad individual únicamente puede ser un **efecto accidental**, nunca la finalidad.

De ahí salen cinco requisitos que el diseño cumple por construcción:

1. **Cámaras panorámicas, nunca enfocadas al puesto de un trabajador.** El sistema no elige el
   encuadre —usa el CCTV existente— pero sí rechaza fuentes cuya finalidad declarada sea el
   control de una persona.
2. **Prohibido en baños, camarines, casino y zonas de descanso.** Implementado como **zonas de
   privacidad**: polígonos que se ennegrecen **antes** de inferir, no después.
3. **Nunca clandestino.** El sistema debe estar declarado en el Reglamento Interno de Orden,
   Higiene y Seguridad, con información previa a los trabajadores y señalética en los accesos.
4. **Acceso del trabajador a sus imágenes** y supresión de lo ajeno a la finalidad.
5. **No puede fundar una sanción disciplinaria.** Cada hallazgo lleva en la interfaz la leyenda:
   *"Este evento es un indicio automatizado y no constituye por sí solo una infracción. Requiere
   validación humana."* Y el flujo registra quién validó, cuándo y con qué observación.

> Ojo con un mito extendido: la Dirección del Trabajo **no emite autorizaciones previas** de
> sistemas de videovigilancia; fiscaliza a posteriori. No existe un sello que blinde el proyecto.
> La defensa es documental.

## 4. La decisión sobre "desagregar por género"

El cliente lo pidió. La respuesta es **no inferirlo desde la imagen**, y la negativa se sostiene
en tres frentes independientes — conviene poder dar los tres:

**Legal.** "Identidad de género" es dato sensible taxativo. Y no es *necesario*: el DS 44 art. 74
ya obliga al empleador a mantener registros desagregados por sexo desde recursos humanos. Sin
necesidad, no hay proporcionalidad.

**Técnico.** Con casco, antiparras y buff puestos, las señales faciales que usan esos
clasificadores están tapadas: el modelo terminaría discriminando por estatura y complexión. Y con
una dotación femenina en torno al 15 % en faena, un clasificador del 95 % de exactitud produce en
la clase minoritaria casi tantos falsos positivos como aciertos. El "ranking por género"
resultante sería estadísticamente indefendible y sesgado **contra** las trabajadoras.

**Ético.** Desde *Gender Shades* la evidencia es concluyente: 34,7 % de error en mujeres de piel
oscura frente a 0,8 % en hombres de piel clara.

### La alternativa que sí entrega lo que el cliente busca

Cruzar hallazgos **agregados** (área × turno × franja horaria) contra la tabla `dotacion`, que es
dato administrativo verificado del propio cliente:

> *"En el turno B del área de chancado, con dotación de 18 hombres y 4 mujeres, hubo 7 eventos
> de casco faltante."*

Con una regla de presentación **obligatoria en la interfaz**: ninguna celda con **n < 5** se
muestra. Con esa dotación, una celda pequeña reidentifica a la trabajadora.

Y hay un uso legítimo que además aporta valor real: la OIT y la normativa recomiendan adecuar el
EPP a diferencias biológicas. Si el EPP mal ajustado o de talla incorrecta explica parte del
incumplimiento, ese hallazgo **sí** es accionable.

> Nunca se presenta como una negativa seca. Se lleva la alternativa a la misma reunión.

## 5. Medidas técnicas concretas

| Medida | Implementación |
|---|---|
| **Anonimización por defecto** | El recorte se escribe con el rostro difuminado de forma irreversible. No existe en disco una versión con rostro visible. |
| **Zonas de privacidad** | Polígonos por cámara, aplicados **antes** de la inferencia. |
| **Minimización** | Solo se guardan recortes de evidencia, nunca cuadros completos "por si acaso". |
| **Retención en tres anillos** | Recortes 30 días · hallazgos y detecciones 12 meses · agregados anonimizados, indefinido. Purgado como tarea programada con su propio registro. |
| **Control de acceso** | Cuatro roles. El administrador configura pero **no** ve evidencia; el supervisor solo ve su área. Ningún rol tiene descarga masiva. |
| **Registro de auditoría** | Tabla *append-only* con reglas que impiden `UPDATE` y `DELETE`. |
| **Vista identificada** | Si alguna vez se requiere, es un flujo aparte con doble autorización y motivo obligatorio en texto libre. El camino por defecto es el anónimo; el identificado es el caro y trazable. |

La carga de acreditar las medidas de seguridad recae sobre el responsable del tratamiento. Sin
registro inmutable, en una controversia el proyecto no puede probar nada aunque haya hecho todo
bien.

## 6. El punto ciego clásico: el dataset

Etiquetar cuadros de trabajadores reales para entrenar el modelo es **un tratamiento de datos
personales con finalidad distinta** de la vigilancia de seguridad. Necesita su propia base de
licitud, y es el error que casi todos los proyectos de visión pasan por alto.

Medidas asociadas:

- La herramienta de etiquetado es **CVAT autoalojado**, no un servicio en la nube. Los planes
  gratuitos de las plataformas comerciales publican el dataset en su catálogo público: subir un
  solo lote de CCTV de faena ahí no es un descuido técnico, es un incidente de datos personales.
- Se registra **procedencia, licencia y alcance de uso** de cada imagen en la propia base de
  datos. Es trivial ahora e imposible de reconstruir después.
- Ninguna imagen de trabajador real entra al repositorio público.

## 7. Marco en movimiento — qué reverificar antes de entregar

A la fecha de corte:

- La Ley 21.719 **no deroga** la Ley 19.628: la **modifica y la renombra**. Después de su entrada
  en vigencia, los artículos que se citan siguen siendo artículos *de* la 19.628 reformada. Casi
  toda la literatura de blogs lo dice mal.
- Su vigencia prevista es el **1-dic-2026**, dentro de la vida del proyecto. Hay un proyecto
  ingresado para postergarla a 1-dic-2027 y otro en trámite que rebajaría las multas.
- El plazo de "72 horas" para notificar brechas que circula en internet **no está en la ley
  chilena**: viene del reglamento europeo. El texto exige notificar "sin dilaciones indebidas".

**Postura del proyecto:** diseñar contra el estándar más exigente. Si la ley se posterga, el
sistema ya cumple; si se endurece, también.

## 8. Entregables de cumplimiento

Cuatro documentos versionados en el repositorio, que ningún proyecto competidor va a tener:

1. Declaración de finalidad y base de licitud.
2. Evaluación de impacto en protección de datos personales.
3. Política de retención y supresión.
4. Matriz de roles y accesos.

Más dos artefactos técnicos que se producen barato y pesan mucho en una defensa:

- **Model card** del detector, con los usos explícitamente fuera de alcance: *este modelo no debe
  usarse para identificar personas, evaluar desempeño individual ni fundar sanciones
  disciplinarias*.
- **Datasheet** del dataset: procedencia, base de licitud de la recolección, distribución de
  clases, condiciones de captura y limitaciones conocidas.

Y un entregable pensado para el cliente, no para el ramo: **cláusula tipo para el Reglamento
Interno** y diseño de la señalética de los accesos.

## 9. Cómo se posiciona ante el sindicato

No es un anexo político: es condición de que el sistema se instale.

- No tiene reconocimiento facial ni capacidad de identificar personas.
- Difumina rostros antes de guardar cualquier evidencia.
- Reporta por área, no por trabajador.
- Incluye un **módulo de reconocimiento positivo**: porcentaje de cumplimiento y ranking positivo
  por área. Es lo que convierte la herramienta de "el que me vigila" en "el que muestra que mi
  cuadrilla lo hace bien".
- Debe estar declarado en el Reglamento Interno, con información previa.
