# Verificaciones críticas antes de comprometer el proyecto

> Este documento existe porque una revisión adversarial del diseño encontró que **el corpus de
> investigación es sólido donde es fácil investigar y está vacío donde el proyecto se juega**.
> Lo que falta no son más fuentes: son **cálculos y decisiones que nadie ha hecho todavía**.
>
> Las cuatro primeras son baratas —horas, no semanas— y de ellas depende si Guardián EPP es
> viable. **Ninguna línea de código de visión debería escribirse antes de cerrarlas.**

## V1 · ¿Existe el video? ✅ CERRADA — 2026-09-04

**Resuelta, pero por una vía distinta a la prevista.** No hay acceso a video de faena minera. Sí
lo hay a **obra de construcción** de una inmobiliaria, más datasets públicos.

Eso obligó a decidir el dominio del proyecto, y quedó escrito en
[ADR-011](../arquitectura/adr/011-dominio-configurable.md):

| | Resolución |
|---|---|
| Dominio evaluado | **Construcción.** El conjunto de prueba y la demo de S15 salen de obra |
| Minería | **Perfil de configuración**, demostrado sin tocar código y declarado como no evaluado |
| Entrenamiento | Datasets públicos de imágenes, con licencia verificada |
| Prueba y demo | **Video propio de obra, 20-30 min continuos** — es lo insustituible |
| Procedencia | Toda fuente pasa por [`07-datasets.md`](07-datasets.md) antes de usarse |

**Lo que este cambio ahorra:** el trámite de cinco semanas del Reglamento Interno se cae. Ese
plazo rige para *instalar vigilancia permanente*, no para una grabación puntual y consentida con
fines académicos. Vuelven S4-S9 al desarrollo. Lo que sí hace falta son dos papeles: autorización
escrita de la empresa y consentimiento informado de las personas grabadas.

**La trampa que queda viva:** casi todo lo público de EPP son **imágenes sueltas, no video**. Sin
video no hay tracks, no hay reglas en segundos y no hay eventos — es decir, no hay nada que
evaluar. Los datasets públicos entrenan; **solo el video propio prueba**. Confundirlos es quedarse
sin defensa en la S15.

## V2 · ¿Cuántos píxeles mide un casco a la distancia real? 🔴 BLOQUEANTE

**Veinte minutos de aritmética que pueden invalidar el caso de uso completo**, y que nadie ha
hecho.

Un casco mide unos 28 cm. A 30 metros, con 1080p y una lente estándar, puede quedar en menos de
10 píxeles de alto: un régimen en el que **ningún detector del mundo** decide si está puesto o no.
En los datasets de CCTV industrial disponibles, más de la mitad de los cascos ya caen en la
categoría "objeto pequeño".

El cambio de dominio de [ADR-011](../arquitectura/adr/011-dominio-configurable.md) juega a favor
—en obra la cámara trabaja a 5-15 m, no a 20-50— pero **no exime del cálculo**: lo que decide no
es la distancia, es la tabla.

**Cómo hacerlo**, con un solo cuadro de cada cámara:

1. Medir en píxeles la altura de una persona a la distancia típica y a la máxima de la zona.
2. Derivar la altura de la cabeza (≈ 1/7 de la persona) y del torso.
3. **Multiplicar por el factor de reescalado a la entrada del detector.** RF-DETR no ve el cuadro
   de 1920 px: lo reduce a su resolución de entrada. Es el paso que casi nadie hace y el que
   manda — subir la cámara a 4K no sirve de nada si el cuadro completo se reescala igual.
4. Contrastar contra los umbrales operativos:

| Para evaluar | Umbral mínimo sugerido |
|---|---|
| Casco | ≥ 40 px de alto de cabeza |
| Chaleco | ≥ 80 px de alto de persona |
| Lentes, guantes | ≥ 120 px de alto de persona (probablemente fuera de alcance) |

**El resultado es una tabla `zona × EPP × evaluable`** que se carga en la base de datos, y el
motor de reglas la respeta: **nunca exige en una zona un EPP que la cámara no alcanza a
resolver**. Eso mata de raíz el modo de fallo número uno de estos sistemas.

### Primera medición real — 2026-09-04

Sobre un cuadro nativo del material descargado (1280×720, clip de Hong Kong), con rejilla de
10 px:

| Posición en el cuadro | Ancho del casco | Tras reescalar a 560 | ¿Sobrevive? |
|---|---|---|---|
| Primer plano | ~60 px | ~26 px | ✅ |
| Media distancia | ~63 px | ~28 px | ✅ |
| Fondo del encuadre | ~40 px | **~17 px** | ❌ |

