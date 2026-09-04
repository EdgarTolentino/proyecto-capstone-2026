# Manifiesto de datos — origen y uso

> Registro de procedencia del material con que se entrena y se evalúa. Sirve para dos cosas
> concretas: poder responder en la defensa **de dónde salió cada dato**, y saber qué hay que
> volver a conseguir si un lote resulta inservible.

**La regla: ningún dato entra al entrenamiento ni a la evaluación sin una fila en este
documento.** El uso es académico, dentro del Portafolio de Título.

## 1. La división que manda

Sale del [ADR-011](../arquitectura/adr/011-dominio-configurable.md) y no se negocia:

| | Origen | Tipo | Para qué |
|---|---|---|---|
| **Entrenamiento** | Datasets públicos | Imágenes | Preentrenar el detector de persona / casco / chaleco |
| **Prueba y demostración** | Grabación propia en obra | **Video** | Conjunto de prueba, tracks, eventos, defensa de S15 |

**Por qué importa la columna "tipo":** un dataset de imágenes sueltas no tiene tiempo. No produce
tracks, no permite reglas en segundos, no puede correr
`test_la_regla_en_segundos_es_invariante_a_la_cadencia` y no evalúa un solo evento. Es material de
entrenamiento y **jamás** conjunto de prueba. Confundir las dos cosas es el error que dejaría el
proyecto sin nada que defender.

## 2. Inventario

Se llena con `scripts/inventario_video.py`, que saca de cada archivo lo que aquí importa sin
pedir ninguna dependencia — solo `ffprobe`:

```bash
python3 "Fase 2/sistema/scripts/inventario_video.py" ruta/a/los/videos
```

### Lote 1 — descargado el 2026-09-04 · bancos de video de stock

| Archivo | Resolución | fps | seg | Orient. | Cámara | Uso |
|---|---|---|---|---|---|---|
| `vecteezy_construction-works-in-hong-kong_28840504` | 1280×720 | 24 | 59,0 | horizontal | **fija** | **Prueba** |
| `vecteezy_construction-of-a-house-workers-clear-a-place…` | 1280×720 | 25 | 6,0 | horizontal | deriva leve | Entrenamiento |
| `16707074_720_1280_30fps` | 720×1280 | 30 | 25,9 | **vertical** | deriva leve | Entrenamiento |
| `14656570_720_1280_30fps` | 720×1280 | 30 | 16,0 | **vertical** | **se mueve** | Entrenamiento |

**Total: 107 s (1,8 min) · 534 cuadros a 5 fps.**

Un solo archivo del lote cumple las dos condiciones de un conjunto de prueba —cámara fija y
duración utilizable—: el de Hong Kong, con 59 s. Los otros tres son material de entrenamiento:
dos verticales, que desperdician el 44 % del canvas del detector en relleno, y uno de 6 s.

### Cómo se detecta que la cámara se mueve

El script compara la franja perimetral de cada cuadro contra el primero y toma la **mediana** de
las diferencias, no la media. La media da falsos positivos: basta con que una esquina tenga gente
trabajando para dispararla — de hecho, con la media el clip de Hong Kong salía marcado como *se
mueve* siendo de cámara fija. La mediana exige que **la mayoría** del fondo haya cambiado, que es
lo que ocurre en un paneo y no cuando solo se mueve lo que hay dentro del encuadre.

Umbrales: `<8` fija · `8-20` deriva leve · `>20` se mueve.

### Píxeles sobre objetivo — medición real (V2)

Medido sobre un cuadro nativo del clip de Hong Kong, con rejilla de 10 px:

| Posición en el cuadro | Ancho del casco | Tras reescalar a 560 | ¿Sobrevive? |
|---|---|---|---|
| Primer plano | ~60 px | ~26 px | ✅ |
| Media distancia | ~63 px | ~28 px | ✅ |
| Fondo del encuadre | ~40 px | **~17 px** | ❌ |

Con la entrada del detector en 560 px, un casco necesita **≥46 px en el cuadro** para llegar a los
20 px que hacen falta. En este material lo cumplen los cascos cercanos y medios; **los del fondo
no**.

**La conclusión que manda:** subir la cámara a 4K no cambia nada. Un casco que en 1280 mide 60 px
mide 90 px en 1920, pero el factor de reescalado baja de 0,44 a 0,29 y el resultado en la entrada
del detector es **el mismo**. Lo que mueve la aguja es el **ángulo de visión** —cuánta escena cabe
en el cuadro— y el ***tiling***: partir el cuadro y correr el detector sobre cada trozo.

### Campos obligatorios de cada fila

URL o banco de origen · fecha de descarga · duración o número de imágenes · clases presentes ·
si la cámara es fija.

## 3. El video propio

Es el activo insustituible del proyecto. Protocolo mínimo:

| Punto | Criterio |
|---|---|
| Duración | 20-30 min continuos, no clips sueltos — hacen falta tracks largos |
| Cámara | **Fija**, en trípode. Una cámara que se mueve invalida las zonas ([V8](06-verificaciones-criticas.md)) |
| Encuadre | A la distancia que resulte de la tabla de V2, no a la que sea cómoda |
| Contenido | Personas con y sin casco, con y sin chaleco, entrando y saliendo de zona |
| Registro | Anotar distancia cámara-sujeto, altura de montaje, resolución y fps reales |

**Autorización — dos papeles distintos, los dos necesarios:**

1. **De la empresa:** autorización escrita para grabar en la obra, con fecha y alcance.
2. **De las personas grabadas:** consentimiento informado, por escrito, que diga uso académico,
   plazo de conservación y derecho a retirarse.

Ambos se guardan **fuera del repositorio** —`.gitignore` bloquea video, pesos y datos
personales— y en el repositorio queda solo la constancia de que existen.

Sigue aplicando el [ADR-006](../arquitectura/adr/006-sin-identificacion.md): rostro difuminado
antes de escribir cualquier recorte, `track_id` efímeros, sin inferencia de atributos.

**Lo que este material *no* dispara:** el trámite de cinco semanas del Reglamento Interno. Ese
plazo rige para *instalar vigilancia permanente*, no para una grabación puntual y consentida con
fines académicos. Si el proyecto llegara a operar de forma continua en la obra, el trámite
vuelve — y hay que arrancarlo con cinco semanas de anticipación.

## 4. Qué queda por hacer

| # | Tarea | Cuándo | Estado |
|---|---|---|---|
| 1 | **Conseguir más video largo y de cámara fija** — hay 1,8 min de los 20-30 | **S5** | 🔴 |
| 2 | Grabar los 20-30 min con el protocolo de arriba (#10) | S5 | 🔴 |
| 3 | Recortar los verticales a 16:9 o dejarlos fuera del conjunto de prueba | S5 | 🟠 |
| 4 | Conseguir los dos papeles de autorización antes de grabar | Antes de grabar | 🟠 |
| 5 | Repetir la medición de píxeles sobre el video propio | Tras grabar | 🟠 |
| 6 | Anotar cada lote nuevo en el inventario, con el script | Continuo | 🟡 |
