# Correr el sistema con un modelo real (ONNX)

Sin modelo, el trabajador usa el detector simulado (`GEPP_GUION_FALSO`). Con un modelo,
usa RF-DETR exportado a ONNX, que corre en CPU: no hace falta GPU.

## Qué se necesita

Dos archivos, uno junto al otro:

| Archivo | Qué es |
|---|---|
| `rfdetr-n-epp-v1.onnx` | El modelo exportado |
| `rfdetr-n-epp-v1.clases.json` | Qué clase es cada índice del modelo |

El `.clases.json` tiene esta forma. Los índices que no aparecen se ignoran:

```json
{"version": "rfdetr-n-epp-v1", "clases": {"0": "persona", "1": "casco", "2": "chaleco"}}
```

**No se escribe a mano.** Lo genera `scripts/exportar_onnx.py`, que lo contrasta con las cajas
verdaderas de validación, clase por clase, y se niega a exportar si alguna no queda verificada.
La razón: un modelo entrenado por nosotros devuelve la **posición** de la clase, que empieza en
0 (0 = persona). El RF-DETR preentrenado en COCO, en cambio, devuelve el **id de categoría COCO**
(1 = persona). Así lo hace el código de rfdetr 1.11 (`remap_category_ids` en
`datasets/coco.py`). En un modelo de prueba de 1 época se observó para casco: los 14 cascos
contrastados salieron con id 1, con umbral 0,3. Un mapa que empezaba en 1 los habría
convertido en personas.

Clases válidas: `persona`, `casco`, `chaleco`, `lentes`, `guantes`, `arnes`, `calzado`.

## Configurarlo

En `Fase 2/sistema/.env`, **sin** `GEPP_GUION_FALSO`:

```
GEPP_MODELO_RUTA=/ruta/a/rfdetr-n-epp-v1.onnx
GEPP_UMBRAL_CONFIANZA=0.25
```

Si el archivo no existe, el trabajador se detiene al arrancar y lo dice.

## Lo que se mide y se muestra: mosaico en la GPU (#203)

**Con ONNX en CPU y sin mosaico, en el CCTV de prueba el trabajador no ve ningún casco.** El
modelo achica el cuadro de 1920×1080 a su entrada (384 o 512 px) y un casco del fondo queda en
1 o 2 px. Las cifras de #31 se midieron con mosaico; sin él, el recall de casco es 0 (#203).
ONNX en CPU sirve para desarrollar en los portátiles, **no para medir ni para la demostración**.

Para eso, en la máquina con GPU (`make setup-gpu`):

```
GEPP_MODELO_MOTOR=rfdetr
GEPP_MODELO_VARIANTE=small
GEPP_MODELO_RUTA=/ruta/a/rfdetr-s-epp-v2.pth     # con rfdetr-s-epp-v2.clases.json al lado
```

`GEPP_MOSAICO_LADO` vacío toma la entrada del modelo (384 el nano, 512 el small). Un valor
distinto detiene el arranque: el modelo reescalaría cada mosaico y los objetos chicos llegarían
más chicos que en la medición.

El mapa de clases se busca con el mismo nombre que los pesos: `modelo.pth` va con
`modelo.clases.json`. Si los pesos se llaman `checkpoint_best_total.pth`, hay que copiarlos o
enlazarlos con el nombre del modelo. Un motor o una variante desconocidos detienen el arranque.

Además, la cámara necesita una **zona `mosaico`** en su perfil (`perfiles/construccion.yaml`
trae un ejemplo comentado): el trabajador analiza solo la caja que encierra ese polígono,
ampliada `GEPP_MOSAICO_FACTOR` veces y partida en mosaicos. Lo de fuera de la zona no se
analiza, y en la evidencia esa parte sale pixelada: ahí no se buscaron personas, así que no se
sabe si hay un rostro que tapar (ADR-006). Sin la zona, el cuadro entero, como antes. A lo sumo
una por cámara: con dos, el video queda en error con su motivo.

`make semilla` no agrega zonas a una base que ya tiene faena: carga el perfil solo la primera
vez. En una base existente, la zona se agrega a mano (coordenadas normalizadas 0..1):

```sql
INSERT INTO zona (area_id, fuente_id, nombre, tipo, poligono)
SELECT area_id, id, 'Foso', 'mosaico',
       '[[0.3125, 0.2037], [0.7292, 0.2037], [0.7292, 0.6759], [0.3125, 0.6759]]'::jsonb
FROM fuente WHERE id = 1;
```

Los videos ya procesados no cambian: se reprocesan para que la zona aplique.

