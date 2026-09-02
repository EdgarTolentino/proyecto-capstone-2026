# Guardián EPP — Especificación de arquitectura v1

| | |
|---|---|
| **Versión** | 1.0 |
| **Fecha** | 2 de septiembre de 2026 |
| **Autor** | Edgar Tolentino — arquitectura, visión y backend |
| **Estado** | Propuesta para revisión del equipo |
| **Reemplaza a** | — |

---

## 1. Resumen ejecutivo

Guardián EPP procesa video de faena y produce **hallazgos**: afirmaciones del tipo *"en el área de
chancado, entre las 02:10:14 y las 02:10:52, una persona estuvo sin casco"*, con evidencia
recortada, severidad y un responsable que debe actuar.

La arquitectura se sostiene sobre cinco decisiones, y todas las demás se derivan de ellas:

| # | Decisión | Por qué importa |
|---|---|---|
| 1 | **El evento, no el cuadro, es la unidad del sistema** | Sin esto, un turno genera 200.000 filas y 200.000 alertas. Con esto, genera 12 hallazgos. |
| 2 | **La fuente de video está detrás de un puerto** (`FrameSource`) | v1 lee archivos, v2 lee RTSP. El resto del sistema no se entera. |
| 3 | **El reloj viene de la captura, nunca del procesamiento** | Un video de la semana pasada debe fechar sus eventos la semana pasada. Es irreparable si se hace mal. |
| 4 | **Las reglas viven en la base de datos, versionadas** | Cambiar "en el taller se exige lente de seguridad" no puede requerir un despliegue. |
| 5 | **El sistema no identifica personas** | Es a la vez requisito legal, condición de aceptación sindical y simplificación técnica. |

## 2. Contexto y restricciones

### Restricciones duras

| Restricción | Consecuencia arquitectónica |
|---|---|
| Una sola máquina con GPU (8 GB VRAM); las otras dos sin GPU | El paquete de API no puede depender de PyTorch. Dos perfiles de instalación desde el mismo *lockfile*. |
| Windows + WSL2 | Los videos viven en el filesystem ext4. `inotify` **no funciona** sobre `/mnt/c` (falla en silencio: la llamada tiene éxito y no llega ningún evento). |
| Edgar hace visión y backend; dos compañeros hacen frontend | El contrato de API se congela antes de que exista el modelo, y hay un servidor simulado desde la S5. |
| 18 semanas, 3 personas | El alcance de v1 son **dos clases de EPP** (casco y chaleco). Las otras son extensión demostrada, no requisito. |
| Repositorio público | Ni una imagen de trabajador real, ni un dato personal, entra al repositorio. |

### Restricción legal que condiciona el diseño

El sistema opera bajo la Ley 19.628 reformada por la **Ley 21.719** (vigencia prevista el
**1-dic-2026**, dentro de la vida del proyecto) y bajo la doctrina de la Dirección del Trabajo
sobre videovigilancia laboral, que exige control **general e impersonal**.

Traducción a arquitectura, no a un párrafo de relleno:

- **Prohibido por diseño**: reconocimiento facial, re-identificación entre cámaras o entre días,
  inferencia de género, edad, etnia o emoción.
- Los `track_id` son **efímeros**: viven dentro de un video y se destruyen al cerrarlo. Nunca se
  cruzan entre fuentes ni se persisten como identidad.
- El recorte de evidencia se escribe **con el rostro ya difuminado**. El cuadro original nunca
  toca el disco.
- La tabla de reglas lleva columnas de gobernanza (`base_licitud`, `norma_fundante`,
  `retencion_dias`), de modo que la trazabilidad jurídica se audita con un `SELECT`.

El detalle está en [`docs/producto/02-privacidad-y-cumplimiento.md`](../producto/02-privacidad-y-cumplimiento.md).

## 3. Vista general

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FUENTE                                                                     │
│                                                                             │
│   v1 ─ carpeta vigilada ──┐                                                 │
│                           ├──▶  FrameSource  ──▶  Frame(capture_ts, imagen) │
│   v2 ─ cámara RTSP  ──────┘      (puerto)          ▲                        │
│                                                    │ el reloj nace aquí     │
└────────────────────────────────────────────────────┼────────────────────────┘
                                                     │
