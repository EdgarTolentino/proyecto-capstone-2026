# ADR-006 — El sistema no identifica personas ni infiere atributos

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

El cliente pidió desagregar los reportes por género. Sería técnicamente posible añadir un
clasificador de atributos sobre el recorte de persona.

## Decisión

Queda **prohibido por diseño**:

- Reconocimiento facial y re-identificación entre cámaras o entre días.
- Inferencia de género, edad, etnia o emoción.
- Persistencia de `track_id` fuera del video en que se generó.
- Escribir a disco cualquier recorte con el rostro visible.

La desagregación por sexo se entrega **cruzando hallazgos agregados** (área × turno × franja)
contra la tabla `dotacion`, que es dato administrativo del cliente. Con supresión de celdas
**n < 5**.

## Por qué

**Legal.** "Identidad de género" es dato sensible taxativo en la ley chilena. El cliente ya está
obligado a mantener registros desagregados por sexo desde recursos humanos (DS 44, art. 74): la
inferencia no es *necesaria*, y sin necesidad no hay proporcionalidad. Mantener los `track_id`
efímeros es lo que deja al sistema fuera del régimen de datos biométricos.

**Técnico.** Con casco, antiparras y buff, las señales faciales que usan esos clasificadores están
tapadas: el modelo discriminaría por estatura y complexión. Con ~15 % de dotación femenina, un
clasificador del 95 % de exactitud produce en la clase minoritaria casi tantos falsos positivos
como aciertos.

**Ético.** La evidencia desde *Gender Shades* es concluyente: 34,7 % de error en mujeres de piel
oscura frente a 0,8 % en hombres de piel clara.

**De negocio.** Los productos serios del rubro publicitan "sin reconocimiento facial" como
argumento de venta, porque es la condición de aceptación sindical. Un sistema percibido como
vigilancia punitiva no se instala.

## Cómo se comunica al cliente

Nunca como una negativa seca. Se presenta la alternativa en la misma reunión: *"le entregamos la
desagregación por sexo cruzando con su propia dotación, que es dato verificado y auditado, en vez
de adivinarlo desde el píxel"*. Y se ofrece el caso de uso legítimo: detectar si el EPP mal
ajustado o de talla incorrecta explica parte del incumplimiento.

## Consecuencias

Se documenta como decisión deliberada, no como limitación técnica, y se acompaña de una *model
card* con los usos explícitamente fuera de alcance: **este modelo no debe usarse para identificar
personas, evaluar desempeño individual ni fundar sanciones disciplinarias.**
