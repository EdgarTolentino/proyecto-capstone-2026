# Bitácora · 4 de septiembre de 2026 — Se cierra V1 y se fija el dominio

> Sesión corta con una decisión grande: dónde vive el proyecto. V1 se cierra, pero no por donde
> se esperaba.

## 1. Qué pasó con V1

La verificación bloqueante era *"¿existe el video de faena?"*. La respuesta: **no hay acceso a
video de faena minera; sí lo hay a obra de construcción** de una inmobiliaria, más datasets
públicos.

Eso no es un contratiempo, es un cambio de escenario, y forzó una decisión que el proyecto venía
esquivando: **en qué dominio se declara, se evalúa y se demuestra el sistema.**

## 2. La decisión

Queda en [ADR-011](../arquitectura/adr/011-dominio-configurable.md):

| | |
|---|---|
| Dominio evaluado | **Construcción** |
| Minería | **Perfil de configuración** — se demuestra sin tocar código, se declara no evaluado |
| Perfiles | `perfiles/construccion.yaml` y `perfiles/mineria.yaml`, versionados |
| Regla que lo sostiene | `gepp-core` no contiene ningún EPP, zona ni umbral literal. Test sobre el AST |

**Por qué no "sirve para ambos" a secas:** declarar dos dominios obliga a evaluar en dos, y no hay
once semanas para eso. Declarar minería y demostrar sobre una obra es incoherente, y la comisión
lo nota. Con un perfil ejecutable se tienen las dos cosas sin mentir en ninguna.

## 3. Lo que este cambio regala

**Los cascos se ven.** En obra la cámara trabaja a 5-15 m; en faena a rajo abierto, a 20-50. La
aritmética de V2 es implacable con la segunda distancia y benigna con la primera. La construcción
no es el premio de consuelo: es donde el caso de uso es viable.

**Se cierra la brecha de dominio.** Todo lo público de EPP es construcción. La cascada de
preentrenamiento existía para salvar la distancia entre lo disponible y lo objetivo; si el
dominio evaluado *es* construcción, la cascada pierde un peldaño.

**Se caen cinco semanas de trámite.** El plazo del Reglamento Interno regía para instalar
vigilancia permanente, no para una grabación puntual y consentida con fines académicos. Vuelven
S4-S9 al desarrollo. Lo que sí hace falta son dos papeles: autorización de la empresa y
consentimiento de las personas grabadas.

**La portabilidad deja de ser un párrafo de intenciones** y pasa a ser una demostración de tres
minutos — que era justo lo que V10 no sabía responder.

## 4. La trampa que casi entra sin que nadie la vea

"Rescatamos datasets de internet" suena a solución y es media solución. **Casi todo lo público de
EPP son imágenes sueltas, no video.** Y un dataset de imágenes:

- no tiene tiempo → no hay reglas en segundos
- no tiene continuidad → no hay tracks de ByteTrack
- no tiene duración → no hay eventos, que es la unidad de salida del sistema
- no puede correr `test_la_regla_en_segundos_es_invariante_a_la_cadencia`

Es decir: **entrena, pero no prueba.** Queda escrito como división no negociable en
[`07-datasets.md`](../producto/07-datasets.md).

La consecuencia práctica es una tarea nueva que sustituye al trámite del RIOHS en el cronograma:
**grabar 20-30 minutos continuos de video propio en la obra, cámara fija, en S5.** Es una tarde de
trabajo y es el único activo insustituible del proyecto.

## 5. El primer lote, medido

Llegaron cuatro clips de bancos de stock. `scripts/inventario_video.py` los fichó sin más
dependencia que `ffprobe`:

| Archivo | Resolución | seg | Orient. | Cámara |
|---|---|---|---|---|
| Hong Kong | 1280×720 | 59,0 | horizontal | **fija** |
| Casa / palas | 1280×720 | 6,0 | horizontal | deriva leve |
| `16707074` | 720×1280 | 25,9 | **vertical** | deriva leve |
| `14656570` | 720×1280 | 16,0 | **vertical** | se mueve |

