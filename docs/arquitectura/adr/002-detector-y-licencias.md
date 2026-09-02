# ADR-002 — RF-DETR en lugar de Ultralytics YOLO

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

YOLO de Ultralytics es el camino por defecto: mejor documentación, más tutoriales, entrenamiento
en tres líneas. Es lo que haría cualquier equipo sin mirar la licencia.

## Decisión

**Detector:** RF-DETR (Apache-2.0), variantes N/S. **Seguidor:** ByteTrack vía `roboflow/trackers`
(Apache-2.0). Plan B del detector: D-FINE con receta DEIM **v1**.

Prohibidos en el repositorio: `ultralytics`, `boxmot`, `deimv2`. Un test de CI falla si aparecen
en el *lockfile*.

## Por qué

- Ultralytics es **AGPL-3.0**, y su licenciante sostiene que la licencia alcanza también a **los
  pesos que uno mismo entrena** ("the models produced by that training code"). Servir inferencia
  por red dispara además la cláusula de red. Eso contamina todo el backend.
- `boxmot` —el `pip install` cómodo para ByteTrack y BoT-SORT, presente en casi todos los
  tutoriales— es **AGPL-3.0**, aunque los trackers originales sean MIT. Es la trampa más fácil de
  pisar de todo el proyecto.
- **DEIMv2 no es Apache-2.0**: su licencia prohíbe explícitamente el uso comercial y la
  redistribución. Los agregadores lo reportan mal. DEIM **v1** sí es Apache-2.0.
- RF-DETR documenta **8 GB de VRAM** para *fine-tuning* con `batch_size=4` y
  `grad_accum_steps=4`: encaja exactamente en la única máquina con GPU del equipo. Es NMS-free y
  exporta a ONNX sin *plugins*.

## Cuidados

Solo las variantes **N, S, M y L** son Apache-2.0. Las **XL y 2XL** (extra `rfdetr[plus]`) tienen
licencia propietaria. Instalar el extra equivocado es un error trivial de cometer.

## Consecuencias

Menos tutoriales y más lectura de código fuente. A cambio: un modelo que se puede publicar, y una
respuesta sólida cuando en la defensa pregunten por qué no se usó YOLO. Se añade `LICENSES.md`
con la licencia verificada de cada dependencia de modelo y su fuente.
