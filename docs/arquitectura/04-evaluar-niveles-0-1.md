# `evaluar.py`: niveles 0 y 1 del plan de evaluación

> Especificación del 3 de octubre de 2026, acordada con Edgar. Parte del #31; destraba el #112.
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

## Nivel 0: `evaluar.py acuerdo A.json B.json`

Entrada: dos exportaciones COCO 1.0 de los mismos cuadros (los 24 con `doble_etiquetado = 1`),
hechas por personas distintas sin ver el trabajo de la otra.

1. Las imágenes se emparejan **por `file_name`**, no por `id`: cada exportación de CVAT numera a
   su manera. Si un archivo está en una y no en la otra, se detiene con error.
2. En cada imagen se emparejan las cajas de A con las de B por IoU ≥ 0,5, **sin mirar la clase**,
   con el emparejamiento óptimo (`entrenamiento._asignar`, húngaro).
3. **Kappa de Cohen** sobre las clases de cada par. Una caja que marcó solo uno de los dos cuenta
   como un par contra la categoría «sin caja». Así, una caja omitida baja el acuerdo en vez de
   desaparecer de la cuenta.
4. **IoU medio** de los pares emparejados.
5. Si el kappa baja de **0,7**, lo imprime como alerta (guía de etiquetado §6). El kappa no detiene
   el script: decidir es de las personas.

## Nivel 1: `evaluar.py deteccion verdad.json predicciones.json --recorte x1,y1,x2,y2`

1. Las categorías se emparejan **por nombre** (`persona`, `casco`, `chaleco`), no por `id`: el id
   de CVAT depende del orden de las etiquetas en el proyecto y el de `a_coco` sale de
   `CLASES_V1`. Un nombre desconocido detiene el script.
2. Cada caja, de verdad o predicha, va a **dentro del foso** o **fuera** según dónde cae su centro
   en el `--recorte` (px del cuadro). Es la misma regla que `etiquetado.combinar`. Cada región se
   evalúa por separado, sobre todas las imágenes, aunque alguna no tenga cajas en esa región.
3. **mAP50 y mAP50-95**, por clase y en total, con `pycocotools` (`COCOeval`, tipo `bbox`).
   - `maxDets` sube a 300: con umbral 0,05 y mosaico, una imagen puede pasar de las 100
     predicciones que COCO evalúa por defecto, y el resto se perdería en silencio. El JSON
     registra el máximo de predicciones que tuvo una imagen.
4. **Precisión y recall por clase con el umbral de la regla (0,45)**: es el que decide si se abre
   un hallazgo. Una predicción acierta si su IoU con una caja verdadera de la misma clase es ≥ 0,5
   (emparejamiento óptimo, una caja verdadera por predicción). El umbral se puede cambiar con
   `--umbral`.
5. Las cajas repetidas que deja el mosaico (~1-2 %, #108) cuentan como falsos positivos. No se
   filtran: es lo que vería el sistema.

## Salida

Un JSON con las métricas y lo necesario para reproducirlas, como pide el `CLAUDE.md`:

- commit del repositorio (`git rev-parse HEAD`) y si había cambios sin confirmar;
- SHA-256 de cada archivo de entrada (verdad y predicciones, o A y B);
- parámetros: recorte, umbrales, IoU, `maxDets`;
- la versión del modelo que viene en `info.description` de las predicciones;
- **limitaciones declaradas:** los 240 cuadros salen de un solo video, en 4 tramos, así que no hay
  intervalos de confianza por remuestreo de video (`02-plan-de-evaluacion.md`). Tampoco hay
  prevalencia de incumplimiento, porque el nivel 1 mide objetos, no eventos.

Además imprime una tabla en Markdown para pegarla en el #31.

## Código

| Archivo | Qué hace |
|---|---|
| `gepp_vision/evaluacion/__init__.py` | Exporta las dos funciones de entrada |
| `gepp_vision/evaluacion/coco.py` | Lee COCO 1.0, indexa por `file_name`, traduce categorías por nombre y separa por región |
| `gepp_vision/evaluacion/acuerdo.py` | Kappa de Cohen e IoU medio. Python puro, sin pycocotools |
| `gepp_vision/evaluacion/deteccion.py` | mAP con pycocotools; precisión y recall al umbral |
| `scripts/evaluar.py` | Subcomandos `acuerdo` y `deteccion`, escritura del JSON y de la tabla |
| `packages/gepp-vision/pyproject.toml` | `pycocotools` como dependencia (BSD; ya está en `uv.lock` por RF-DETR; no está en la lista de prohibidas del CI) |
| `tests/test_evaluacion.py` | Ver abajo |

## Pruebas

Casos sintéticos con resultado conocido, sin GPU, que corren en el CI:

- Predicción idéntica a la verdad: mAP50 = mAP50-95 = 1,0; precisión = recall = 1,0.
- Sin predicciones: mAP 0, recall 0.
- Una caja de más y una de menos, con precisión y recall calculados a mano.
- **Extremos (regla 5):** IoU justo en 0,5 (empareja) y apenas debajo (no empareja); confianza
  justo en 0,45 (cuenta), 0,25 y 0,75 (con valores diádicos, que dan resultados exactos); una
  entrada inválida (categoría desconocida, archivo que falta en una de las dos exportaciones).
- Kappa con una tabla calculada a mano, más los dos extremos: acuerdo total (1,0) y acuerdo igual
  al azar (0,0).
- Región: una caja con el centro justo en el borde del recorte va a un solo lado.
- `maxDets`: una imagen con más de 100 predicciones no pierde las que sobran.
- Cada prueba se valida inyectándole el defecto que dice cuidar (regla 4).

## Tamaño

Cerca del límite de 400 líneas. Si se pasa, se divide en dos PR, primero el nivel 0 y después el
nivel 1, y se avisa antes de abrir el primero.
