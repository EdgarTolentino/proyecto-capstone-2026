# Recorrido H2 — del video a la bandeja, en un portátil sin GPU

> Hito H2 (#33). Se sigue de arriba abajo, sin saber nada del proyecto. Si un paso falla, se anota
> en la bitácora de la semana con lo que se vio y cómo se arregló.

## Qué se demuestra

Un video entra por un extremo y el hallazgo aparece por el otro, en la bandeja, con la evidencia
difuminada y la explicación de por qué se disparó. **Todo el sistema es real salvo el modelo:** el
detector lee un guion escrito a mano mirando el video (`demo/guion_cam03.json`). El modelo
entrenado lo reemplaza en PT-08 sin tocar nada más. Así se dice en la demostración.

Hay dos caminos. El **principal** es el que se muestra en la demo: el video se pide **desde la web**
(Videos → «Procesar video»). El **alternativo** es la carpeta vigilada (`make demo`), que no
necesita la web para meter el video.

| | Principal: desde la web | Alternativo: carpeta vigilada |
|---|---|---|
| Cómo entra el video | Se copia a `GEPP_CARPETA_ENTRADA` y se pide en el diálogo «Procesar video», eligiendo la cámara | Se copia a `GEPP_CARPETA_VIGILADA` y el vigilante lo toma solo, con la cámara de `GEPP_FUENTE_ID` |
| Qué se ve | Pedido, avance en la fila, vista en vivo del modelo, hallazgos | Hallazgos |
| Comandos | Sección «Recorrido principal» | Secciones «Todo con un comando» y «Camino alternativo» |

## Requisitos

| Qué | Versión | Cómo comprobarlo |
|---|---|---|
| Docker (con Docker Desktop en Windows) | cualquiera reciente | `docker ps` |
| uv | 0.9 o más | `uv --version` |
| Node | 22 | `node --version` |
| ffmpeg | cualquiera | `ffprobe -version` |
| El video de demostración | `generativa.mp4` (CAM 03, sintético) | Lo comparte Edgar; **no está en el repositorio** |

En Windows todo se corre dentro de WSL2 y el repositorio se clona en el disco de Linux
(`~/`), **no** en `/mnt/c/`: la ingesta rechaza rutas bajo `/mnt/` (ADR-005).

## Recorrido principal: el video se pide desde la web

Se levantan cuatro cosas: la base (con Redis), la API, el trabajador y la web. Los puertos son el
8000 (API) y el 5173 (web); si `make demo-todo` o `make demo-api` están corriendo, apágalos antes
(`make demo-apagar`), porque usan los mismos puertos.

### 1. Preparar (solo la primera vez)

```bash
cd "Fase 2/sistema"
make setup                 # dependencias de Python
make up                    # PostgreSQL y Redis (Docker)
make migrar                # crea las tablas en la base `gepp`
make semilla               # cámaras, reglas y las cuentas del equipo
cp .env.example .env
mkdir -p ~/gepp/vigilada ~/gepp/entrada ~/gepp/evidencia
```

Luego edita `.env` (está en `Fase 2/sistema/`; nunca se versiona). Estas son las líneas que
importan para este recorrido; el resto déjalo como viene:

| Variable | Qué poner | Por qué |
|---|---|---|
| `GEPP_API_TOKENS` | **Déjala comentada**, como viene en `.env.example` | Sin definirla entran `demo` (prevencionista), `mortega` (administrador) y `lgrandon` (prevencionista). Definida pero **vacía** no cae a ese mapa y nadie entra (401) |
| `GEPP_CARPETA_VIGILADA` | `/home/<tú>/gepp/vigilada` | Obligatoria para el trabajador. Debe estar en el disco de Linux, no bajo `/mnt/` |
| `GEPP_CARPETA_EVIDENCIA` | `/home/<tú>/gepp/evidencia` | Donde quedan los recortes difuminados |
| `GEPP_CARPETA_ENTRADA` | `/home/<tú>/gepp/entrada` | Los videos que se piden desde la web. Debe existir, no estar bajo `/mnt/` y **no ser ni estar dentro de** la vigilada (ni al revés). La leen la API y el trabajador: deben ver la misma ruta |
| `GEPP_VISTA_EN_VIVO` | `1` | La vista en vivo viene **apagada** (`0`); solo el valor `1` la enciende |
| `GEPP_GUION_FALSO` | `demo/guion_cam03.json` si usas `generativa.mp4` sin modelo; si usas el modelo, **borra la línea** | Sin modelo el detector lee un guion escrito a mano; con modelo no debe estar |
| `GEPP_MODELO_RUTA` | Solo con modelo: la ruta al `.onnx` (con su `.clases.json` al lado) | Corre en CPU, sin GPU. Ver [modelo-onnx.md](modelo-onnx.md) |

`GEPP_CARPETA_VIVO` (por defecto `/dev/shm/gepp-vivo`, memoria) y `GEPP_VIVO_FPS` (por defecto
`25`, debe ser un número positivo o el trabajador no arranca) no hace falta tocarlas.

### 2. Levantar (tres terminales, desde `Fase 2/sistema`)

```bash
make api                                                # 1. API en :8000 (el Makefile carga el .env)
set -a; . ./.env; set +a; uv run python -m gepp_worker  # 2. trabajador (no hay `make` para él: carga el .env a mano)
cd apps/web && npm ci && VITE_API_URL=http://localhost:8000/api/v1 npm run dev   # 3. web en :5173
```

El trabajador imprime `[trabajador] esperando videos`. Si en su lugar dice
`sin GEPP_CARPETA_ENTRADA: no atiende pedidos de la web`, la variable no llegó a su entorno.

Copia el video a la carpeta de entrada (no a la vigilada):

```bash
cp ~/videos/generativa.mp4 ~/gepp/entrada/
```

### 3. Recorrer la web

Se abre <http://localhost:5173>. Entras como el **prevencionista de demostración** (token `demo`,
el que la web usa si no defines otro). También sirve `lgrandon` (prevencionista): ponlo en
`apps/web/.env.development.local` como `VITE_API_TOKEN=lgrandon`. Con `mortega`
(administrador) puedes pedir videos pero **no ves la vista en vivo**: ese rol no tiene
`ver_evidencia`.

