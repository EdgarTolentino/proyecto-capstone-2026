# Plan de evaluación y aseguramiento de calidad

> El mAP del detector **no es la métrica del producto**. El mAP mide cuadros; el prevencionista
> consume **alertas**. Casi toda la literatura de EPP publica mAP sobre su propio dataset y no
> descompone los falsos positivos ni reporta alarmas por hora. Ese hueco es una oportunidad: es
> exactamente lo que este proyecto puede llenar y convertir en evidencia de título.

## Jerarquía de cinco niveles

Cada nivel responde a una pregunta distinta. Reportar solo el nivel 1, como hace casi todo el
mundo, es responder la pregunta fácil.

| Nivel | Pregunta | Métricas |
|---|---|---|
| **0 · Dato** | ¿Están bien etiquetadas las imágenes? | Kappa de Cohen e IoU entre anotadores sobre el 10 % doble etiquetado |
| **1 · Detección** | ¿El modelo ve los objetos? | mAP50, mAP50-95, AP/precisión/recall **por clase**, matriz de confusión con el fondo |
| **2 · Seguimiento** | ¿Mantiene la identidad? | HOTA (con DetA y AssA), IDF1, cambios de identidad por persona-minuto, fragmentación |
| **3 · Evento** | ¿Detecta el incumplimiento *como hecho*? | Sensibilidad, precisión y F1 **de evento**; mAP temporal a tIoU {0,3 · 0,5 · 0,7}; **falsas alarmas por hora de video** |
| **4 · Alerta** | ¿Sirve para algo? | Alertas por turno y cámara; **tasa de alertas accionables**; latencia de detección; VPP confirmado por el prevencionista |

> El nivel 4 es el que ningún proveedor publica y el que mejor defiende el proyecto.
> **Tasa de alertas accionables** = hallazgos que terminan en acción correctiva ÷ hallazgos
> emitidos. Sale gratis del flujo de triage.

## Cómo se empareja un evento con la realidad

Un evento predicho **empareja** con un evento real si comparten track y zona y su solape temporal
supera un umbral. Los parámetros viven **en la misma tabla que las reglas**, versionados:

| Parámetro | Valor de partida |
|---|---|
| `tolerancia_inicio_s` | 3,0 |
| `tolerancia_fin_s` | 5,0 |
| `solape_minimo` (tIoU) | 0,3 |
| `duracion_minima_evento_s` | 4,0 |
| `gap_fusion_s` | 20,0 |
| `duracion_maxima_evento_s` | 180,0 |

Más dos métricas de patología que revelan lo que el F1 esconde:

- **Tasa de fragmentación** = eventos predichos por evento real. Si vale 3, el sistema está
  partiendo un incumplimiento en tres y el conteo por zona está inflado.
- **Latencia de detección** = segundos entre el inicio real y la emisión del evento.

## Reglas de partición del dataset — el riesgo metodológico número uno

Con muestreo a 5 fps, dos cuadros vecinos son **casi copias**. Partir el dataset por imagen es
fuga de datos pura, y produce una métrica optimista y falsa. La literatura mide la diferencia
entre partir por registro y partir por sujeto en cerca del doble de error.

**Reglas duras, forzadas por tests de CI:**

1. La unidad de partición es el **video**, nunca el cuadro.
2. El conjunto de prueba reserva **al menos dos cámaras completas** nunca vistas en entrenamiento,
   y **un día completo**.
3. El conjunto de prueba se **congela antes de tocar el modelo** y no se vuelve a mirar hasta la
   S14. La partición se versiona en un archivo en git desde la S6.
4. Deduplicación por similitud perceptual antes de etiquetar. Un test falla si un mismo hash
   aparece en dos particiones.

## Tamaño del conjunto de prueba

Se dimensiona por **número de eventos positivos**, no por imágenes: **mínimo 60 incumplimientos
reales** anotados, repartidos en **≥6 videos** y **≥3 cámaras**.

Y se documenta la **prevalencia** junto a cada métrica: la línea base de la precisión media es la
prevalencia, no 0,5.

## Métricas prohibidas en este proyecto

El incumplimiento es un evento **raro**. Con clases desbalanceadas, tres métricas mienten:

| Prohibida | Por qué |
|---|---|
| Exactitud (*accuracy*) | Un sistema que nunca alerta acierta el 97 % |
| Especificidad | Domina la clase mayoritaria |
| ROC-AUC | Optimista con desbalance |

**En su lugar:** PR-AUC / precisión media, MCC, y falsas alarmas por hora.

Detalle de implementación que sí importa: usar `average_precision_score` de scikit-learn, **nunca**
integración trapezoidal sobre la curva PR — es optimista.