┌────────────────────────────────────────────────────┼────────────────────────┐
│  ETAPA 1 — barata, siempre encendida               │                        │
│                                                    ▼                        │
│   muestreo a 5 fps  ─▶  máscaras de privacidad  ─▶  DETECTOR  ─▶  TRACKER   │
│                          (polígonos, antes            RF-DETR      ByteTrack│
│                           de inferir)                                       │
│                                          │                                  │
│                                          ▼                                  │
│                                    detecciones crudas ──────────┐           │
│                                    (persistidas por track)      │           │
│                                          │                      │           │
│                                          ▼                      │           │
│                                  MOTOR DE REGLAS  ◀── reglas (BD, versionadas)
│                                   ¿incumple? ¿por cuántos segundos?         │
│                                          │                                  │
│                                          ▼                                  │
│                                     HALLAZGO  (inicio, fin, severidad)      │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
     ┌─────────────────┐        ┌────────────────────┐       ┌──────────────────┐
     │ EVIDENCIA       │        │ NOTIFICACIÓN       │       │ ETAPA 2 — cara,  │
     │ recorte con     │        │ outbox → canal     │       │ selectiva        │
     │ rostro          │        │ cooldown,          │       │ VLM describe     │
     │ difuminado      │        │ escalamiento,      │       │ (NO decide)      │
     └─────────────────┘        │ acuse de recibo    │       └──────────────────┘
                                └────────────────────┘                │
                                                                      ▼
                                                            update del hallazgo