| Paso | Dónde | Qué se ve |
|---|---|---|
| 1 | Menú lateral → **Videos** | «Cola de videos»; vacía dice «No hay videos en la cola.» |
| 2 | Botón **Procesar video** (arriba a la derecha) | Diálogo «Procesar video» |
| 3 | En el diálogo | «Archivo»: los videos de la carpeta de entrada, con su tamaño (y «Posible duplicado» si ya hay uno registrado con el mismo nombre y tamaño). «Cámara»: «Cámara 01 · acceso» o «Cámara 02 · obra gruesa». Pulsa **Procesar** |
| 4 | Sobre la tabla | Avisa «El archivo … quedó pedido; se registrará cuando el trabajador lo tome.» y aparece el panel «Pedidos de procesamiento»: «Pedido pendiente» → «Registrando» → «Registrado» (si falla, «Rechazado» y el motivo) |
| 5 | Tabla «Cola de videos» | La fila pasa de «En cola» a «Procesando», con una barra de avance, el tiempo (como `0:12 de 0:40 (30 %)`), la velocidad y «En el cuadro actual: N personas, N cascos, N chalecos.», luego «Guardando resultados…» y por fin «Listo» |
| 6 | Bajo la fila «Procesando» | **Vista en vivo.** Primero «Esperando el primer cuadro…»; después el cuadro con las cajas de persona, casco y chaleco y el rótulo «Vista del modelo · en vivo (~1 s de atraso)» |
| 7 | Menú lateral → **Hallazgos** | «Bandeja de hallazgos» con lo que salió |
| 8 | **Ver** en un hallazgo | El visor: el recorte difuminado, la línea de tiempo y «Por qué se disparó» |