Y un rigor barato que casi nadie hace: **intervalos de confianza del 95 % por remuestreo a nivel
de video** (1.000 réplicas, remuestreando videos completos con reemplazo), no a nivel de cuadro.

## Metas y expectativas honestas

| Métrica | Meta v1 | Comentario |
|---|---|---|
| mAP50 casco y chaleco, dominio propio | ≥ 0,70 | Prometer >0,90 en CCTV de faena es prometer un fracaso |
| F1 de evento (tIoU 0,3) | ≥ 0,75 | La métrica que se defiende |
| Falsas alarmas por hora de video | ≤ 1,0 | Con el umbral de confirmación calibrado |
| Alertas por prevencionista por turno de 12 h | **≤ 6** | Requisito **no funcional**, ver abajo |
| Tasa de alertas accionables | ≥ 30 % | La referencia de la industria sin agregación es <3 % |

> Referencia de contexto: el mismo detector cae de ~90 % a ~73 % de mAP50 **solo por poca luz**, y
> de ~71 % a ~59 % al cambiar de dataset, con el chaleco desplomándose de 58 % a 36 %. Cualquier
> cifra que se prometa tiene que sobrevivir a eso.

## El presupuesto de alertas es un requisito, no un deseo

**≤ 6 avisos por prevencionista por turno de 12 h.** Techo duro absoluto: 1 cada 10 minutos.

Deriva de dos referencias establecidas: el estándar de gestión de alarmas industriales tolera
del orden de una alarma cada diez minutos por operador, y la práctica de ingeniería de
confiabilidad fija en dos incidentes por turno el límite de lo que una persona atiende bien.

**El umbral de confirmación se calibra para respetar el presupuesto, no para maximizar el
recall.** Si se excede, el sistema **degrada solo**: sube el umbral, agrupa por zona y baja a
resumen.

Además se audita la distribución de severidad contra el reparto de referencia **5 % crítica /
15 % alta / 80 % baja**. Si el sistema emite 40 % de críticas, lo que está mal es la
clasificación, no el mundo.

## Aseguramiento de calidad: tres anillos

| Anillo | Cuándo | Presupuesto | Qué corre |
|---|---|---|---|
| **1** | Cada empuje | < 3 min | Pruebas del motor de reglas y del agregador con detecciones sintéticas en JSON (**sin modelo**), lint, tipos, validación del esquema, y comparación del contrato OpenAPI |
| **2** | Cada Pull Request | < 15 min | Conjunto de referencia: 2-3 clips de 10-30 s, modelo nano en ONNX sobre CPU, comparación del JSON de eventos; más pruebas de la API con el detector sustituido por un doble |
| **3** | Nocturno | sin límite | Evaluación completa sobre el conjunto de validación, con GPU |

El anillo 1 es posible porque `gepp-core` es Python puro (ADR-007). Es la razón de que esa
frontera exista.

### El conjunto de referencia no puede ser inestable

La reproducibilidad numérica no está garantizada entre versiones de PyTorch ni entre CPU y GPU.
Por eso el conjunto de referencia **no compara coordenadas ni confianzas exactas**. Compara:

1. número de eventos,
2. clase de cada evento,
3. instantes de inicio y fin con tolerancia de ±1 cuadro muestreado,
4. F1 de evento del clip contra un umbral fijo.

Con semillas, resolución, umbrales y cadencia fijados dentro del test, y la versión del runtime
anclada en el *lockfile*.

## Calidad del dato: lo que se mide antes de entrenar

- **Guía de etiquetado escrita ANTES de abrir la herramienta**, con fotos de casos límite ya
  resueltos: casco colgando del brazo, chaleco abierto, casco sin barbiquejo, persona a más de
  30 m, reflejo en vidrio, persona en un afiche, gorro de tela contra casco.
- **Doble anotación del 10 %** y publicación del acuerdo entre anotadores **en el informe**.
  Si el acuerdo humano es 0,75, ningún modelo puede honestamente reportar 0,95.
- **Negativos duros recolectados a propósito**: conos naranjos, bidones, extintores, señalética,
  ropa de calle naranja, cascos colgados en un perchero, maniquíes, afiches de seguridad. Es la
  contramedida directa contra "chaleco = cualquier cosa naranja" y "casco = cualquier cosa
  redonda y clara". Sin esto, la primera demostración con material real se cae.
- **Aumentación física**, no solo geométrica: niebla, lluvia, poca luz con ruido, reverbero solar.
  Son unas 200 líneas sobre CPU, no requieren datos nuevos, y en la literatura compran del orden
  de +14 puntos de mAP50 en poca luz. Es la mejor relación esfuerzo/resultado de todo el proyecto.
