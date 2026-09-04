# ADR-011 — El dominio es configuración: se valida en construcción, la minería es un perfil

**Estado:** aceptada · **Fecha:** 2026-09-04

## Contexto

[V1](../../producto/06-verificaciones-criticas.md) se cerró, pero por una vía distinta a la
prevista: **no hay acceso a video de faena minera; sí lo hay a obra de construcción** de una
inmobiliaria, complementado con datasets públicos.

Eso obliga a responder una pregunta que el proyecto venía esquivando: ¿en qué dominio se
*declara*, se *evalúa* y se *demuestra* el sistema? Declarar dos dominios significa evaluar en
dos, y no hay once semanas para eso. Declarar minería y demostrar sobre una obra es incoherente
y la comisión lo va a notar.

[V10](../../producto/06-verificaciones-criticas.md) ya había anticipado la salida —separar el
**modelo** de la **configuración**— pero como aspiración de diseño, sin obligación técnica. Este
ADR la convierte en regla.

## Decisión

**1. El dominio de validación es la construcción.** El conjunto de prueba, las métricas del
plan de evaluación y la demostración de la S15 salen de video de obra.

**2. La minería es un *perfil*, no un caso evaluado.** Se demuestra que el sistema opera en
faena minera **cambiando un archivo de configuración, sin tocar una línea de código**. Se declara
explícitamente como extensión **no evaluada**.

**3. El perfil de dominio es un artefacto versionado**, no constantes repartidas por el código.
Contiene el catálogo de EPP, las zonas, las reglas, los umbrales y la matriz `zona × EPP ×
evaluable` de V2:

```
perfiles/
  construccion.yaml   ← el que se evalúa
  mineria.yaml        ← el que se demuestra
```

**4. Regla que lo sostiene:** `gepp-core` no contiene ningún nombre de EPP, zona ni umbral
literal. Se verifica con un test sobre el AST, igual que el que prohíbe `datetime.now()`
([ADR-005](005-fuente-y-reloj.md)). Sin ese test, el perfil se degrada a documentación en tres
semanas.

**5. El corpus se parte por función:**

| | Origen | Para qué | Por qué así |
|---|---|---|---|
| **Entrenamiento** | Datasets públicos de imágenes, con licencia verificada | Preentrenar el detector | Volumen, variedad, cero costo |
| **Prueba y demo** | Video propio de obra, 20-30 min | Conjunto de prueba, tracks, eventos, defensa | Es lo único insustituible |

Ningún dato entra sin fila en [`07-datasets.md`](../../producto/07-datasets.md).

## Por qué

**Porque es el video que existe.** Es el único material real al que el equipo tiene acceso
verificado. Lo demás era una esperanza con fecha de vencimiento en la S9.

**Porque el casco se ve.** En obra la cámara trabaja a 5-15 m; en faena a rajo abierto, a 20-50 m.
La aritmética de V2 es implacable con la segunda distancia y benigna con la primera. La
construcción no es el premio de consuelo: es el escenario en que el caso de uso es viable.

**Porque desaparece la brecha de dominio.** La [cascada de preentrenamiento](../00-arquitectura.md)
existía para salvar la distancia entre "todo lo público es construcción" y "hay que entrenar para
minería". Si el dominio evaluado *es* construcción, la brecha se cierra sola y la cascada se
acorta un peldaño.

**Porque el corpus de imágenes no puede evaluar el sistema.** Lo que se defiende no es un
detector: son reglas en segundos, tracks y eventos con duración. Un dataset de imágenes sueltas no
tiene tiempo, no tiene continuidad y no puede correr
`test_la_regla_en_segundos_es_invariante_a_la_cadencia`. Sirve para entrenar; no para probar.

**Porque el trámite se cae.** El plazo de cinco semanas del Reglamento Interno aplicaba a
*instalar vigilancia permanente*. Una grabación puntual, acotada y con consentimiento firmado
para un proyecto académico no lo dispara. Devuelve S4-S9 al desarrollo.

**Porque la portabilidad deja de ser una promesa.** Hoy la respuesta a *"¿esto sirve en otra
faena?"* es un párrafo de intenciones. Con dos perfiles ejecutables es una demostración de tres
minutos.

## Consecuencias

| Cambia | De | A |
|---|---|---|
| Marco normativo | DS 132 SERNAGEOMIN | DS 594 + Ley 16.744 |
| Catálogo de EPP v1 | Casco, buzo reflectante, respirador, autorrescatador | **Casco y chaleco** (+ arnés en altura, si V2 lo permite) |
| Distancia de diseño | 20-50 m | 5-15 m |
| Interlocutor | Prevencionista de faena | Prevencionista de obra |

**Lo que no cambia:** los diez ADR anteriores siguen en pie sin una enmienda. Dos etapas,
RF-DETR, FastAPI + React, el evento como unidad, el puerto `FrameSource`, la prohibición de
identificar personas, el monorepo, las alertas a dos velocidades, el pipeline propio y el cómputo
partido son todos independientes del dominio. Que la decisión no toque nada es la evidencia de
que la arquitectura estaba bien separada.

## El límite, dicho antes de que lo pregunten

**El perfil minero no estará medido.** Se puede afirmar que el sistema *opera* en minería; no se
puede afirmar con qué exactitud. Decirlo en el informe y en la defensa cuesta una frase; que lo
descubra la comisión cuesta la nota.
