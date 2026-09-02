# Verificaciones críticas antes de comprometer el proyecto

> Este documento existe porque una revisión adversarial del diseño encontró que **el corpus de
> investigación es sólido donde es fácil investigar y está vacío donde el proyecto se juega**.
> Lo que falta no son más fuentes: son **cálculos y decisiones que nadie ha hecho todavía**.
>
> Las cuatro primeras son baratas —horas, no semanas— y de ellas depende si Guardián EPP es
> viable. **Ninguna línea de código de visión debería escribirse antes de cerrarlas.**

## V1 · ¿Existe el video de faena? 🔴 BLOQUEANTE

**El supuesto que sostiene todo el proyecto y que nadie ha verificado.** Sin video real no hay
dataset propio, no hay entrenamiento, no hay conjunto de prueba y no hay demostración.

Y hay un plazo que nadie metió al cronograma: el sistema debe estar declarado en el **Reglamento
Interno de Orden, Higiene y Seguridad** antes de la primera ingesta de video real, con **30 días
de aviso previo más 5 de remisión** a la autoridad. Son unas **cinco semanas de trámite dentro de
las once de desarrollo**.

| Qué hay que conseguir | Formato |
|---|---|
| Quién entrega el video, de qué áreas y cuánto | Correo, basta |
| Con qué autorización y en qué fecha | Correo |
| Si el sistema ya está declarado en el RIOHS de esa faena | Sí / No / En trámite |

**Fecha límite: S3.** Si en la S3 no hay confirmación escrita, se activa el plan B.

### Plan B, decidido de antemano

Grabar material propio: personas con y sin EPP en un patio o instalación, con una cámara fija a
altura y distancia comparables. Complementado con datasets públicos de CCTV industrial.

No es un fracaso: es un **corpus sustituto declarado**, y el informe explica la diferencia de
dominio. Lo que no puede pasar es descubrirlo en la S9.

## V2 · ¿Cuántos píxeles mide un casco a la distancia real? 🔴 BLOQUEANTE

**Veinte minutos de aritmética que pueden invalidar el caso de uso completo**, y que nadie ha
hecho.

Un casco mide unos 28 cm. A 30 metros, con 1080p y una lente estándar, puede quedar en menos de
10 píxeles de alto: un régimen en el que **ningún detector del mundo** decide si está puesto o no.
En los datasets de CCTV industrial disponibles, más de la mitad de los cascos ya caen en la
categoría "objeto pequeño".

**Cómo hacerlo**, con un solo cuadro de cada cámara:

1. Medir en píxeles la altura de una persona a la distancia típica y a la máxima de la zona.
2. Derivar la altura de la cabeza (≈ 1/7 de la persona) y del torso.
3. Contrastar contra los umbrales operativos:

| Para evaluar | Umbral mínimo sugerido |
|---|---|
| Casco | ≥ 40 px de alto de cabeza |
| Chaleco | ≥ 80 px de alto de persona |
| Lentes, guantes | ≥ 120 px de alto de persona (probablemente fuera de alcance) |

**El resultado es una tabla `zona × EPP × evaluable`** que se carga en la base de datos, y el
motor de reglas la respeta: **nunca exige en una zona un EPP que la cámara no alcanza a
resolver**. Eso mata de raíz el modo de fallo número uno de estos sistemas.

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

## V5 · ¿Qué EPP exige realmente la faena? 🟠 IMPORTANTE

El catálogo de clases se está eligiendo desde datasets de **construcción occidental y china**
(casco, chaleco, guantes, lentes), no desde el EPP minero chileno. En faena el elemento relevante
incluye **respirador media cara, autorrescatador, arnés con doble cola, botas con puntera, buzo
reflectante completo** (no chaleco) y **barbiquejo**.

Entrenar clases de "safety vest" cuando en la faena se usa buzo reflectante completo es entrenar
para otro problema.

**Qué hacer:** pedir la matriz de EPP por área del reglamento interno de la faena, cruzarla con la
tabla de V2, y quedarse con **5-7 clases detectables**, descartando por escrito las que no lo son.

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

| # | Verificación | Costo | Fecha límite |
|---|---|---|---|
| V1 | Confirmar acceso al video, por escrito | 1 correo | **S3** |
| V2 | Tabla de píxeles sobre objetivo por cámara | 20 min | **S3** |
| V3 | Definir la métrica de evento | ya escrita, falta acordarla | **S4** |
| V5 | Matriz de EPP exigido por área de la faena | 1 correo | S5 |
| V4 | Presupuesto de VRAM medido | 2 h | S6 |
| V9 | Suma de horas contra el calendario | 1 h | **S4** |
| V6 | Experimento de asociación EPP-persona | 1 día | S8 |

> **V1 y V2 son bloqueantes de verdad.** Si el video no llega y los cascos no tienen píxeles
> suficientes, la decisión racional es cambiar de propuesta — y es infinitamente más barato
> descubrirlo en la S3 que en la S12.