> **La vista en vivo muestra las caras sin tapar.** Es una excepción decidida por Edgar Tolentino el
> 2026-10-09 (nota del 2026-10-09 en [ADR-006](../arquitectura/adr/006-sin-identificacion.md) y
> «Excepción: vista en vivo del procesamiento» en
> [02-privacidad-y-cumplimiento](../producto/02-privacidad-y-cumplimiento.md)): solo la ven los roles
> con `ver_evidencia`, solo con `GEPP_VISTA_EN_VIVO=1`, queda en memoria y no se guarda. **La
> evidencia que se guarda (los recortes del visor) sigue difuminada.**

Con `generativa.mp4` y el guion `demo/guion_cam03.json` se espera el mismo hallazgo que en el
camino alternativo (ver la tabla de abajo): en la «Cámara 02 · obra gruesa», crítico; en la
«Cámara 01 · acceso», alta.

## Camino alternativo: carpeta vigilada

### Todo con un comando

```bash
cd "Fase 2/sistema"
make setup                                        # solo la primera vez
make demo-todo VIDEO=~/videos/generativa.mp4      # base, demo, API y web; abre el navegador
make demo-apagar                                  # al terminar
```

`FUENTE=1` usa la cámara de acceso (regla alta: el aviso va al resumen); por defecto es la 2
(regla crítica: aviso inmediato), tanto en `make demo-todo` como en `make demo`. Si el `.env` tiene
el bot de Telegram, arranca también el despachador. Los pasos de abajo son lo mismo, uno por uno.

> No mezclar los dos caminos en una misma sesión: `make demo-todo` vuelve a crear la base `gepp_demo`
> desde cero, así que lo que mostraba la web hasta ese momento desaparece, y ocupa los puertos 8000 y
> 5173 que usa el recorrido principal.

### Paso a paso

Desde `Fase 2/sistema`:

```bash
make setup                 # 1. dependencias de Python (una vez)
make up                    # 2. PostgreSQL y Redis en Docker
make demo VIDEO=~/videos/generativa.mp4
```

`make demo` crea una base aparte (`gepp_demo`), levanta el trabajador, copia el video a una carpeta
vigilada, espera a que quede `listo`, lo copia **otra vez** para mostrar que no se duplica e
imprime lo que quedó en la base. Lo esperado:

| Bloque | Esperado |
|---|---|
| Video | `listo` · 40 cuadros (8 s a 5 fps) · reloj `mtime` |
| Hallazgos | **1**: sin casco ni chaleco, ~2 s ("Casco y chaleco en obra gruesa", crítico; con `FUENTE=1`, "Casco y chaleco en acceso", alta) |
| Evidencia | 1 recorte |
| Avisos (outbox) | 1 pendiente |

La persona que está 1,5 s sin casco **no** genera hallazgo: la regla exige 2 s. Es lo que
demuestra que las reglas van en segundos.

Luego, en dos terminales:

```bash
make demo-api                                                     # 3. API en :8000
cd apps/web && npm ci && VITE_API_URL=http://localhost:8000/api/v1 npm run dev   # 4. web en :5173
# Para entrar con tu cuenta en vez del prevencionista de demo: VITE_API_TOKEN=mortega (o lgrandon), o ponlo en apps/web/.env.development.local
```

Se abre <http://localhost:5173>: la bandeja de Hallazgos muestra el hallazgo; **Ver** abre el visor con el
recorte pixelado, la línea de tiempo (primera detección → umbral → fin) y "Por qué se disparó".

## Guion para grabar la demostración (≈ 4 min)

Los tiempos son una guía: se ajustan al ensayar. El video a mostrar lo define Edgar.

