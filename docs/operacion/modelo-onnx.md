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
{"version": "rfdetr-n-epp-v1", "clases": {"1": "persona", "2": "casco", "3": "chaleco"}}
```

Clases válidas: `persona`, `casco`, `chaleco`, `lentes`, `guantes`, `arnes`, `calzado`.

## Configurarlo

En `Fase 2/sistema/.env`, **sin** `GEPP_GUION_FALSO`:

```
GEPP_MODELO_RUTA=/ruta/a/rfdetr-n-epp-v1.onnx
GEPP_UMBRAL_CONFIANZA=0.5
```

Si el archivo no existe, el trabajador se detiene al arrancar y lo dice.

## Exportar un modelo (solo en la máquina con GPU)

```
make setup-gpu
uv run python -c "from rfdetr import RFDETRNano; RFDETRNano(pretrain_weights='pesos.pth').export(output_dir='modelos')"
```

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
