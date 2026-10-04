# `evaluar.py`: niveles 0 y 1 del plan de evaluación

> Especificación del 3 de octubre de 2026, acordada con Edgar y revisada el 4 de octubre (sesgo por
> pre-etiquetas, mAP por tamaño, orden de los PR; luego umbral de la regla y aviso de score mínimo).
> Parte del #31; destraba el #112.
> Los niveles están definidos en [`02-plan-de-evaluacion.md`](02-plan-de-evaluacion.md).

## Alcance

| Nivel | Pregunta | Entra |
|---|---|---|
| **0 · Dato** | ¿Coinciden los dos etiquetadores? | **Sí** |
| **1 · Detección** | ¿El modelo ve los objetos? | **Sí** |
| 2 · Seguimiento, 3 · Evento, 4 · Alerta | — | **No** |

Los niveles 2 a 4 necesitan video continuo con personas seguidas en el tiempo y eventos marcados
con inicio y fin. Hoy hay 240 cuadros sueltos (`datos/lote0.csv`), uno cada varios segundos: con
eso no se calcula HOTA ni F1 de evento. Quedan en un issue aparte, para cuando haya video anotado.

## Flujo: predecir y medir por separado

| Paso | Dónde | Cómo |
|---|---|---|
| **Predecir** | Máquina con GPU | `scripts/preetiquetar.py ... --umbral 0.05`. No cambia: ya corre lo que pide el #112 (mosaico dentro del foso, modelo normal fuera, cajas bajo 10 px descartadas) y `etiquetado.a_coco` ya escribe la confianza en `score`. El umbral bajo hace falta porque el mAP recorre la curva completa |
| **Medir** | Cualquier máquina, también el CI | `scripts/evaluar.py`: lee la verdad (exportación COCO 1.0 de CVAT) y las predicciones. Sin GPU ni modelo |

Así la métrica sale del mismo proceso que generó las pre-etiquetas, y medir no obliga a volver a
correr el modelo.

## El sesgo de las pre-etiquetas

La verdad de los 240 cuadros **no es independiente del modelo**: las personas corrigieron las
cajas que el modelo propuso. Quien corrige tiende a dejar como está una caja «casi bien», así que
el modelo medido contra esa verdad sale **mejor de lo que es**. No se puede rehacer: las
pre-etiquetas ya están cargadas y el etiquetado está en curso.

Se declara y se mide:

- Cada corrida del nivel 1 dice de dónde sale su verdad con `--origen-verdad`, obligatorio:
  `con-preetiquetas` o `sin-preetiquetas`. Va al JSON y al título de la tabla.