| Tiempo | En pantalla | Qué se dice |
|---|---|---|
| 0:00 | La carpeta con el video (video a definir por Edgar) | "Este es un video de cámara fija de obra. Es sintético, generado con IA: no hay personas reales" |
| 0:20 | Videos → **Procesar video**: el diálogo con el archivo y la cámara elegidos | "El prevencionista elige el video de la carpeta del servidor y la cámara que lo grabó. No se sube nada desde el navegador" |
| 0:40 | El panel «Pedidos de procesamiento» y la fila con su barra de avance | "El pedido queda anotado; el trabajador lo toma, lo registra y empieza a procesarlo. Se lee a 5 cuadros por segundo; el detector hoy es simulado y en la semana 8 entra el modelo" |
| 1:00 | La vista en vivo bajo la fila (video a definir por Edgar) | "Esto es lo que ve el modelo, con un segundo de atraso. Aquí las caras se ven sin tapar: es una excepción acotada, decidida el 9 de octubre y documentada en el ADR-006; solo la ven los roles con permiso de evidencia, está apagada por defecto y no se guarda nada. Lo que se guarda como evidencia sí va difuminado" |
| 1:30 | La fila en «Listo» y la tabla de hallazgos | "Un hallazgo: sin casco ni chaleco, unos 2 segundos: lleva gorra, no casco. El que estuvo 1,5 s sin casco no cuenta: la regla pide 2 s" |
| 1:50 | El diálogo con «Posible duplicado» | "Si el mismo video llega dos veces, no se duplica nada: la clave es el hash del archivo" |
| 2:10 | La bandeja | "El prevencionista ve la bandeja; cada hallazgo dice que es un indicio y requiere validación humana" |
| 2:30 | El visor | "La evidencia se guarda ya pixelada: no existe una versión con rostro. Y aquí se explica qué regla, qué versión y qué umbral" |
| 3:10 | Confirmar | "Lo confirma; queda auditado quién y cuándo. El contador baja" |

Grabación en Windows: `Win + Alt + R` (barra de juegos) o OBS. El archivo **no** va al
repositorio: se sube a la carpeta del equipo y aquí se deja el enlace.

## Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `connection refused` en el 5432 | PostgreSQL no está arriba | `make up` y esperar 5 s |
| El video queda `en_cola` | El trabajador no arrancó | Ver la salida de `make demo`; `docker ps` debe mostrar Redis |
| El video queda `reintentando` o `error` | El trabajador lo intentó y falló; en `error` agotó los 3 intentos | Leer `error_motivo` en `GET /videos`: "No se pudo leer el video" es el archivo; "no tiene reglas activas" es la configuración de la cámara. Corregida la causa, `POST /videos/{id}/reprocesar` lo devuelve a la cola |
| `ruta bajo /mnt/ rechazada` | El repositorio o el video están en el disco de Windows | Copiarlos a `~/` |
| La web dice "No pudimos comunicarnos con la API" | Falta `VITE_API_URL` o la API no está arriba | Revisar la terminal de `make demo-api` |
| La bandeja sale vacía | La API apunta a otra base | En el camino alternativo, usar `make demo-api`, no `make api`. En el principal, al revés: `make api` y haber corrido `make migrar` y `make semilla` |
| Nadie puede entrar (401) | `GEPP_API_TOKENS=` quedó vacía en el `.env` | Borrar esa línea del `.env` y reiniciar `make api` |
| No aparece el botón «Procesar video» | La cuenta no tiene el permiso `procesar_videos` | Entrar como `demo` o `lgrandon` (prevencionista) o `mortega` (administrador) |
| El diálogo dice «El servidor no tiene configurada la carpeta de entrada.» | Falta `GEPP_CARPETA_ENTRADA` en la API | Ponerla en el `.env` y reiniciar `make api` |
| El diálogo dice «No hay archivos en la carpeta de entrada.» | El video no está en `GEPP_CARPETA_ENTRADA`, o no es `.mp4`, `.mov`, `.mkv` ni `.avi` | Copiarlo ahí |
| El pedido se queda en «Pedido pendiente» | El trabajador no está corriendo, o arrancó sin `GEPP_CARPETA_ENTRADA` | Ver la terminal del trabajador: debe decir `esperando videos` y no `no atiende pedidos de la web` |
| El trabajador no arranca | Carpeta de entrada inexistente, bajo `/mnt/` o dentro de la vigilada; `GEPP_VIVO_FPS` inválido; falta el modelo | Leer el mensaje: dice cuál variable falla |
| No aparece la vista en vivo | `GEPP_VISTA_EN_VIVO` no es `1` (en la API **y** en el trabajador), la cuenta es administrador, o el video ya terminó | Poner `1`, reiniciar los dos y entrar como prevencionista |
| La vista en vivo dice «La vista del modelo terminó.» | Pasaron 60 s sin cuadros nuevos | Es lo esperado cuando el video terminó |
