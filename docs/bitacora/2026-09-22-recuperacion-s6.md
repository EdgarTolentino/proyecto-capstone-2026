# Bitácora · 22 de septiembre de 2026 — Recuperación de la S5 y la S6, y H2 adelantado

Al empezar la S6, del lado de visión y backend no había nada construido: PT-01 (persistencia) y
PT-02 (grabación) seguían abiertos, y `gepp-vision` y `gepp-api` estaban vacíos. En una jornada se
construyeron seis paquetes de trabajo, incluida la API real, que estaba prevista para la S9.

## 1. Lo que entró

| PT | Qué | PR |
|---|---|---|
| PT-01 | `gepp-bd`: 14 tablas, migraciones Alembic, repositorios, semilla del perfil de construcción, ER y `esquema.sql`. ADR-012 aceptada | #64 |
| PT-05 | Lectura del video con reloj de captura, muestreo a 5 fps sin deriva, máscaras y pixelado | #63 |
| PT-07 | Detector falso guionado, seguidor IoU, pipeline de la Etapa 1 sin E/S | #65 |
| PT-06 | Ingesta: vigilante por sondeo, cola Redis, trabajador, evidencia pixelada, outbox | #67 |
| PT-03 | Guía de etiquetado, deduplicación dHash, partición por video, datasets con licencia verificada | #66 |
| — | `make demo` sobre el video sintético CAM 03 y ffmpeg en CI | #68 |
| PT-09 | API real: las 18 operaciones del contrato contra PostgreSQL; la web funciona sin cambios | #69 |
| PT-10 | Prueba del recorrido H2, `make demo-api`, guía y guion de la demo (`docs/operacion/recorrido-h2.md`) | este PR |

## 2. Lo que falló y cómo se arregló

| Qué pasó | Por qué | Arreglo |
|---|---|---|
| `deteccion.track_id NOT NULL` en el modelo de datos | En el dominio solo la persona lleva track; casco y chaleco se asocian después. Con `NOT NULL` el recálculo sin GPU se quedaba sin EPP | Columna nullable; la diferencia quedó escrita en `01-modelo-de-datos.md` |
| Las cajas releídas no eran iguales a las escritas | `REAL` es float4: 0,43 vuelve como 0,4300000012 | Comparación con tolerancia; float4 sobra para coordenadas normalizadas |
| `roboflow/trackers` no se pudo usar | Exige `opencv-python`, que choca con `opencv-python-headless` (instalan el mismo `cv2`) | Seguidor IoU propio, provisional; ByteTrack se decide en PT-08 |
| La prueba que fecha el video desde sus metadatos no corría en CI | El ejecutor de GitHub no trae ffmpeg y la prueba se saltaba en silencio | `apt-get install ffmpeg` en el trabajo de pruebas |
| Fusionar una cadena de PR con squash | Cada PR arrastraba los commits originales del anterior, que ya habían entrado aplastados: `uv.lock` en conflicto | Rebase de cada PR sobre `main` con `git rebase --onto` |
| GitHub **cerró** el #67 al fusionar el #65 | `--delete-branch` borró la rama que era base del #67 | Rama recreada un momento, PR reabierto con base `main`. Regla: antes de fusionar, apuntar a `main` los PR que dependen de esa rama |
| Pruebas que fallaban solo al correr dos suites a la vez | Las dos usaban `gepp_pruebas` y el fixture la recrea con `FORCE` | Una base por proceso (`<base>_pruebas_<pid>`), borrada al terminar |
| La API mandaba `null` en campos que el contrato no admite (`ancho`, `alto`, bloque técnico sin video) | La base los admite nulos; el contrato los declara opcionales, pero no nulos | Se omiten cuando no hay dato. Lo detectó el validador que compara cada respuesta con el YAML |
| Una prueba de turno esperaba el turno A | `T0` = 02:10 UTC = 22:10 en Santiago: turno B | Se corrigió la expectativa, no el código. El turno se decide con la hora local de la faena |
| No se podían sacar capturas de la web desde WSL | Al Chromium de Playwright le faltan librerías del sistema | Edge de Windows en modo headless contra `localhost` |

## 3. Números del cierre

- 227 pruebas sin GPU; 90 usan PostgreSQL (`make up`). CI las corre todas con la base como servicio.
- `make contrato`: 18 de 18 operaciones.
- `make demo` sobre CAM 03: 1 hallazgo sin casco ni chaleco de 3,4 s con 18 cuadros confirmados
  (3,4 × 5 = 17: se cumple `cuadros_confirmados ≈ duracion_s × 5`).

## 4. Pendiente

- **Grabación en obra (#10):** es la ruta crítica, y sin ella no hay lote 0 real ni conjunto de prueba.
- Matriz de EPP (#7) y píxeles por cámara (#3): ajustan `perfiles/construccion.yaml`.
- CVAT arriba y la guía de etiquetado revisada por Miguel y Lian.
- H2: grabar la demostración con el guion de `recorrido-h2.md`, probarla en el portátil de Miguel
  o de Lian y crear la etiqueta de la semana.
