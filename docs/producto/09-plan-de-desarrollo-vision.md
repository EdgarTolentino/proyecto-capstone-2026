# Plan de acción y estructura de desarrollo — visión, ingesta, API y datos

> El plan de trabajo del equipo ([`03-plan-de-trabajo.md`](03-plan-de-trabajo.md)) reparte las 18
> semanas y la verificación V9 ([`08-verificacion-v9-horas.md`](08-verificacion-v9-horas.md)) fija
> cuántas horas caben. Este documento baja el lado de Edgar —visión, ingesta, API y datos— a
> **paquetes de trabajo** con módulos, orden, horas, definición de terminado e issue. Es el
> equivalente, para el backend, del issue #11 que guía al frontend.

| | |
|---|---|
| **Versión** | 1.0 |
| **Fecha** | 7 de septiembre de 2026 (S4) |
| **Autor** | Edgar Tolentino |
| **Estado** | Propuesta — se aprueba al fusionar el PR que la introduce |
| **Horas** | Respeta las 184 h base y 221 h con holgura de V9; solo las reparte en paquetes |

## 1. Punto de partida

Lo que hay en `main` al cierre de la S4 y lo que falta para que exista un sistema.

| Paquete | Existe | Falta |
|---|---|---|
| `gepp-core` | Dominio completo: entidades, geometría, asociación EPP-persona, agregador de hallazgos. Pruebas en CI, tipado estricto y test sobre el AST que prohíbe `datetime.now()` | Nada para la v1. Se toca solo si el experimento V6 exige cambiar la asociación |
| `gepp-vision` | Los puertos `Detector`, `Seguidor` y `Descriptor` | Todo lo demás: adaptadores reales, privacidad, pipeline, evaluación |
| `gepp-worker` | El puerto `FuenteDeCuadros`, `Cuadro`, `PropiedadesFuente` y la derivación del reloj | La fuente de archivo, el muestreo, el vigilante, la cola y el trabajador |
| `gepp-api` | Un `__init__.py` | La API entera y, antes de ella, la persistencia |
| Persistencia | El modelo de datos diseñado (`01-modelo-de-datos.md`); PostgreSQL y Redis en `docker/compose.yml` | El esquema implementado, las migraciones y **quién es dueño de ellas** ([ADR-012](../arquitectura/adr/012-persistencia-compartida.md)) |
| Contrato | `contracts/openapi.yaml` con 18 operaciones y ejemplos, servido por Prism | El servidor real que lo cumple |
| Datos | Manifiesto de procedencia, inventario técnico de video, medición parcial de V2 | Video propio (#10), matriz de EPP (#7), V2 con cámara real (#3), dataset etiquetado |
| Web | Bandeja y visor fusionados (#17), contra Prism | Que apunten al backend real en la S9 |

## 2. Estructura de desarrollo

### 2.1 Los módulos, paquete por paquete

Cada archivo tiene una responsabilidad y el paquete de trabajo (PT) que lo construye. Los marcados
con ✔ ya existen.

```
packages/gepp-worker/src/gepp_worker/       ingesta: lo único que cambia entre v1 y v2
  fuente.py            ✔      puerto FuenteDeCuadros, Cuadro, PropiedadesFuente, instante_de_captura
  fuente_archivo.py    PT-05  FuenteArchivo sobre OpenCV: abre el .mp4, deriva inicio_captura de los
                              metadatos (ffprobe) o de mtime - duracion, y registra origen_reloj
  muestreo.py          PT-05  Muestreador: de los fps de la fuente a fps_objetivo (5); decide qué
                              indices pasan sin decodificar los demás
  vigilante.py         PT-06  carpeta vigilada por sondeo (inotify falla bajo /mnt/: la ruta se
                              rechaza), estabilidad de tamaño, hash SHA-256 como clave de idempotencia
  cola.py              PT-06  cola de trabajos en Redis: encolar, estado por video, reintentos
  trabajador.py        PT-06  consume la cola: fuente -> muestreo -> pipeline -> persistencia -> outbox
  __main__.py          PT-06  `python -m gepp_worker`: vigilante y trabajador en procesos separados
  fuente_rtsp.py       v2     FuenteRtsp: reloj de recepción y reconexión. Diseñada, no en la v1

packages/gepp-vision/src/gepp_vision/       visión: detectar, seguir, evaluar
  puertos.py           ✔      Detector, Seguidor, Descriptor
  privacidad.py        PT-05  máscaras por fuente (polígonos) aplicadas ANTES de inferir; difuminado
                              de rostros para la evidencia
  detectores/falso.py  PT-07  detector guionizado: devuelve las detecciones de un JSON. Es el que
                              corre en CI y en los portátiles sin modelo
  detectores/rfdetr.py PT-07  adaptador PyTorch de RF-DETR (máquina con GPU; entrenamiento y evaluación)
  detectores/onnx.py   PT-07  adaptador ONNX Runtime (CPU): los compañeros corren el pipeline sin GPU
  seguimiento/bytetrack.py PT-07 adaptador de roboflow/trackers con los umbrales de 5 fps: IoU
                              0,15-0,20, track_buffer en segundos, sin compensación de cámara
  pipeline.py          PT-07  Etapa 1 completa: cuadro -> detecciones con track_id -> asociación y
                              agregador de gepp-core -> hallazgos. Sin E/S: recibe cuadros, devuelve objetos
  evidencia.py         PT-06  recorte del hallazgo, difuminado y escritura; el cuadro original nunca
                              toca el disco
  evaluacion/          PT-08  la jerarquía de 02-plan-de-evaluacion.md: cuadro (mAP), seguimiento
                              (HOTA, IDF1), evento (F1 a tIoU, falsas alarmas por hora), alerta
  descripcion/qwen_vl.py PT-16 Etapa 2, extensión: implementa Descriptor; nunca decide

packages/gepp-bd/src/gepp_bd/               persistencia compartida (ADR-012)
  modelos.py           PT-01  SQLAlchemy: las tablas de 01-modelo-de-datos.md
  sesion.py            PT-01  motor y sesión desde GEPP_BD_URL
  migraciones/         PT-01  Alembic: entorno y versiones. `make migrar` las aplica
  repositorios/        PT-01  detecciones (inserción por lotes), videos, hallazgos, reglas versionadas,
                              notificaciones (outbox), auditoría append-only

packages/gepp-api/src/gepp_api/             la API: cumple el contrato y no importa la visión
  app.py               PT-09  FastAPI, autenticación Bearer, routers, /metrics (cinco métricas por fuente)
  routers/             PT-09  hallazgos, evidencias, videos, panel, reglas, reportes, catalogos, estado, yo
  servicios/recalculo.py PT-12 reglas sobre detecciones crudas sin GPU, con el agregador de gepp-core
  servicios/simulador.py PT-12 "¿y si...?": POST /reglas/{id}/simular
  servicios/analitica.py PT-15 agregados por EPP, zona y turno; cruce con dotación; supresión n < 5
  notificaciones/      PT-13  despachador del outbox; puerto CanalNotificacion; un canal en la v1

scripts/
  inventario_video.py  ✔
  entrenar.py          PT-08  afinado de RF-DETR: nube con datasets públicos, local con el propio (ADR-010)
  exportar_onnx.py     PT-08  exporta el modelo y verifica que ONNX y PyTorch coinciden
  evaluar.py           PT-08  corre la jerarquía de métricas sobre el conjunto de prueba y escribe JSON
  exportar_openapi.py  PT-09  lo invoca `make contrato` y todavía no existe
```

### 2.2 Cómo se comunican los procesos

```
  /datos/videos/entrada   (v1: la obra deja .mp4  ·  v2: cámara RTSP, MediaMTX la simula)
          |
   [vigilante] --hash, tamaño estable--> [cola Redis] --> [trabajador]
                                                            |  fuente -> muestreo 5 fps -> máscaras
                                                            |  -> detector -> seguidor        (gepp-vision)
                                                            |  -> asociación -> agregador      (gepp-core)
                                                            v
        +-------------------------- PostgreSQL (gepp-bd) ---------------------------+
        |  video · deteccion (cruda, por track) · hallazgo · evidencia · regla ·      |
        |  notificacion (outbox) · accion_correctiva · auditoria                      |
        +-----------------------------------------------------------------------------+
               ^                                        |
        [gepp-api]  <---- apps/web (React)        [despachador del outbox] --> Telegram o correo --> acuse
        recálculo · simulador · analítica
```

Tres reglas que el dibujo hace cumplir:

- **El trabajador escribe; la API lee y decide sobre reglas.** Ambos usan `gepp-bd`; ninguno
  importa al otro. `gepp-api` sigue sin importar `gepp-vision` (ADR-007).
- **El reloj entra una sola vez**, en `FuenteArchivo`. Todo lo demás recibe `capture_ts` (ADR-005).
- **La evidencia se escribe ya difuminada** y la fila `deteccion` guarda cajas, no imágenes (ADR-006).

### 2.3 Cómo se prueba cada pieza sin GPU y sin video real

| Pieza | Doble o dato de prueba | Anillo (`02-plan-de-evaluacion.md`) |
|---|---|---|
| Fuente, muestreo, privacidad | Video sintético generado con NumPy y escrito con OpenCV en `tmp_path`: cuadros de colores con un rectángulo que se mueve. Sin personas | 1 · cada empuje |
| Vigilante y cola | Carpeta temporal y Redis como servicio de CI (`fakeredis` en local si no hay Docker) | 1 |
| Pipeline y reglas | `detectores/falso.py` con detecciones guionizadas en JSON, lo mismo que ya usa el agregador | 1 |
| Persistencia y API | PostgreSQL como servicio de GitHub Actions; pruebas de contrato con `httpx` contra la app real y comparación con `openapi.yaml` | 1 |
| Modelo | 2-3 clips de referencia de 10-30 s con el modelo nano en ONNX sobre CPU; el JSON de eventos se compara con el esperado | 2 · cada PR |
| Evaluación completa | Conjunto de prueba (video propio) con GPU, en local | 3 · nocturno |

Dónde viven los clips de referencia es una decisión pendiente para la S6: el repositorio es
público y no pueden contener trabajadores reales. Opciones: material con licencia permisiva del
manifiesto, o video sintético.

## 3. Paquetes de trabajo

Horas base de V9 repartidas sin cambiar el total. La columna "V9" dice de qué línea de la suma
sale cada paquete.

| PT | Semana | Qué | Módulos | Horas | V9 | Issue |
|---|---|---|---|---|---|---|
| PT-01 | S5 | Persistencia: `gepp-bd`, esquema, migraciones, semilla del perfil de construcción | `gepp-bd/*` | 10 | S5 BD | #25 |
| PT-02 | S5 | Grabación de 20-30 min con autorización y consentimientos; V2 con cámara real; matriz de EPP | — | 6 | S5 grabación | #10 · #3 · #7 |
| PT-03 | S6 | Dataset v0.1: públicos descargados y registrados, clases, guía de etiquetado, CVAT, lote 0 | `07-datasets.md`, `docs/datos/guia-etiquetado.md` | 6 | S6 clases | #26 |
| PT-04 | S6-S8 | Etiquetado en tres rondas, en sesiones de los tres; Edgar: un tercio y la auditoría del 10 % | CVAT | 10 | Etiquetado | #27 |
| PT-05 | S6-S7 | Fuente de archivo, muestreo a 5 fps y privacidad | `fuente_archivo`, `muestreo`, `privacidad` | 6 | Ingesta | #28 |
| PT-06 | S7 | Ingesta: vigilante, cola, trabajador, persistencia cruda, evidencia | `vigilante`, `cola`, `trabajador`, `evidencia` | 8 | Ingesta | #29 |
| PT-07 | S7 | Adaptadores de visión y pipeline de la Etapa 1 | `detectores/*`, `seguimiento/*`, `pipeline` | 6 | Ingesta e integración | #30 |
| PT-08 | S8 | Primer modelo y arnés de evaluación; experimento V6 | `scripts/entrenar`, `exportar_onnx`, `evaluar`, `evaluacion/` | 15 | S8 afinado | #31 |
| PT-09 | S9 | API real: 18 operaciones contra la base de datos; Prism se retira | `gepp-api/app`, `routers/` | 10 | Integración | #32 |
| PT-10 | S9 | **H2** · Integración extremo a extremo y demostración | Todo | 6 | Integración | #33 |
| PT-11 | S10 | **H3** · Evaluación de avance: demo, métrica base e informe (parte de Edgar) | — | 8 | S10 | #34 |
| PT-12 | S11 | Motor de reglas en la base: versionado, recálculo sin GPU, simulador | `servicios/recalculo`, `simulador`, `routers/reglas` | 12 | S11 reglas | #35 |
| PT-13 | S12 | Alertas v1: outbox, un canal, acuse, supresión, presupuesto de 6 avisos por turno | `notificaciones/*` | 10 | S12 alertas | #36 |
| PT-14 | S12 | Segunda ronda del modelo: aprendizaje activo sobre los fallos del primero | `scripts/*`, dataset v0.2 | 6 | S12 modelo v2 | #37 |
| PT-15 | S13 | Analítica: endpoints agregados y supresión n < 5, con Lian | `servicios/analitica`, `routers/reportes` y `panel` | 4 | S13 analítica | #38 |
| PT-16 | S13 | Extensión no comprometida: Etapa 2 con Qwen3-VL | `descripcion/qwen_vl` | 0 | Fuera (palanca 3) | #39 |
| PT-17 | S14 | Endurecimiento: plan de pruebas ejecutado, rendimiento, manual técnico, respaldos | `docs/operacion/*` | 16 | S14 | #40 |
| PT-18 | S15 | **H4** · Congelar v1.0.0: etiqueta, evidencias de Fase 2, informe final | `Fase 2/Evidencias Proyecto/*` | 12 | S15 | #41 |
| — | S5-S15 | Transversal: reunión semanal, revisión de los PR del frontend, issues | — | 33 | 3 h/sem | — |
| | | **Total** | | **184** | **184** | |

## 4. Calendario semanal

Carga base de Edgar por semana. Fechas derivadas de **S4 = semana del 7 de septiembre de 2026**
(exposición el martes 8); si el calendario académico tiene receso, se corren todas.

| Sem | Fechas | Paquetes | Horas | Nota |
|---|---|---|---|---|
| S5 | 14-18 sep | PT-01, PT-02 | 16 | Fiestas Patrias (18 y 19): semana de cuatro días. La grabación se agenda de lunes a miércoles |
| S6 | 21-25 sep | PT-03, PT-04, PT-05 | 12 | Primera sesión de etiquetado del equipo. MediaMTX publica un .mp4 como RTSP (ADR-009) |
| S7 | 28 sep - 2 oct | PT-04, PT-05, PT-06, PT-07 | 20 | El video entra al sistema con el detector falso |
| S8 | 5-9 oct | PT-04, PT-08 | 19 | Pico de GPU: preentrenar en la nube (públicos) y afinar en local (propio) en ventanas separadas |
| S9 | 12-16 oct | PT-09, PT-10 | 16 | **H2**. Lunes 12 feriado. La web cambia de Prism al backend real |
| S10 | 19-23 oct | PT-11 | 8 | **H3** · Evaluación de avance · etiqueta `v0.1.0-avance` |
| S11 | 26-30 oct | PT-12 | 12 | Reglas sin desplegar código; Miguel construye la pantalla |
| S12 | 2-6 nov | PT-13, PT-14 | 16 | Una alerta llega a un teléfono real |
| S13 | 9-13 nov | PT-15 (PT-16 solo con holgura) | 4 | Lian construye el tablero sobre los endpoints |
| S14 | 16-20 nov | PT-17 | 16 | Plan de pruebas ejecutado con el video de referencia |
| S15 | 23-27 nov | PT-18 | 12 | **H4** · `v1.0.0` · informe final |
| S5-S15 | | Transversal | 33 | 3 h por semana |
| | | **Total** | **184** | 221 con holgura del 20 %. Realista: 12-15 h por semana (V9, §4) |

## 5. Terminado significa

La definición de terminado del equipo (CI, pruebas, documentación, otro lo ejecutó) aplica a
todos. Lo específico de cada paquete:

**PT-01 · Persistencia.** `make up && make migrar` crea el esquema completo desde cero y
`alembic downgrade base` lo deshace. Las tablas coinciden con `01-modelo-de-datos.md`: columnas
de gobernanza en `regla`, `auditoria` sin UPDATE ni DELETE, `deteccion` con índice por video y
track. La semilla `perfiles/construccion.yaml` carga la matriz de #7 y la tabla de V2 (#3).
`esquema.sql` y el diagrama ER van a `Evidencias de sistema/Base de datos/`. Pruebas de
integración en CI con PostgreSQL de servicio. ADR-012 aceptado.

**PT-03 · Dataset v0.1.** Públicos descargados y registrados en `07-datasets.md` con licencia
permisiva verificada (se rechaza `-NC`, `-ND` y lo que no declare licencia). La guía de
etiquetado se escribe **antes** de abrir CVAT: clases, casos límite, qué cuenta como "casco
puesto". CVAT autoalojado en la máquina de Edgar. Lote 0 de 300-500 imágenes deduplicadas por
similitud. Partición por grabación, cámara y turno, nunca por cuadro.

**PT-04 · Etiquetado.** Tres rondas: manual, preetiquetada y corregida, selección activa. El 10 %
de cada lote se etiqueta doble y se audita, con kappa e IoU entre anotadores registrados. Al
cierre de la ronda 2, 800 o más instancias por clase crítica. Dataset y respaldo fuera del
repositorio, con copia semanal en disco externo (ADR-010).

**PT-05 · Fuente, muestreo y privacidad.** `FuenteArchivo` implementa los cinco métodos del puerto
y rechaza rutas bajo `/mnt/`. `inicio_captura` sale de los metadatos y `origen_reloj` queda
registrado. El muestreador entrega 5 fps desde cualquier cadencia de origen, con prueba de
invariancia. Las máscaras se aplican antes de inferir. El test del AST del reloj sigue pasando con
los módulos nuevos incluidos.

**PT-06 · Ingesta.** Un `.mp4` copiado a la carpeta vigilada termina como filas en `video`,
`deteccion` y `hallazgo` usando el detector falso. El mismo archivo dos veces no duplica nada
(hash). Un archivo a medio copiar no se lee (`.part` o tamaño estable). La evidencia se escribe
difuminada. `python -m gepp_worker` corre vigilante y trabajador en procesos separados. Reintentos
y estado por video visibles en `GET /videos`.

**PT-07 · Adaptadores y pipeline.** Los tres detectores cumplen el protocolo `Detector` y comparten
la misma batería de pruebas. ByteTrack corre con los umbrales de 5 fps y `track_buffer` en
segundos. `pipeline.py` no hace E/S y se prueba con JSON. `mypy --strict` en verde. Ninguna
dependencia AGPL en `uv.lock`: el trabajo de licencias de CI sigue en verde.

**PT-08 · Primer modelo.** RF-DETR-N preentrenado en la nube con públicos y afinado en local con el
propio. Exportado a ONNX con verificación de equivalencia. `scripts/evaluar.py` produce el JSON de
la jerarquía completa sobre el conjunto de prueba, que es video propio. Métrica base publicada en
el issue con la plantilla de modelo. Experimento V6 (100 cuadros) con resultado escrito y decisión
entre heurística y pose. Nunca se entrena y se sirve a la vez.

**PT-09 · API real.** Las 18 operaciones responden desde la base. `make contrato` exporta el
OpenAPI de la aplicación y falla si difiere del contrato. Pruebas de contrato con `httpx`.
`Authorization: Bearer` obligatorio. `/metrics` con las cinco métricas por fuente. La web de #17
funciona sin cambios apuntando al backend.

**PT-10 · H2.** Demostración grabada: un video entra, aparece un hallazgo en la bandeja con
evidencia y bloque "por qué se disparó". El recorrido corre en un portátil sin GPU con el modelo
ONNX, o con el detector falso si el modelo de la S8 no está. Etiqueta de la semana y bitácora con
lo que falló.

**PT-12 · Motor de reglas.** Cada cambio de regla es una fila nueva, nunca un UPDATE. Recálculo
desde detecciones crudas sin GPU. `POST /reglas/{id}/simular` responde "esta regla habría
generado N hallazgos" sobre el corpus. Umbrales en segundos con la prueba de invariancia a la
cadencia. El motor nunca exige en una zona un EPP que la tabla de V2 marca como no evaluable.

**PT-13 · Alertas.** La notificación se escribe en la misma transacción que el hallazgo (outbox).
Despachador con reintentos. Un canal real, Telegram o correo según `.env`, con acuse de recibo que
cierra el ciclo. Supresión por tiempo de espera global y por cámara. Presupuesto de 6 avisos por
turno de 12 h **medido** en la demostración. Tasa de alertas accionables calculada desde el triage.

**PT-14 · Segunda ronda.** Los cuadros donde el seguidor pierde identidad alimentan la selección
activa. Una ronda de corrección. Reevaluación con el mismo `evaluar.py` y el mismo conjunto de
prueba. Comparación publicada en el issue.

**PT-15 · Analítica.** `GET /panel` y `GET /reportes/{tipo}` con agregados por EPP, zona, turno y
tendencia. Cruce con `dotacion` con supresión de celdas n < 5. Las consultas las escribe quien
construye el tablero; Edgar revisa el plan de ejecución.

**PT-16 · Extensión.** Solo si en la S13 hay holgura: `Descriptor` con Qwen3-VL local, V4 medida
(VRAM y latencia), descripción como actualización del hallazgo sin tocar la severidad. Si no hay
holgura, queda como diseño en el informe.

**PT-17 · Endurecimiento.** Plan de pruebas de `docs/operacion/` ejecutado sobre el video de
referencia, con resultados. Rendimiento registrado: cuadros por segundo y latencia por fuente.
Manual técnico de instalación para el portátil sin GPU y la máquina con GPU. Respaldo y
restauración probados. Accesibilidad de la web revisada con Miguel y Lian.

**PT-18 · v1.0.0.** Etiqueta `v1.0.0`. `Evidencias de sistema/Base de datos/` con `esquema.sql`,
diagrama ER, `datos-ejemplo.sql` sintético y `respaldo.dump`. `Evidencias de documentacion/` con
las versiones congeladas en PDF. Licencia del repositorio decidida. Informe final.

## 6. Dependencias y ruta crítica

```
#10 grabación (S5) --> PT-03 lote 0 (S6) --> PT-04 rondas (S6-S8) --> PT-08 modelo (S8) --> PT-14 (S12)

PT-01 BD (S5) --> PT-06 ingesta (S7) --> PT-09 API (S9) --> PT-10 H2 (S9) --> PT-12 reglas (S11) --> PT-13 alertas (S12)
PT-05 fuente (S6-S7) --/                                 PT-07 adaptadores (S7) --/

#3 V2 + #7 matriz (S5) --> semilla del perfil (PT-01) --> reglas que respetan lo evaluable (PT-12)
```

- **La grabación es la ruta crítica.** Sin video propio no hay conjunto de prueba ni H2 con datos
  reales. El plan B está escrito en `03-plan-de-trabajo.md`: escenario simulado por el equipo con
  cámara fija.
- **H2 no espera al modelo.** La integración de la S9 se hace con el detector falso si el modelo
  de la S8 no está; lo que se prueba es que todo está conectado.
- **Nada del sistema depende del VLM** (ADR-001). PT-16 se puede caer sin tocar otro paquete.

## 7. Riesgos propios de este plan

| Riesgo | Señal | Respuesta |
|---|---|---|
| S7 y S8 concentran 39 h base | El lote 1 no está corregido al cerrar la S7 | PT-07 se adelanta a la S6 (los adaptadores no dependen del dataset); el tercio de etiquetado de Edgar se reparte con el equipo |
| Fiestas Patrias en la S5 | La grabación no está agendada al 16 de septiembre | Autorización pedida en la reunión del 8 de septiembre; se graba lunes o martes. Si se cae, corre a la S6 sin mover H2 |
| Una sola GPU y la S8 la necesita para entrenar y evaluar | Colas de más de un día | Preentrenar en Kaggle o Colab con públicos desde la S6, con checkpoints respaldados; afinar en local en ventanas nocturnas |
| Los clips de referencia del anillo 2 no pueden ir al repositorio público | El anillo 2 no corre en CI | Decisión en la S6: material permisivo o sintético, en una release privada |
| ADR-012 no se decide | PT-01 arranca sin dueño del esquema | Se decide al fusionar este PR; la alternativa B (trabajador cliente de la API) cuesta lo mismo en la S5 |

## 8. Lo que produce cada paquete para la Fase 2

Correspondencia con las evidencias que exige la rúbrica (Anexo A de la Guía 1.5).

| Evidencia | Paquetes | Indicador |
|---|---|---|
| Modelo de datos implementado, `esquema.sql`, diagrama ER | PT-01, PT-18 | 3.1, 3.2 |
| Pruebas de validación diseñadas y aplicadas | PT-05 a PT-09 (anillo 1), PT-08 (jerarquía), PT-17 (plan ejecutado) | 1.1, 1.2 |
| Mejoras a partir de resultados | PT-14; revisión del plan en la S6 | 1.3 |
| Solución construida e integrada | PT-06, PT-07, PT-09, PT-10 | 4.1, 4.2 |
| Solución implantada | PT-17 (manual técnico), PT-18 (`v1.0.0`) | 4.3 |
| Control del proyecto | Un issue por paquete, PR, reunión semanal, bitácora | 2.1, 2.2 |