```

**La regla que ordena el dibujo:** la Etapa 1 decide, la Etapa 2 describe. El modelo de lenguaje
visual nunca crea, suprime ni cambia la severidad de un hallazgo. Si lo hiciera, el sistema
dejaría de ser auditable — y un cliente minero exige poder explicar por qué se disparó cada
alerta.

## 4. Componentes

### 4.1 `gepp-core` — el dominio

Python puro. **Sin `torch`, sin `cv2`, sin framework web.** Contiene las entidades (`Hallazgo`,
`Regla`, `Severidad`, `Area`, `Deteccion`), el motor de reglas y el agregador de eventos.

Que este paquete no dependa de nada pesado es lo que permite que la lógica de negocio —el
corazón evaluable del proyecto— se pruebe en CI en segundos, sin GPU y sin video.

### 4.2 `gepp-vision` — la visión

| Pieza | Elección | Licencia | Por qué |
|---|---|---|---|
| Detector | **RF-DETR-N** → **RF-DETR-S** | Apache-2.0 | Permisiva de verdad; documenta 8 GB VRAM para *fine-tuning*; sin NMS; exporta a ONNX limpio |
| Seguidor | **ByteTrack** vía `roboflow/trackers` | Apache-2.0 | El paquete cómodo (`boxmot`) es AGPL-3.0 |
| VLM | **Qwen3-VL-4B** local, respaldo por API | Apache-2.0 | Solo describe hallazgos ya confirmados |
| Runtime | PyTorch → ONNX Runtime (~S10) | — | ONNX es lo que permite a los compañeros correr el pipeline sin GPU |

> **Ultralytics YOLO queda descartado y la razón hay que saber decirla en la defensa:** es
> AGPL-3.0 y su licenciante sostiene que la licencia alcanza también **a los pesos que uno
> mismo entrena**. Eso contaminaría todo el backend. Un CI que falle si aparece `ultralytics`,
> `boxmot` o `deimv2` en el *lockfile* cuesta media hora y evita reescribir el proyecto en la S15.

### 4.3 `gepp-api` — la API

FastAPI + SQLAlchemy sobre PostgreSQL. **Regla dura: `gepp-api` no importa `gepp-vision`.** Se
comunican por la base de datos y la cola. Eso es lo que permite levantar la API completa en un
portátil sin GPU y sin descargar 3 GB de CUDA.

### 4.4 `gepp-worker` — la ingesta

Vigila la carpeta (v1) o consume RTSP (v2). Es el **único** paquete que cambia entre v1 y v2.

### 4.5 `apps/web` — la interfaz

React + Vite, construida por el equipo de frontend contra el contrato OpenAPI y un servidor
simulado. Ver [`docs/producto/05-diseno-interfaz.md`](../producto/05-diseno-interfaz.md).

## 5. Las decisiones difíciles, explicadas

### 5.1 El muestreo es de 5 fps, y no es negociable a la baja

La tentación es bajar a 2 fps "para ahorrar cómputo". La aritmética lo desmiente: una persona
caminando a 1,4 m/s recorre **0,70 m** entre cuadros a 2 fps, y una caja de persona mide unos
0,5–0,6 m de ancho. A 2 fps las cajas de cuadros consecutivos **no se solapan**, el seguidor
pierde la identidad y un mismo trabajador mal equipado genera tres hallazgos en vez de uno.

No se paga en fotogramas por segundo: se paga en cambios de identidad, que es exactamente lo que
rompe el pilar 1 de esta arquitectura. Si hay que abaratar, se baja la resolución, no la cadencia.

### 5.2 Todos los umbrales se guardan en segundos

`confirmacion_segundos`, `cierre_segundos`, `track_buffer_segundos`. El código deriva los cuadros
en tiempo de ejecución: `n_cuadros = ceil(segundos × fps_objetivo)`.

Guardarlos en cuadros funciona perfecto en v1 y rompe v2 **en silencio**: al cambiar la cadencia,
todas las reglas ya validadas con el cliente cambian de significado y ningún test falla.

### 5.3 Se persisten las detecciones crudas, no solo los hallazgos

Son filas, no video: el costo de almacenamiento es despreciable. Lo que compra es enorme:

- **Recalcular reglas sin volver a inferir.** Con una sola GPU en el equipo, reprocesar todo el
  corpus cada vez que se ajusta un umbral es la ruta crítica que mata el cronograma en la S14.
- **Simulador "¿y si...?"**: *"esta regla nueva habría generado 47 hallazgos el mes pasado"*.
  Es la función que convierte el editor de reglas en producto.
- **Auditoría**: poder explicar por qué se generó un hallazgo, cuadro por cuadro.

### 5.4 El seguidor a 5 fps necesita otros umbrales

Los valores por defecto de ByteTrack están calibrados para 30 fps. Copiarlos es un error
silencioso. Tres ajustes, y los tres van a la base de datos junto con las reglas:

1. Umbral de IoU de emparejamiento: bajar de ~0,30 a **0,15–0,20**.
2. `track_buffer` expresado en **segundos**, no en cuadros (30 cuadros a 5 fps son 6 s reales).
3. Compensación de movimiento de cámara **desactivada**: el CCTV de faena es fijo y solo gasta CPU.

### 5.5 No se alerta por cada hallazgo

Esta es la decisión de producto que separa el proyecto de un demo de detección de objetos.
La industria, con cientos de cámaras, produce miles de alertas por turno con menos del 3 %
accionables. A escala de 4–8 cámaras el problema aparece igual.

| Tipo de condición | Cómo se notifica |
|---|---|
| Peligro inminente (persona en zona restringida, línea de fuego) | Alerta inmediata, con validación humana antes de escalar |
| Incumplimiento de EPP corriente | **No** genera alerta individual: se agrega en un resumen por turno |
| Incumplimiento de EPP grave | Alerta inmediata solo si supera duración (p. ej. >120 s en área crítica) o se repite N veces en el turno |

Si en la demostración el prevencionista recibe 200 correos, el proyecto está muerto aunque el
modelo sea perfecto.

### 5.6 Sobre la desagregación por género que pidió el cliente

**No se infiere desde la imagen.** Y conviene poder defender la negativa en tres frentes:

- **Legal**: "identidad de género" es dato sensible taxativo en la ley chilena. Además, el
  cliente ya está obligado a mantener registros desagregados por sexo desde recursos humanos
  (DS 44, art. 74): la inferencia no es *necesaria*, y sin necesidad no hay proporcionalidad.
- **Técnico**: con casco, antiparras y buff, las señales faciales que usan esos clasificadores
  están tapadas. El modelo terminaría discriminando por estatura y complexión. Y con ~14,9 % de
  dotación femenina en faena, un clasificador del 95 % de exactitud produce en la clase
  minoritaria casi tantos falsos positivos como aciertos: el ranking resultante sería
  estadísticamente indefendible y sesgado contra las trabajadoras.
- **Ético**: la literatura sobre clasificación automática de género por imagen es concluyente
  desde *Gender Shades* (34,7 % de error en mujeres de piel oscura frente a 0,8 % en hombres de
  piel clara).

**La alternativa que sí entrega lo que el cliente quiere:** cruzar los hallazgos **agregados** por
área, turno y franja horaria contra la **dotación** que recursos humanos ya mantiene. El reporte
queda como *"turno B del área de chancado, dotación de 18 hombres y 4 mujeres, N eventos de casco
faltante"*. Con supresión de celdas con **n < 5** para que ninguna trabajadora sea reidentificable.

Y hay un caso de uso legítimo que además aporta valor real: si el EPP mal ajustado o de talla
incorrecta explica parte del incumplimiento, ese hallazgo sí es accionable — y conecta con la
obligación del cliente de adecuar el EPP a diferencias biológicas.

> Esto no es una limitación del proyecto: **es una decisión de diseño que hay que presentar como
> tal en la defensa.** Ninguno de los proyectos que compiten va a tener este análisis.

## 6. Lo que hay que decidir hoy para no reescribir en v2

Doce decisiones, todas baratas ahora y caras después.

| # | Decisión | Costo hoy | Costo si se omite |
|---|---|---|---|
| 1 | Puerto `FrameSource` con 5 métodos | 1 día | Reescribir el ingestor completo |
| 2 | `capture_ts` en UTC, derivado de la fuente | 0 | **Toda la analítica temporal queda inservible** |
| 3 | Política de *backpressure* inyectable | 0,5 día | Memoria o latencia creciendo sin techo |
| 4 | Cola de inferencia única compartida | 0,5 día | Rediseñar el detector para multi-cámara |
| 5 | Muestreo contra `fps_objetivo` configurable | 0 | Cadencia incrustada en el código |
| 6 | Umbrales en segundos | 0 | Reglas que cambian de significado en silencio |
| 7 | Ciclo de vida del evento `new`/`update`/`end` | 0,5 día | Reescribir el frontend entero |
| 8 | VLM como consumidor asíncrono | 0,5 día | El detector se queda sin VRAM justo al detectar |
| 9 | Vigilante de fuente (sin cuadros en N s → reabrir) | 0,5 día | Reconexión RTSP frágil en v2 |
| 10 | Cinco métricas por fuente en `/metrics` | 0,5 día | Sin evidencia de rendimiento para el informe |
| 11 | Hash del archivo como clave de idempotencia | 0 | Eventos duplicados al reprocesar |
| 12 | Capa de re-*streaming* delante de la fuente | 0,5 día | Las cámaras IP limitan conexiones concurrentes |

**El atajo que cambia el calendario:** con **MediaMTX** (MIT) se publica un `.mp4` grabado como si
fuera una cámara RTSP en una línea:

```bash
ffmpeg -re -stream_loop -1 -i faena_01.mp4 -c copy -f rtsp rtsp://127.0.0.1:8554/camara_01
```

Con eso la ruta de v2 se prueba **en la semana 6**, con los mismos videos del dataset, sin
cámaras, sin faena y sin permisos. Y da una frase verificable para el informe: *"la arquitectura
en vivo fue validada con fuentes RTSP antes del cierre de la v1"*.

## 6.bis El dataset: cascada de preentrenamiento

No hay ningún dataset público de EPP en minería a rajo abierto. Todo lo abierto es construcción
occidental o china, diurno y recolectado de la web. La estrategia es una **cascada**, de lo
genérico a lo propio:

```
pesos genéricos  →  CCTV industrial real  →  densidad de casco/chaleco  →  faena propia
   (COCO)            enseña la física          más instancias              lo que importa
                     correcta: cámara fija,
                     escala pequeña, poca luz