Costo medido el 2026-10-25 sobre 24 cuadros de 1920×1080 (#203):

| Modelo | Sin mosaico | Con mosaico, CPU (8 núcleos) | Con mosaico, GPU (RTX 4070 Laptop) |
|---|---|---|---|
| small v2, mosaicos de 512 | 0,029 s/cuadro (GPU) | 4,48 s/cuadro | 0,49 s/cuadro |
| nano v1, mosaicos de 384 | 0,024 s/cuadro (GPU) | 7,82 s/cuadro | 1,04 s/cuadro |

A 5 fps, el small con mosaico en la GPU procesa un minuto de video en unos 2,5 minutos. No es
tiempo real. Regla de ADR-010: nunca entrenar y servir a la vez en esa máquina.

**El mosaico es necesario, pero no basta.** En la corrida real del 2026-10-25 (#203), en 122 de
los 157 hallazgos de casco comparables con la verdad, la persona tenía casco: con el recall de
casco y chaleco actual en el CCTV, inferir el incumplimiento por ausencia da sobre todo falsas
alarmas. Hasta que eso se resuelva (#31), los hallazgos no se presentan como incumplimientos
confirmados.

## Probar un video propio

```
make demo-todo VIDEO=ruta/al/video.mp4 MODELO=ruta/rfdetr-nano.onnx
```

Recrea la base de demo, procesa el video con el modelo y deja la API y la web arriba
(`http://localhost:5173`). Para apagar: `make demo-apagar`. Sin la web: `make demo VIDEO=... MODELO=...`.

Si el video falla, igual se levantan la API y la web. El motivo queda en la cola de videos
(`error_motivo`), y también en la salida de la demo:

| Motivo | Qué significa | Qué hacer |
|---|---|---|
| `No se pudo leer el video: ...` | El archivo no es un video o está dañado | Probar con otro archivo, o convertirlo a MP4 (H.264) |
| `... no tiene reglas activas` / `ninguna regla se puede aplicar` | La cámara no tiene reglas que evaluar | Revisar las reglas del área y usar "Reprocesar" |
| `falta el mapa de clases junto al modelo` | Falta el `.clases.json` al lado del `.onnx` | Copiarlo junto al modelo |
| `la cámara tiene 2 zonas de mosaico; admite una` | El perfil declara más de una zona `mosaico` en esa cámara | Dejar una y usar "Reprocesar" |
| `... mosaicos por cuadro (tope 64) ...` | La zona, el factor u `objeto_max_px` dan demasiados mosaicos | Achicar la zona o bajar `GEPP_MOSAICO_FACTOR` |
| `el recorte ... no cubre ningún píxel ...` | La zona `mosaico` es tan chica que no llega a un píxel | Redibujarla |

Un video queda en `error` después de 3 intentos. Corregida la causa, "Reprocesar" lo
devuelve a la cola.

## Entrenar y exportar un modelo (solo en la máquina con GPU)

```
make setup-gpu
uv run python scripts/descargar_datasets.py ~/datos/gepp/crudos
uv run python scripts/preparar_dataset.py ~/datos/gepp/crudos ~/datos/gepp/epp-v2 \
    --pesos-coco ~/.roboflow/models/rf-detr-medium.pth --variante medium \
    --pesos-epp ~/modelos/rfdetr-n-epp-v1/checkpoint_best_total.pth \
    --clases-epp ~/modelos/rfdetr-n-epp-v1/rfdetr-n-epp-v1.clases.json
uv run python scripts/entrenar.py ~/datos/gepp/epp-v2 ~/modelos/rfdetr-n-epp-v2
uv run python scripts/exportar_onnx.py ~/modelos/rfdetr-n-epp-v2 ~/datos/gepp/epp-v2
```

`--pesos-epp` es el modelo anterior: completa los cascos y chalecos que una fuente no marca
(#37). En la primera ronda todavía no hay modelo EPP, así que se usa `--sin-epp`: los cascos y
chalecos sin caja quedan como fondo, como en la v1.

`exportar_onnx.py` deja junto al modelo el `.onnx`, el `.clases.json` y `verificacion.json`
con el acierto del mapa y la comparación ONNX contra PyTorch. Mientras se entrena no se corre la
demo en la misma máquina (ADR-010).

Para probar el recorrido antes de tener el modelo propio (#31), sirve el RF-DETR Nano de
COCO con `{"version": "coco-nano", "clases": {"1": "persona"}}`: detecta personas y nada más,
así que todas salen "sin casco".

## Cuánto tarda

Medido el 24-sep-2026 con RF-DETR Nano, en videos de 1280×720:

| Detector | Tiempo por cuadro |
|---|---|
| ONNX en CPU (portátil) | ~130 ms: alcanza para 5 fps en tiempo real |
| PyTorch en GPU (RTX 4070 Laptop) | ~25-35 ms |

Los dos ven lo mismo: sobre los mismos cuadros dan las mismas cajas y confianzas
(`tests/test_detector_rfdetr.py`).
