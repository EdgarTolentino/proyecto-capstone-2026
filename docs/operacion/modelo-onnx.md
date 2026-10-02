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

Un video queda en `error` después de 3 intentos. Corregida la causa, "Reprocesar" lo
devuelve a la cola.

## Entrenar y exportar un modelo (solo en la máquina con GPU)

```
make setup-gpu
uv run python scripts/descargar_datasets.py ~/datos/gepp/crudos
uv run python scripts/preparar_dataset.py ~/datos/gepp/crudos ~/datos/gepp/epp-v1 \
    --pesos-coco ~/.roboflow/models/rf-detr-medium.pth --variante medium
uv run python scripts/entrenar.py ~/datos/gepp/epp-v1 ~/modelos/rfdetr-n-epp-v1
uv run python scripts/exportar_onnx.py ~/modelos/rfdetr-n-epp-v1 ~/datos/gepp/epp-v1
```

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
