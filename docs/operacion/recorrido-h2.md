# Recorrido H2 — del video a la bandeja, en un portátil sin GPU

> Hito H2 (#33). Se sigue de arriba abajo, sin saber nada del proyecto. Si un paso falla, se anota
> en la bitácora de la semana con lo que se vio y cómo se arregló.

## Qué se demuestra

Un video entra por un extremo y el hallazgo aparece por el otro, en la bandeja, con la evidencia
difuminada y la explicación de por qué se disparó. **Todo el sistema es real salvo el modelo:** el
detector lee un guion escrito a mano mirando el video (`demo/guion_cam03.json`). El modelo
entrenado lo reemplaza en PT-08 sin tocar nada más. Así se dice en la demostración.

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

## Pasos

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
| Hallazgos | **1**: sin casco ni chaleco, ~3,4 s, "Casco y chaleco en acceso" |
| Evidencia | 1 recorte |
| Avisos (outbox) | 1 pendiente |

La persona que está 1,5 s sin casco **no** genera hallazgo: la regla exige 2 s. Es lo que
demuestra que las reglas van en segundos.

Luego, en dos terminales:

```bash
make demo-api                                                     # 3. API en :8000
cd apps/web && npm ci && VITE_API_URL=http://localhost:8000/api/v1 npm run dev   # 4. web en :5173
```

Se abre <http://localhost:5173>: la bandeja muestra el hallazgo; **Ver** abre el visor con el
recorte pixelado, la línea de tiempo (primera detección → umbral → fin) y "Por qué se disparó".

## Guion para grabar la demostración (≈ 3 min)

| Tiempo | En pantalla | Qué se dice |
|---|---|---|
| 0:00 | La carpeta con el video | "Este es un video de cámara fija de obra. Es sintético, generado con IA: no hay personas reales" |
| 0:20 | `make demo` corriendo | "Lo dejo en la carpeta que vigila el sistema. Se lee a 5 cuadros por segundo; el detector hoy es simulado y en la semana 8 entra el modelo" |
| 0:50 | La tabla de hallazgos | "Un hallazgo: sin casco ni chaleco, 3,4 segundos. El que estuvo 1,5 s sin casco no cuenta: la regla pide 2 s" |
| 1:10 | La segunda copia sin duplicar | "Si el mismo video llega dos veces, no se duplica nada: la clave es el hash del archivo" |
| 1:30 | La bandeja | "El prevencionista ve la bandeja; cada hallazgo dice que es un indicio y requiere validación humana" |
| 1:50 | El visor | "La evidencia se guarda ya pixelada: no existe una versión con rostro. Y aquí se explica qué regla, qué versión y qué umbral" |
| 2:30 | Confirmar | "Lo confirma; queda auditado quién y cuándo. El contador baja" |

Grabación en Windows: `Win + Alt + R` (barra de juegos) o OBS. El archivo **no** va al
repositorio: se sube a la carpeta del equipo y aquí se deja el enlace.

## Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `connection refused` en el 5432 | PostgreSQL no está arriba | `make up` y esperar 5 s |
| El video queda `en_cola` | El trabajador no arrancó | Ver la salida de `make demo`; `docker ps` debe mostrar Redis |
| `ruta bajo /mnt/ rechazada` | El repositorio o el video están en el disco de Windows | Copiarlos a `~/` |
| La web dice "No pudimos comunicarnos con la API" | Falta `VITE_API_URL` o la API no está arriba | Revisar la terminal de `make demo-api` |
| La bandeja sale vacía | La API apunta a otra base | Usar `make demo-api`, no `make api` |