```

**Advertencia contra un error que dos fuentes recomiendan y una desmiente con datos:** el dataset
de 17 clases más citado tiene *menos de mil* instancias de casco y *menos de seiscientas* de
chaleco entre casi 76.000 anotaciones. Sirve para **partes del cuerpo** (manos, cabezas,
personas), no para EPP. El dataset que sí importa es el de CCTV industrial real, y es el que
ninguna de esas dos fuentes menciona.

**La cifra que calibra expectativas:** el mismo detector obtiene ~91 % de mAP50 sobre fotos web y
~79 % sobre CCTV industrial real. Un mAP alto en un dataset público **no predice nada** sobre el
rendimiento en la faena.

**Presupuesto realista:** 2.000-3.000 imágenes propias —contadas en **instancias**, no en
imágenes: ≥800 por clase crítica— en tres rondas de esfuerzo decreciente:

| Ronda | Imágenes | Método |
|---|---|---|
| 0 | 300-500 | Manuales, con la guía de etiquetado ya escrita |
| 1 | 800-1.000 | Preetiquetadas con el modelo de la ronda 0, solo corregidas |
| 2 | 800-1.500 | Seleccionadas por criterio activo |

El criterio de selección activa sale gratis de la arquitectura: **donde el seguidor pierde o
cambia la identidad, hay un cuadro difícil**. El tracker de la Etapa 1 es, sin costo, el detector
de casos que vale la pena etiquetar.

**Herramienta: CVAT autoalojado.** Los planes gratuitos de las plataformas comerciales publican
el dataset en su catálogo público — inaceptable con CCTV de trabajadores.

## 7. Riesgos técnicos y su mitigación

| Riesgo | Señal temprana | Mitigación |
|---|---|---|
| Los cascos son objetos pequeños en CCTV | En los benchmarks públicos, más de la mitad de los cascos caen en la categoría "pequeño" | Entrenar a mayor resolución con modelo chico, en vez de modelo grande a 640 px |
| El mAP de un dataset público no predice el de la faena | El mismo detector cae de 91,5 % a 78,9 % al pasar de fotos web a CCTV real | Validar solo contra video propio; nunca prometer >90 % |
| Fuga de datos al separar entrenamiento y prueba | mAP de validación sospechosamente alto | Separar **por grabación, cámara y turno**, jamás por cuadro |
| Cuadros casi idénticos inflando el dataset | 2.000 imágenes que son 3 minutos de turno | Deduplicar por similitud antes de etiquetar |
| Confundir severidad con confianza | "Sin arnés en altura" con 0,62 tratado como leve | Son dos columnas distintas y no se mezclan nunca |
| Etiquetado inconsistente entre tres anotadores | Desacuerdo alto en la auditoría cruzada | Guía de etiquetado escrita **antes** de abrir la herramienta; auditar el 10 % de cada lote |
| Archivos leídos mientras se copian | Fallos intermitentes irreproducibles | Renombrado atómico `.part` → `.mp4` o comprobación de estabilidad de tamaño |
| `inotify` sobre `/mnt/c` | El vigilante "funciona" y nunca dispara | El sistema **rechaza** rutas bajo `/mnt/` y lo registra |

## 8. Qué queda fuera de la v1

Escrito para que nadie lo confunda con un olvido: reconocimiento facial y re-identificación
(prohibidos por diseño, no pendientes) · ingesta RTSP en vivo (diseñada y probada, no puesta en
producción) · detección de arnés, guantes y lentes (el modelo se entrena con ellas si el dataset
alcanza; el compromiso de v1 es casco y chaleco) · integración con el sistema EHS del cliente
(existe el webhook; no hay integración real) · aplicación móvil.