**El umbral es de 46 px en el cuadro.** Los cascos cercanos y medios pasan; los del fondo no.
Es decir: en un mismo encuadre conviven zonas evaluables y zonas que no lo son — que es
exactamente lo que la tabla `zona × EPP × evaluable` existe para registrar.

**Y la resolución de origen no salva nada:** un casco que en 1280 mide 60 px mide 90 px en 1920,
pero el factor de reescalado baja de 0,44 a 0,29 y llega igual a ~26 px. Lo que mueve la aguja es
el ángulo de visión y el ***tiling***.

Queda pendiente repetir la medición sobre el video propio, con la cámara y las distancias reales
de la obra (#10).

Esa tabla es además un entregable que ningún competidor comercial publica.

## V3 · ¿Con qué métrica se mide un evento? 🔴 BLOQUEANTE

Todo el material de referencia mide **detectores** (mAP) o **seguidores** (HOTA, IDF1). Pero la
unidad de salida de este sistema es el **evento con duración**, y para eso **no hay métrica
definida**. Es exactamente con lo que se defiende el proyecto en la S18.

Un mAP de 0,70 no dice nada sobre si el sistema generó **3 eventos donde había 1** ni sobre
cuántos incumplimientos reales se perdieron.

Queda definido en [`docs/arquitectura/02-plan-de-evaluacion.md`](../arquitectura/02-plan-de-evaluacion.md).

## V4 · ¿Caben las tres cargas en 8 GB de VRAM? 🟠 IMPORTANTE

Se está planificando simultáneamente: *fine-tuning* de RF-DETR (que la documentación oficial dice
que consume los 8 GB con lote 4), el detector sirviendo inferencia, y un modelo de lenguaje visual
de 4B cuantizado. **Nadie ha sumado.**

Medición de dos horas en la máquina real:

1. VRAM en reposo del detector servido.
2. VRAM y latencia p50/p95 de Qwen3-VL-4B en Q4 sobre 50 recortes de 384 px.
3. Si (1) + (2) exceden los 8 GB.

Según el resultado: bajar a un modelo de 2B, cargar y descargar bajo demanda con cola
serializada, o pasar la Etapa 2 a una API externa.

**Regla que sale gratis:** nunca entrenar y servir en la misma máquina al mismo tiempo. Se
reservan ventanas.

## V5 · ¿Qué EPP exige realmente la obra? 🟠 IMPORTANTE

**Se alivia con [ADR-011](../arquitectura/adr/011-dominio-configurable.md), no desaparece.** El
riesgo original era entrenar clases de *safety vest* desde datasets de construcción occidental
cuando en faena minera se usa buzo reflectante completo, respirador, autorrescatador y
barbiquejo: entrenar para otro problema. Al evaluar en construcción, el catálogo público y el
catálogo real **coinciden**, y la brecha de dominio se cierra sola.

Lo que sigue vivo es la pregunta concreta: **¿qué exige el reglamento de *esta* obra, por área?**
Casco y chaleco son seguros; el arnés en altura depende de si la cámara lo resuelve.

**Qué hacer:** pedir la matriz de EPP por área a la inmobiliaria, cruzarla con la tabla de V2, y
quedarse con las clases detectables —previsiblemente **casco y chaleco** en la v1—, descartando
por escrito las que no lo son. El resultado se escribe en `perfiles/construccion.yaml`, no en el
código.

## V6 · ¿Cómo se asocia un EPP a su persona? 🟠 IMPORTANTE

Es el **corazón algorítmico** de la Etapa 1 y hoy es una heurística geométrica sin evaluar:
el casco pertenece a la persona si su centro cae en la franja superior de su caja.

Falla justo donde importa: trabajadores agrupados, cámara cenital, distancia. Y produce el peor
error posible del dominio: **marcar como incumplidor a alguien que sí lleva casco**.

**Experimento pequeño, semana 8:** 100 cuadros etiquetados a mano con la asociación correcta,
comparando dos enfoques:

| Enfoque | Costo | Qué se mide |
|---|---|---|
| Heurística geométrica (lo implementado) | Ya está | Exactitud de asociación |
| Estimación de pose ligera (anclar cada EPP a su nodo anatómico) | +cómputo | Exactitud de asociación |

Si la heurística baja del 90 % con dos o más personas en el cuadro, entra la pose.

## V7 · El riesgo que nadie nombró: el falso negativo 🔴 CONCEPTUAL

Todo el diseño está orientado a **reducir falsos positivos** —fatiga de alertas, umbral de
confirmación, verificación selectiva—. Nadie analizó el otro lado.

**Si la faena adopta Guardián EPP como cobertura de supervisión y reduce las rondas presenciales,
el recall real del sistema se convierte en un hueco de seguridad de personas.** Un sistema de
seguridad que falla en silencio es **peor** que no tener sistema.

Tres medidas, y las tres entran al diseño y al informe:

1. **Posicionamiento escrito:** el sistema es **complemento** de la supervisión, nunca sustituto.
   Va en el informe, en la interfaz y en la presentación al cliente.
2. **Piso de recall declarado por regla**, monitoreado. Si una regla baja de su piso, se marca
   como degradada en la interfaz.
3. **Cobertura efectiva visible en la interfaz:** qué cámaras, zonas y horarios están siendo
   evaluados **y cuáles no**, incluyendo las caídas del pipeline. El prevencionista tiene que
   poder ver el hueco.

## V8 · La cámara se mueve y nadie se entera 🟡 MADUREZ

Las zonas y las reglas se definen en píxeles de una vista concreta. En faena las cámaras se
golpean, se limpian, se reorientan y se mueven con el viento. Cuando la vista cambia, **todas las
reglas de esa cámara evalúan el área equivocada en silencio**: el sistema sigue emitiendo eventos,
todos mal atribuidos, y contamina la analítica por zona que es el valor del producto.

**Mitigación, ~30 líneas:** guardar el cuadro de referencia junto con la definición de zonas y
comparar en cada ingesta (histograma o correspondencia de puntos). Si la similitud cae bajo un
umbral, marcar la fuente como **"requiere recalibración"** y **suspender sus reglas** en lugar de
emitir eventos dudosos.

Complementario: un **vigilante de salud de cámara** que calcule nitidez, brillo y tasa de
detección de personas por video y los compare con la línea base de esa cámara. Una caída
pronunciada genera un **aviso de mantención**, no una alerta de EPP. Convierte el fallo silencioso
—lente sucio interpretado como "zona 100 % cumplidora"— en un evento visible.

## V9 · ¿Cuántas horas tiene Edgar? 🟠 IMPORTANTE

El reparto deja en **una sola persona**, entre la S5 y la S15: etiquetar 2.000-3.000 imágenes en
tres rondas, entrenar y evaluar el detector, escribir el pipeline, el motor de reglas, la base de
datos, la API y el trabajador del modelo de lenguaje visual.

**Hay que hacer la suma y contrastarla con la evaluación de avance de la S10** antes de cerrar el
alcance. Si no cuadra, hay tres palancas, en este orden:

1. Recortar clases (v1 cierra con **casco y chaleco**; es un resultado de ingeniería, no una
   rebaja, y se justifica con números).
2. Mover el etiquetado a los tres integrantes en sesiones conjuntas.
3. Sacar la Etapa 2 del alcance comprometido y dejarla como extensión demostrada.

## V10 · ¿Esto sirve en otra faena? 🟡 ESTRATÉGICO

Es la pregunta que la comisión puede hacer en la defensa, y hoy no hay respuesta.

No se puede medir sin dos faenas, pero **sí se puede diseñar para ello y decirlo**: separar el
**modelo** (genérico) de la **configuración** (zonas, reglas, catálogo de EPP, umbrales — todo en
la base de datos), y declarar en el informe el protocolo de puesta en marcha para un cliente
nuevo: N imágenes de su faena, M horas de reetiquetado, recalibración de umbrales.

## Resumen: qué hacer esta semana

| # | Verificación | Costo | Fecha límite | Estado |
|---|---|---|---|---|
| V1 | Confirmar acceso al video, por escrito | 1 correo | S3 | ✅ **Cerrada** — ADR-011 |
| V2 | Tabla de píxeles sobre objetivo por cámara | 20 min | **S3** | 🔴 Abierta |
| V3 | Definir la métrica de evento | ya escrita, falta acordarla | **S4** | 🟠 Falta acordarla |
| V9 | Suma de horas contra el calendario | 1 h | **S4** | 🟠 Abierta |
| V5 | Matriz de EPP exigido por área de la obra | 1 correo | S5 | 🟠 Abierta |
| — | Grabar los 20-30 min de video propio | 1 tarde | **S5** | 🔴 Nueva, de V1 |
| V4 | Presupuesto de VRAM medido | 2 h | S6 | 🟡 Abierta |
| V6 | Experimento de asociación EPP-persona | 1 día | S8 | 🟡 Abierta |

> **Queda un solo bloqueante: V2.** Si los cascos no tienen píxeles suficientes a la distancia de
> la obra, no se cambia de propuesta —se cambia dónde va la cámara, o se pasa a *tiling*—, pero
> hay que saberlo antes de etiquetar la primera imagen.
>
> Y la tarea que V1 dejó en su lugar no es de papel: **sin los 20-30 minutos de video propio, en
> la S15 no hay nada que demostrar.** Los datasets públicos entrenan; no prueban.