**107 s en total. De los 20-30 min que hacen falta.** Y un solo archivo sirve como conjunto de
prueba: el de Hong Kong, por cámara fija y duración.

**Cómo se detecta que la cámara se mueve, y el error que costó dos intentos:** la primera versión
comparaba el perímetro de cada cuadro contra el primero usando la **media** de las diferencias, y
marcó los cuatro clips como *se mueve*. Comparando a ojo el primer y el último cuadro del de Hong
Kong quedó claro que era falso: mismo encuadre, escena distinta. Basta con que una esquina del
perímetro tenga gente trabajando para disparar el promedio. Con la **mediana** el criterio pasa a
exigir que la mayoría del fondo haya cambiado —que es lo que ocurre en un paneo y no cuando solo
se mueve lo que hay dentro del encuadre— y el resultado coincide con lo que se ve.

**V2 tiene su primera medición real.** Sobre cuadro nativo, con rejilla de 10 px: el casco mide
~60 px en primer plano y ~40 px al fondo del encuadre; tras reescalar a 560 quedan ~26 px y
~17 px, contra un umbral de 20. Es decir: **en un mismo encuadre conviven zonas evaluables y zonas
que no lo son**, que es justo lo que la tabla `zona × EPP × evaluable` existe para registrar.

Y queda confirmado con números que **la resolución de origen no salva nada**: en 1920 el casco
mediría 90 px, pero el factor de reescalado cae de 0,44 a 0,29 y llega igual a ~26 px. Lo que
mueve la aguja es el ángulo de visión y el *tiling*.

## 6. Qué se tocó

| Archivo | Cambio |
|---|---|
| `adr/011-dominio-configurable.md` | **Nuevo** — la decisión |
| `producto/07-datasets.md` | **Nuevo** — manifiesto de procedencia del material |
| `sistema/scripts/inventario_video.py` | **Nuevo** — inventario técnico de video, sin dependencias |
| `producto/06-verificaciones-criticas.md` | V1 cerrada · V2 con el paso del reescalado · V5 reorientada |
| `producto/03-plan-de-trabajo.md` | RIOHS fuera · tarea de grabación en S5 · riesgo nuevo |
| `producto/01-problema-y-vision.md`, `README.md` | Dominio |
| `arquitectura/00-arquitectura.md` | Cascada de preentrenamiento acortada |
| `arquitectura/01-modelo-de-datos.md`, `producto/02-privacidad-y-cumplimiento.md` | DS 594 como norma fundante; DS 132 al perfil minero |
| `adr/001`, `adr/010`, `PROMPT-DISENO.md` | Referencias al cliente |

**Lo que no se tocó: los diez ADR anteriores siguen en pie sin una enmienda.** Que una decisión de
este tamaño no obligue a reabrir ninguno es la evidencia de que la arquitectura estaba bien
separada del dominio.

## 7. Lo que queda, en orden

| Prioridad | Qué | Quién | Cuándo |
|---|---|---|---|
| 🔴 | **V2**: tabla de píxeles sobre objetivo, con el paso del reescalado | Edgar | **S3** |
| 🔴 | Presentar ADR-011 al equipo y validarlo | Equipo | Próxima reunión |
| 🟠 | Diseño de interfaz **junto con** el contrato OpenAPI congelado y el servidor simulado | Edgar + Frontend | S3-S4 |
| 🟠 | V9: sumar las horas contra las 11 semanas | Edgar | S4 |
| 🟠 | Competencias del perfil de egreso para la Guía 1.5 | Equipo | S4 |
| 🔴 | Pedir los dos papeles y **grabar los 20-30 min** | Equipo | S5 |
| 🔴 | **Conseguir más video largo y de cámara fija** — hay 1,8 min de los 20-30 | Equipo | S5 |

> **Nota sobre el orden del frontend:** el diseño solo desbloquea al compañero si viene con el
> contrato de API congelado. Sin él construye contra datos inventados y hay que rehacerlo. Por eso
> el issue #4 sube de S5 a la semana del diseño.