- Los **24 cuadros del doble etiquetado** se etiquetan **sin pre-etiquetas** (#112). El modelo
  contra esa verdad limpia es la cifra honesta.
- Para comparar en igualdad, la corrida con pre-etiquetas se repite sobre esos mismos 24 cuadros
  (`--imagenes-de`). La diferencia entre las dos es el **sesgo estimado**, y se reporta en el #31
  junto a las dos cifras. Con 24 cuadros es una estimación gruesa, y así se dice.

## Nivel 0: `evaluar.py acuerdo A.json B.json`

Entrada: dos exportaciones COCO 1.0 de los mismos cuadros (los 24 con `doble_etiquetado = 1`),
hechas por personas distintas sin ver el trabajo de la otra.

1. Las imágenes se emparejan **por `file_name`**, no por `id`: cada exportación de CVAT numera a
   su manera. Si un archivo está en una y no en la otra, se detiene con error.
2. En cada imagen se emparejan las cajas de A con las de B por IoU ≥ 0,5, **sin mirar la clase**,
   con el emparejamiento óptimo (`entrenamiento._asignar`, húngaro: el máximo de pares con
   IoU ≥ 0,5; a igual cantidad, la mayor IoU).
3. **Kappa de Cohen** sobre las clases de cada par. Una caja que marcó solo uno de los dos cuenta
   como un par contra la categoría «sin caja». Así, una caja omitida baja el acuerdo en vez de
   desaparecer de la cuenta.
4. **IoU medio** de los pares emparejados.
5. Si el kappa baja de **0,7**, lo imprime como alerta (guía de etiquetado §6). El kappa no detiene
   el script: decidir es de las personas.
6. **Limitación declarada:** A etiquetó partiendo de las pre-etiquetas y B desde cero. El kappa
   mezcla el desacuerdo entre personas con el efecto de las sugerencias del modelo. A esta escala
   no se puede separar; el JSON lo dice.

## Nivel 1: `evaluar.py deteccion verdad.json predicciones.json --recorte x1,y1,x2,y2 --origen-verdad ...`

1. Las categorías se emparejan **por nombre** (`persona`, `casco`, `chaleco`), no por `id`: el id
   de CVAT depende del orden de las etiquetas en el proyecto y el de `a_coco` sale de
   `CLASES_V1`.
   - `tiene_pequenos` es una etiqueta de imagen (*tag*) en CVAT. La exportación COCO 1.0 la trae
     en `categories` pero sin cajas (comprobado el 4-oct con la tarea `prueba-youtube-lote0`).
     Se ignora.
   - Cualquier otro nombre desconocido detiene el script.
2. Las imágenes se emparejan por `file_name`. Toda imagen de la verdad tiene que estar en las
   predicciones, con el mismo ancho y alto; si no, error. Las predicciones de imágenes que no están
   en la verdad se ignoran: así las predicciones de los 240 cuadros sirven también para los 24.
   `--imagenes-de otra.json` limita la evaluación a las imágenes de otro archivo COCO.
3. Una predicción sin `score` detiene el script: casi seguro se pasó la verdad como predicciones.
4. Cada caja, de verdad o predicha, va a **dentro del foso** o **fuera** según dónde cae su centro
   en el `--recorte` (px del cuadro, borde incluido). Es la misma regla que `etiquetado.combinar`.
   Cada región se evalúa por separado, sobre todas las imágenes, aunque alguna no tenga cajas en
   esa región.
5. **mAP50 y mAP50-95**, por clase y en total, con `pycocotools` (`COCOeval`, tipo `bbox`).
   - `maxDets` sube a 300: con umbral 0,05 y mosaico, una imagen puede pasar de las 100
     predicciones por clase que COCO evalúa por defecto, y el resto se perdería en silencio
     (comprobado: 150 cajas perfectas dan mAP50 0,66 con 100 y 1,0 con 300). El JSON registra el
     máximo de predicciones que tuvo una imagen en una clase.
   - Las métricas se leen de `COCOeval.eval["precision"]`, no de `summarize()`, que para los
     tamaños vuelve a usar 100.
   - Una clase **sin cajas verdaderas** en la región no tiene mAP (`null`), no 0. Una clase con
     verdad y sin predicciones da 0.
   - Una región **sin predicciones** no pasa por `COCOeval`: `loadRes([])` se cae.
6. **mAP por tamaño** (COCO: chico < 32², mediano < 96², grande el resto, en px de área), en total
   y por clase. En CCTV de obra casi todo es chico: es el argumento del mosaico.
7. **Precisión y recall por clase al umbral de la regla** (`Regla.confianza_minima`, 0,45), el
   mismo para las tres clases (decisión de Edgar del 4-oct). El agregador filtra con él tanto a
   las personas (`agregador.py`, `procesar_cuadro`) como al EPP (`epp_faltante`), y ByteTrack crea
   identidades desde ese mismo valor: es el que decide si se abre un hallazgo. Una persona entre
   0,25 y 0,45 solo mantiene viva una identidad en el seguidor; no se mide aparte.
   `--umbral` lo cambia para todas las clases. Una predicción acierta si su IoU con una caja
   verdadera de la misma clase es ≥ 0,5, con el emparejamiento óptimo: el **máximo de pares** con
   IoU ≥ 0,5 y, a igual cantidad, la mayor IoU (una caja verdadera por predicción).
   - **Score mínimo.** El mAP necesita las predicciones desde 0,05 (ver «Predecir»). Si se corrió
     `preetiquetar.py` con un umbral más alto, la curva se corta y el mAP sale bajo sin que nada
     falle. El JSON registra el score mínimo de las predicciones evaluadas y la tabla avisa desde
     1/16 (0,0625), no en 0,05 justo: el score viene en float32 y el mínimo de un archivo bien
     hecho queda apenas encima (0,050000179 en los 240 cuadros del 4-oct).
8. Cada fila lleva cuántas cajas verdaderas y predichas tiene. Una clase con pocas cajas da una
   cifra poco fiable, y el lector tiene que verlo. Ejemplo: en las pre-etiquetas de los 240
   cuadros hay 3 chalecos contra 1446 personas.
9. Las cajas repetidas que deja el mosaico (~1-2 %, #108) cuentan como falsos positivos. No se
   filtran: es lo que vería el sistema.

## Salida

Un JSON con las métricas y lo necesario para reproducirlas, como pide el `CLAUDE.md`:

- commit del repositorio (`git rev-parse HEAD`) y si había cambios sin confirmar;
- SHA-256 de cada archivo de entrada (verdad y predicciones, o A y B);
- parámetros: recorte, umbral de confianza, IoU, `maxDets`, score mínimo de las
  predicciones, origen de la verdad, imágenes evaluadas;
- la versión del modelo que viene en `info.description` de las predicciones. Si esa descripción
  trae el recorte del mosaico y no coincide con `--recorte` (tolerancia de 1 px), el script avisa
  por stderr sin detenerse;
- **limitaciones declaradas:** los 240 cuadros salen de un solo video, en 4 tramos, así que no hay
  intervalos de confianza por remuestreo de video (`02-plan-de-evaluacion.md`). Tampoco hay
  prevalencia de incumplimiento, porque el nivel 1 mide objetos, no eventos. Y, si la verdad es
  `con-preetiquetas`, que la cifra está inflada por el sesgo de arriba.

Además imprime una tabla en Markdown para pegarla en el #31.

## Código

| Archivo | Qué hace |
|---|---|
| `gepp_vision/evaluacion/__init__.py` | Exporta las funciones de entrada |
| `gepp_vision/evaluacion/coco.py` | Lee COCO 1.0, indexa por `file_name`, traduce categorías por nombre y separa por región |
| `gepp_vision/evaluacion/deteccion.py` | mAP con pycocotools; precisión y recall al umbral |
| `gepp_vision/evaluacion/reporte.py` | Procedencia (commit, SHA-256), JSON y tabla Markdown |
| `gepp_vision/evaluacion/acuerdo.py` | Kappa de Cohen e IoU medio. Python puro, sin pycocotools |
| `scripts/evaluar.py` | Subcomandos `deteccion` y `acuerdo` |
| `packages/gepp-vision/pyproject.toml` | `pycocotools` como dependencia (BSD; ya está en `uv.lock` por RF-DETR; no está en la lista de prohibidas del CI) |
| `tests/test_evaluacion_*.py` | Ver abajo |

## Pruebas

Casos sintéticos con resultado conocido, sin GPU, que corren en el CI:

- Predicción idéntica a la verdad: mAP50 = mAP50-95 = 1,0; precisión = recall = 1,0.
- Sin predicciones: mAP 0, recall 0, sin pasar por `loadRes`.
- Una caja de más y una de menos, con precisión y recall calculados a mano.
- **Extremos (regla 5):** IoU justo en 0,5 (empareja) y apenas debajo (no empareja); confianza
  justo en 0,45 (cuenta) y en 0,4375 (no cuenta), y con `--umbral 0.5` en 0,5 (cuenta) y 0,25 (no
  cuenta), con valores diádicos, que dan resultados exactos; persona con el mismo umbral que el
  EPP; score mínimo en 0,05 y en 7/128 (sin
  aviso) y justo en 1/16 (con aviso); una
  entrada inválida (categoría desconocida, archivo que falta en una de las dos exportaciones,
  predicción sin `score`, tamaños distintos).
- Kappa con una tabla calculada a mano, más los dos extremos: acuerdo total (1,0) y acuerdo igual
  al azar (0,0).
- Región: una caja con el centro justo en el borde del recorte va a un solo lado.
- `maxDets`: una imagen con más de 100 predicciones de una clase no pierde las que sobran.
- Clase sin verdad: `null`, no 0. Tamaño: una caja chica cuenta en «chico» y no en «grande».
- Cada prueba se valida inyectándole el defecto que dice cuidar (regla 4).

## Tamaño y orden de los PR

No cabe en un PR de menos de 400 líneas, que en CONTRIBUTING cuentan pruebas y documentos. Se
divide en seis, en este orden, más un arreglo aparte. Las líneas de los PR 2 a 5 y del arreglo
son las de `git diff --stat` contra su base el 4-oct; la del 1, la de la spec contra `main`:

| PR | Qué | Líneas | Por qué en este orden |
|---|---|---|---|
| **1** | Esta spec, sola | 184 | Con el código no cabe; se revisa la decisión antes que la implementación |
| **2** | La lectura: `coco.py`, dependencia y pruebas | 324 | Fija el formato de entrada, comprobado con una exportación real |
| **3** | Nivel 1, el cálculo: `deteccion.py` y pruebas | 427 | Es la cifra del H3 (S10). Pasa de 400: se avisa en el PR |
| **4** | Nivel 1, el reporte: `reporte.py` (JSON y tabla) y pruebas | 284 | Fija qué se registra antes de que lo escriba el script |
| **5** | Nivel 1, el script: `scripts/evaluar.py deteccion` y pruebas | 330 | Deja el comando listo para cuando terminen #110 y #111 |
| **6** | Nivel 0: `acuerdo.py`, `scripts/evaluar.py acuerdo` y pruebas | — | Espera el doble etiquetado de Edgar (#112) |
| aparte | `fix/31-asignar-pares`: `entrenamiento._asignar` maximiza la cantidad de pares | 28 | Independiente, desde `main`. Lo usan `exportar_onnx.py` y la precisión y el recall del nivel 1 (PR 3), y lo usará el nivel 0 |

Si un PR se pasa al escribirlo, se avisa antes de abrirlo.
