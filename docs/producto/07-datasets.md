# Manifiesto de datos — origen y uso

> Registro de procedencia del material con que se entrena y se evalúa. Sirve para dos cosas
> concretas: poder responder en la defensa **de dónde salió cada dato**, y saber qué hay que
> volver a conseguir si un lote resulta inservible.

**La regla: ningún dato entra al entrenamiento ni a la evaluación sin una fila en este
documento.** El uso es académico, dentro del Portafolio de Título.

## 1. La división que manda

Sale del [ADR-011](../arquitectura/adr/011-dominio-configurable.md) y no se negocia:

| | Origen | Tipo | Para qué |
|---|---|---|---|
| **Entrenamiento** | Datasets públicos | Imágenes | Preentrenar el detector de persona / casco / chaleco |
| **Entrenamiento, escena de obra** | Video público CC BY (lote 5) | Video | Enseñar `cabeza` desde una cámara en altura (decisión de Edgar, 2026-10-27) |
| **Prueba y demostración** | Grabación propia en obra | **Video** | Conjunto de prueba, tracks, eventos, defensa de S15 |

**Por qué importa la columna "tipo":** un dataset de imágenes sueltas no tiene tiempo. No produce
tracks, no permite reglas en segundos, no puede correr
`test_la_regla_en_segundos_es_invariante_a_la_cadencia` y no evalúa un solo evento. Es material de
entrenamiento y **jamás** conjunto de prueba. El video del lote 5 también es entrenamiento, por
decisión aparte, y tampoco es prueba. Confundir las dos cosas es el error que dejaría el
proyecto sin nada que defender.

### Decisión del 2026-10-01: no hay grabación propia

El equipo decidió **no grabar en obra** (#10 se cierra). Un video de YouTube (2 h 32 min, lote 3)
ocupa el lugar de la grabación propia, con una regla que no cambia: **se usa solo para prueba y
demostración, nunca para entrenar.** El detector se entrena con los datasets públicos de §2.bis
y, desde el 2026-10-27 (decisión de Edgar), con el video público CC BY del lote 5; el video de
este lote 3 nunca entra a entrenar. Lo que sale de esta decisión:

- La métrica de prueba se mide en una escena que el modelo no vio. Es más débil que una
  grabación propia, porque es una sola escena y una sola cámara, y así se declara en el informe.
- El video no tiene licencia de reutilización declarada. Queda fuera del repositorio y se
  registra en el lote 3 con su URL y esa salvedad. La única excepción son dos cuadros de la
  vista en vivo, citados con su fuente en `Evidencias de sistema/Aplicación` como evidencia del
  avance (decisión de Edgar, 2026-10-13), con los rostros tapados.
- Ya no aplican la autorización de la empresa ni el consentimiento de §3: no se graba a nadie.
  Sigue aplicando el ADR-006 (rostro difuminado en todo recorte, sin identificación).

**Cambio del 2026-10-17 (decisión de Edgar):** sí hay una grabación propia, corta y en oficina
(lote 4). Con ella vuelven a aplicar la autorización y el consentimiento de §3, y la regla del
video de prueba no cambia: **solo prueba, nunca entrenamiento.** El lote 3 sigue siendo el
conjunto de prueba principal; el lote 4 agrega una segunda escena, de cerca.

## 2. Inventario

Se llena con `scripts/inventario_video.py`, que saca de cada archivo lo que aquí importa sin
pedir ninguna dependencia — solo `ffprobe`:

```bash
python3 "Fase 2/sistema/scripts/inventario_video.py" ruta/a/los/videos
```

### Lote 1 — descargado el 2026-09-04 · bancos de video de stock

| Archivo | Resolución | fps | seg | Orient. | Cámara | Uso |
|---|---|---|---|---|---|---|
| `vecteezy_construction-works-in-hong-kong_28840504` | 1280×720 | 24 | 59,0 | horizontal | **fija** | **Prueba** |
| `vecteezy_construction-of-a-house-workers-clear-a-place…` | 1280×720 | 25 | 6,0 | horizontal | deriva leve | Entrenamiento |
| `16707074_720_1280_30fps` | 720×1280 | 30 | 25,9 | **vertical** | deriva leve | Entrenamiento |
| `14656570_720_1280_30fps` | 720×1280 | 30 | 16,0 | **vertical** | **se mueve** | Entrenamiento |

**Total: 107 s (1,8 min) · 534 cuadros a 5 fps.**

Un solo archivo del lote cumple las dos condiciones de un conjunto de prueba —cámara fija y
duración utilizable—: el de Hong Kong, con 59 s. Los otros tres son material de entrenamiento:
dos verticales, que desperdician el 44 % del canvas del detector en relleno, y uno de 6 s.

### Cómo se detecta que la cámara se mueve

El script compara la franja perimetral de cada cuadro contra el primero y toma la **mediana** de
las diferencias, no la media. La media da falsos positivos: basta con que una esquina tenga gente
trabajando para dispararla — de hecho, con la media el clip de Hong Kong salía marcado como *se
mueve* siendo de cámara fija. La mediana exige que **la mayoría** del fondo haya cambiado, que es
lo que ocurre en un paneo y no cuando solo se mueve lo que hay dentro del encuadre.

Umbrales: `<8` fija · `8-20` deriva leve · `>20` se mueve.

### Píxeles sobre objetivo — medición real (V2)

Medido sobre un cuadro nativo del clip de Hong Kong, con rejilla de 10 px:

| Posición en el cuadro | Ancho del casco | Tras reescalar a 560 | ¿Sobrevive? |
|---|---|---|---|
| Primer plano | ~60 px | ~26 px | ✅ |
| Media distancia | ~63 px | ~28 px | ✅ |
| Fondo del encuadre | ~40 px | **~17 px** | ❌ |

Con la entrada del detector en 560 px, un casco necesita **≥46 px en el cuadro** para llegar a los
20 px que hacen falta. En este material lo cumplen los cascos cercanos y medios; **los del fondo
no**.

**La conclusión que manda:** subir la cámara a 4K no cambia nada. Un casco que en 1280 mide 60 px
mide 90 px en 1920, pero el factor de reescalado baja de 0,44 a 0,29 y el resultado en la entrada
del detector es **el mismo**. Lo que mueve la aguja es el **ángulo de visión** —cuánta escena cabe
en el cuadro— y el ***tiling***: partir el cuadro y correr el detector sobre cada trozo.

### Campos obligatorios de cada fila

URL o banco de origen · fecha de descarga · duración o número de imágenes · clases presentes ·
si la cámara es fija.

### Lote 2 — 2026-09-22 · video generado por IA (sintético)

| Archivo | Resolución | fps | seg | Cámara | Uso |
|---|---|---|---|---|---|
| `generativa.mp4` (CAM 03) | 1280×720 | 24 | 8,0 | fija, con cortes de escena | **Demostración del MVP** (`make demo`) |

**Es video sintético, generado con IA, y se declara así** en toda presentación. No es
grabación de obra ni reemplaza el video propio (#10). La marca `CAM 03` con fecha y hora está
sobreimpresa y el sistema **no la lee**: el reloj sale de los metadatos o de la fecha del archivo
(ADR-005). Los cortes de escena parten los tracks; para la demostración no importa, para el
conjunto de prueba sí. El plan es unir estos clips en uno largo con la misma marca; los clips
originales se conservan por separado, porque la partición es por video.

### Lote 3 — 2026-10-01 · video de YouTube · **el conjunto de prueba**

| Campo | Valor |
|---|---|
| Origen | <https://www.youtube.com/watch?v=GPCHfE_-XQE>, canal de un vendedor de cámaras de seguridad, subido el 2018-09-18 |
| Licencia | No declara licencia de reutilización (licencia estándar de YouTube). Uso académico, fuera del repositorio, con esta salvedad (ver la decisión de arriba) |
| Técnica | 1920×1080, 30 fps, 2 h 32 min (9.140 s), VP9 |
| Cámara | **Fija**: se desplaza 0,2 px entre el minuto 5 y el 145 (correlación de fase sobre la pared del foso). `inventario_video.py` dice «se mueve», un falso positivo que probablemente provocan el reloj sobreimpreso y la cinta que flamea en el borde |
| Escena | Un foso de obra visto desde arriba. Las personas del fondo miden **41-81 px** de alto, y un casco unos 8 px: por eso se analiza con `DetectorMosaico` (#31) |
| Uso | **Solo prueba y demostración. Nunca entrenamiento** |

**El lote de etiquetado** (`datos/lote0.csv`, versionado; las imágenes quedan fuera del
repositorio):

| Tramo | Archivo | Cuadros |
|---|---|---|
| Minutos 20-25 | `yt_GPCHfE_min020.mp4` | 60 |
| Minutos 50-55 | `yt_GPCHfE_min050.mp4` | 60 |
| Minutos 85-90 | `yt_GPCHfE_min085.mp4` | 60 |
| Minutos 120-125 | `yt_GPCHfE_min120.mp4` | 60 |

Son 240 cuadros, uno cada 5 s, todos en la partición `prueba`. Se armó con
`lote0.py --sin-deduplicar`: con la deduplicación, 150 cuadros de un tramo quedaban en 1,
porque en una cámara fija el fondo domina el dHash. Los tramos están repartidos en las dos
horas y media para cubrir distintas fases de la obra. Uno cada 5 s da cuadros distintos
(las personas se mueven), pero no independientes: es una muestra para medir detección, no
un conjunto de miles.

### Lote 4 — 2026-10-17 · grabación propia con celular · prueba de cerca

| Campo | Valor |
|---|---|
| Origen | Grabación propia de Edgar con su celular, recibida por WhatsApp el 2026-10-17 |
| Autorización | Consentimiento de las personas grabadas y permiso del lugar, declarados por Edgar el 2026-10-17. Los papeles se guardan fuera del repositorio (§3) |
| Técnica | Tres videos de 128,9 s, 83,8 s y 129,3 s (342 s en total), 30 fps, verticales (576×1024 una vez rotados), recomprimidos por WhatsApp |
| Cámara | **En mano**: `inventario_video.py` da «se mueve» (mediana de perímetro 79-107). Sirve para medir detección cuadro a cuadro, no para zonas, tracks ni eventos. El inventario dice «horizontal» porque no lee la rotación del archivo; los cuadros que escribe `lote0.py` salen verticales |
| Escena | Una oficina, personas a pocos metros: con casco y chaleco, con el casco en la mano y subida a una silla. Clases presentes: persona, casco, chaleco |
| Uso | **Solo prueba, como medición aparte: su cifra nunca se suma a la del lote 3** (§4, tarea 3). Nunca entrenamiento |

**El lote de etiquetado** (`Fase 2/sistema/datos/lote-celular.csv`, versionado; las imágenes
quedan fuera del repositorio): 115 cuadros, uno cada 3 s, todos en la partición `prueba`
(`celular-01.mp4` 43, `celular-02.mp4` 28, `celular-03.mp4` 44), con `lote0.py
--sin-deduplicar`. Se etiquetan **sin pre-etiquetas**, para que la verdad no herede los
errores del modelo que se va a medir.

### Lote 5 — 2026-10-27 · video público de cámaras de obra en altura · **solo entrenamiento**

Decisión de Edgar del 2026-10-27, para enseñarle al modelo la `cabeza` (persona sin casco,
[ADR-013](../arquitectura/adr/013-incumplimiento-por-evidencia.md)) vista desde una cámara de obra
en altura: epp-v3 la aprendió de fotos de cerca y su recall de `cabeza` en el video del lote 3 es
0,008. El lote 3 sigue siendo solo prueba.

| Campo | Valor |
|---|---|
| Fecha de descarga | 2026-10-27, a `~/datos/gepp/cctv-cc/` (fuera del repositorio) |
| Licencia | **Creative Commons Attribution (CC BY)**, la que YouTube muestra como «Creative Commons Attribution license (reuse allowed)». Verificada el 2026-10-27 video por video con `yt-dlp --print "%(license)s"`. Solo se usan los videos que la declaran |
| Atribución | CC BY exige citar al autor. Se cita en el README del repositorio (sección «Atribución del video público CC BY»), junto a los datasets CC BY de §2.bis, y en el informe final, con canal, título, URL y licencia de cada video. Los videos no se redistribuyen: no están en el repositorio |
| Uso | **Solo entrenamiento. Nunca prueba**: la cifra que se reporta sigue saliendo de los lotes 3 y 4 |

**Fuente: canal «Construction Camera Swiss»**
(<https://www.youtube.com/channel/UCK04-wLgybCNo869wlT2pAQ>).

| Campo | Valor |
|---|---|
| Autor | Canal «Construction Camera Swiss» |
| Técnica | Timelapses de obra: 14 videos en 2160p (4K) y 4 en 1080p, de 58 a 191 s. 18 videos, 3,2 GB (`cat *.mp4 \| wc -c` = 3.190.956.212 bytes) |
| Cámara | Fija, en altura, sobre obras en Suiza. Por ser timelapse, las personas aparecen a saltos y no hay tracks continuos: sirve para enseñar apariencia, no para reglas en segundos |
| Selección | El canal tiene 116 videos y solo **18** declaran CC BY; el resto no se usa. Se evaluó también «Giga Berlin Timelapse» (Tobias Lindh): casi todos sus videos tienen licencia estándar de YouTube, así que no se usa |
| Cuadros | **1171**, uno cada 2 s, con `ffmpeg -vf fps=1/2 -q:v 2` (`ls ~/datos/gepp/cctv-cc/cuadros/*/ \| grep -c jpg` = 1171) |
| Pre-marcado | epp-v3 en mosaico. En 4K: `--recorte 0,300,3840,2160 --factor 0.5 --lado 384 --objeto-max-px 300`. En 1080p: `--recorte 0,150,1920,1080 --factor 1 --objeto-max-px 150`. El alto mediano de la persona detectada va de 47 a 108 px según el video |
| Descartados | 3 videos con poca gente (mediana de 0 personas por cuadro): quedan 1013 cuadros para entrenamiento de los 1171 |

| Id | Título | Altura | seg | Cuadros | Uso |
|---|---|---|---|---|---|
| `UVmFsIoasJ4` | Time-Lapse City Uster Seerestaurant | 2160p | 142 | 71 | entrenamiento |
| `EnFcSvWYhY4` | Construction Camera for Image Filme | 2160p | 81 | 41 | entrenamiento |
| `N2Wsw7qDjxQ` | Construction Camera for new Hospital Building | 2160p | 124 | 62 | entrenamiento |
| `bE9eUhZw_JQ` | Construction Camera new School Diessenhofen | 2160p | 144 | 72 | entrenamiento |
| `v2cCZj7g2bA` | Baustellenkamera Zeitraffer Adliswil MERBAG über 4 Jahre | 2160p | 191 | 96 | entrenamiento |
| `IEtIzcHoMOw` | Construction Camera for Time-Lapse | 2160p | 124 | 62 | entrenamiento |
| `NLlyuKZKHKo` | Construction Camera Aarau | 2160p | 92 | 46 | entrenamiento |
| `rwyGL9gnLh8` | Time-Lapse SCL Tiger Campus | 2160p | 151 | 76 | entrenamiento |
| `SfQxyGXQ_I0` | Time-Lapse Zurich ETH | 2160p | 142 | 71 | entrenamiento |
| `2qXEZOPxZlg` | Construction Camera Company Swiss | 2160p | 102 | 51 | entrenamiento |
| `oHFGGpv2GM8` | Construction Site Camera for Time-Lapse | 2160p | 126 | 63 | descartado: poca gente |
| `qZEmbu7WaBM` | Construction Camera for Time-Lapse | 2160p | 118 | 59 | entrenamiento |
| `02FPXXYmp6I` | Construction Site Camera | 2160p | 123 | 61 | entrenamiento |
| `HqpU2xb-wXs` | Construction Camera Canon EOS Mobile 4 G | 1080p | 173 | 86 | entrenamiento |
| `F-ocdGvR-f8` | Time-Lapse | 2160p | 148 | 74 | entrenamiento |
| `ovkTck6svQQ` | Construction Camera for Time-Lapse | 1080p | 131 | 66 | descartado: poca gente |
| `H5y1reMnDoE` | Time-Lapse Flaach Brige Construction Camera | 1080p | 58 | 29 | descartado: poca gente |
| `EgGT0mkdsQU` | Construction Camera for Construction | 1080p | 170 | 85 | entrenamiento |

**Partición por video y escena.** Nunca por cuadro: los cuadros de un video van enteros a una sola
partición. Para agrupar por obra solo hay el título; no se miraron encuadres ni fechas.

| Grupo (obra o escena) | Videos | Con qué se agrupó |
|---|---|---|
| Uster, Seerestaurant | `UVmFsIoasJ4` | Título |
| Hospital | `N2Wsw7qDjxQ` | Título |
| Escuela Diessenhofen | `bE9eUhZw_JQ` | Título |
| Adliswil, MERBAG | `v2cCZj7g2bA` | Título |
| Aarau | `NLlyuKZKHKo` | Título |
| SCL Tiger Campus | `rwyGL9gnLh8` | Título |
| ETH Zúrich | `SfQxyGXQ_I0` | Título |
| Puente de Flaach | `H5y1reMnDoE` | Título |
| **Obra desconocida** | `EnFcSvWYhY4`, `IEtIzcHoMOw`, `2qXEZOPxZlg`, `oHFGGpv2GM8`, `qZEmbu7WaBM`, `02FPXXYmp6I`, `HqpU2xb-wXs`, `F-ocdGvR-f8`, `ovkTck6svQQ`, `EgGT0mkdsQU` | **No se sabe.** Sus títulos son genéricos y pueden repetir obra entre sí o con las nombradas. Van juntos como un solo grupo, a una sola partición, hasta mirar un cuadro de cada uno |

Pendiente: confirmar a ojo qué videos del grupo desconocido son la misma obra, y fijar qué
partición (entrenamiento o validación) recibe cada grupo.

**Cómo se etiqueta.** Se pre-marca cada cuadro con epp-v3 y una persona corrige a mano en CVAT. La
`cabeza` se sugiere en las personas sin casco asociado, y el humano la confirma, la mueve o la
borra. Lo que propone el modelo no es verdad hasta que alguien lo revisa, y un cuadro sin corregir
no entra al entrenamiento. Aquí sí se corrigen `cabeza` y `sin_chaleco`, en un proyecto de CVAT aparte; la verdad de prueba (lotes 3 y 4) sigue sin ellas. Detalle en la sección 9 de [`guia-etiquetado.md`](../datos/guia-etiquetado.md).

**Privacidad ([ADR-006](../arquitectura/adr/006-sin-identificacion.md)).** Los videos muestran
personas, y algunos rostros pueden ser visibles. Nada de este lote entra al repositorio: ni los
videos, ni los cuadros, ni los recortes. Todo recorte que se escriba lleva el rostro difuminado
antes. No se identifica a nadie ni se infiere ningún atributo: la `cabeza` es un objeto, no una
persona. Desde la altura de estas cámaras la mayoría de los rostros no deberían ser legibles, pero
no se da por supuesto: se revisa al etiquetar.

**Salvedad de la licencia.** CC BY es lo que declara cada canal en YouTube, y la plataforma no
verifica que quien la marca sea el titular de todo lo que sale en el video (música, logos, personas
filmadas). Es una declaración, no una garantía, y los videos no declaran el consentimiento de las
personas que aparecen. Por eso el uso es académico y los archivos quedan fuera del repositorio,
igual que en el lote 3; sigue aplicando el ADR-006.

## 2.bis Datasets públicos de imágenes — para entrenar (PT-03)

Revisados el **2026-09-22** en la fuente primaria de cada uno (el `LICENSE` del repositorio o la
ficha oficial), no en blogs ni en copias subidas por terceros. Regla: se rechaza `-NC`, `-ND` y
todo lo que **no declare licencia**. Una licencia que puso en Roboflow o Kaggle alguien que no es
el autor **no cuenta**.

### Aceptados

| Dataset | Licencia (dónde se verificó) | Imágenes | Clases útiles | Formato | Nota |
|---|---|---|---|---|---|
| [Hard Hat Workers](https://public.roboflow.com/object-detection/hard-hat-workers) (Roboflow) | **CC0 1.0**, en la página oficial | ~7.041 | casco, cabeza, persona | COCO / YOLO / VOC | **Núcleo** de casco + persona |
| [Construction Site Safety](https://universe.roboflow.com/roboflow-universe-projects/construction-site-safety) (Roboflow Universe Projects) | **CC BY 4.0**, en Roboflow y en la [copia de Kaggle](https://www.kaggle.com/datasets/snehilsanyal/construction-site-safety-image-dataset-roboflow) | 717 | casco / sin casco, **chaleco / sin chaleco**, persona | COCO / YOLO | El único aceptado con chaleco explícito. Exige atribución |
| [SHWD](https://github.com/njvisionpower/Safety-Helmet-Wearing-Dataset) | **MIT**, archivo `LICENSE` del repositorio | 7.581 | casco, cabeza | Pascal VOC | Imágenes de buscadores; las negativas vienen en parte de SCUT-HEAD (aulas): **submuestrear** esa parte |
| [Safety Vests](https://universe.roboflow.com/roboflow-universe-projects/safety-vests) (Roboflow Universe Projects) | **CC BY 4.0**, en el `README.dataset.txt` de la versión 1 (2026-10-15) | 3.897 | chaleco / sin chaleco | COCO / YOLO | Refuerzo de chaleco. Exige atribución. Ver «Uso real» |
| [Hard Hat Detection](https://www.kaggle.com/datasets/andrewmvd/hard-hat-detection) (Kaggle) | **CC0 1.0**, en la ficha de Kaggle | 5.001 | casco, cabeza, persona | Pascal VOC | Refuerzo |
| [Helmet Detection](https://www.kaggle.com/datasets/andrewmvd/helmet-detection) (Kaggle) | **CC0**, en la ficha de Kaggle | 764 | con / sin casco | Pascal VOC | Aporte menor |

> **Confirmación al descargar:** las páginas de Roboflow Universe respondieron 403 a la consulta
> automática, así que la licencia se confirma con lo que trae la descarga. *Construction Site
> Safety* quedó confirmada el 2026-10-01: CC BY 4.0 en el `README.dataset.txt` de la versión 30
> (ver «Uso real»). *Safety Vests* quedó confirmada el 2026-10-15: CC BY 4.0 en el
> `README.dataset.txt` de la versión 1.

### Rechazados

| Dataset | Motivo |
|---|---|
| [SH17](https://github.com/ahmadmughees/SH17dataset) | **-NC**: CC BY-NC-SA 4.0 en GitHub y CC BY-NC 4.0 en [Zenodo](https://zenodo.org/records/12659325). Las dos fuentes no coinciden entre sí, pero ambas son no comerciales |
| [Pictor-PPE](https://github.com/ciber-lab/pictor-ppe) | No declara licencia |
| [CHV](https://github.com/ZijianWang-ZW/PPE_detection) | Los autores no declaran licencia; la que figura en Roboflow la puso un tercero |
| [SHEL5K](https://github.com/MoyoG/SHEL5K) | No declara licencia |
| [GDUT-HWD](https://github.com/wujixiu/helmet-detection) | Dudoso: el Apache-2.0 del repositorio cubre el código, no los datos alojados en Baidu |
| [SODA](https://arxiv.org/abs/2202.09554) | Dudoso: el mejor alineado (19.846 imágenes de obra con casco, chaleco y persona), pero ni el artículo ni un sitio oficial declaran licencia. Solo con confirmación escrita de los autores |
| [Construction-PPE](https://docs.ultralytics.com/datasets/detect/construction-ppe) (Ultralytics) | **AGPL-3.0**, la misma licencia que ADR-002 deja fuera |
| CPPE-5 | Dominio médico: no tiene casco de obra ni chaleco |

### Uso real — 2026-10-01 (`scripts/fuentes.yaml`)

Los datasets se bajan con `scripts/descargar_datasets.py` y se unen con
`scripts/preparar_dataset.py`, todo fuera del repositorio. Cada descarga deja un `ORIGEN.json`
con la versión y el sha256.

| Fuente | Estado | Lo que se verificó al descargar |
|---|---|---|
| Hard Hat Detection (Kaggle) | Descargado el 2026-10-01 | 5000 imágenes `hard_hat_workers*.png`: son las de **Hard Hat Workers**, que por eso no se baja aparte. Categorías `helmet` (18.966), `head` (5.785) y `person` (751, en solo 158 imágenes). Entran `helmet` y `person`; `head` entra como `cabeza` desde epp-v3 (ADR-013) |
| Construction Site Safety (Roboflow) | Descargado el 2026-10-01, **versión 30** (fijada en `fuentes.yaml`) | 717 imágenes, licencia CC BY 4.0 en su `README.dataset.txt`. Trae 25 categorías: entran `Hardhat`, `Safety Vest` y `Person`, y desde epp-v3 también `NO-Hardhat` como `cabeza` y `NO-Safety Vest` como `sin_chaleco` (ADR-013); las otras 20 se descartan a propósito |
| Safety Vests (Roboflow) | Descargado el 2026-10-15, **versión 1**, sha256 del zip `fd553b25cb6d…`, fijada en `fuentes.yaml` | 3.897 imágenes (2.728 / 779 / 390), sin aumento y sin redimensionar; las versiones 2, 3, 5, 8, 9, 13 y 14 traen 9.353 o 14.809 imágenes aumentadas, y la 6 y la 7 están redimensionadas o con clases renombradas. Licencia CC BY 4.0 en su `README.dataset.txt`. Categorías de la v1: `Safety Vest` (6.448 cajas), `NO-Safety Vest` (2.024) y la supercategoría `vest-ppe`; la ficha web muestra otros nombres (`safety_vest`, `no_safety_vest`), y manda lo descargado. Entra `Safety Vest`; `NO-Safety Vest` entra como `sin_chaleco` desde epp-v3 (ADR-013) |

**Personas completadas automáticamente.** Una persona sin caja le enseña al modelo que es
fondo. En las fuentes que no marcan a todas las personas, el RF-DETR Medium preentrenado en
COCO (Apache-2.0, umbral 0,6) propone las que faltan, y se agregan con `"automatica": true` en
el COCO de salida. Así se pueden auditar y contar por separado. El 2026-10-01 se revisaron a
ojo 6 imágenes dibujadas, de una corrida de 200 de Hard Hat Detection: cajas de cuerpo
entero, sin duplicar las que ya venían. Es una muestra, no una auditoría.

**Cuadros del mismo video.** Roboflow parte Construction Site Safety por cuadro, y la revisión
independiente encontró cuadros del mismo video en entrenamiento y en prueba. El dHash no los
detecta: quedan a más de 14 bits. `fuentes.yaml` declara patrones que reconocen el video en el
nombre del archivo (159 imágenes `*_mp4-N` y `*_MOV-N`), y cada video va entero a una sola
partición. Las 192 `youtube-N` no dicen de qué video vienen y van como un solo grupo.
La validación y la prueba públicas sirven para elegir el checkpoint; la medición que se
reporta es sobre el video de prueba.

**Limitación conocida del chaleco.** En la v1, solo Construction Site Safety marcaba chaleco, y en
las demás fuentes un chaleco visible sin caja contaba como fondo. Desde el #37, el modelo EPP
completa casco y chaleco en las fuentes que no los marcan siempre, con `"automatica": true`.

**Safety Vests, revisado el 2026-10-15.** La caja de `Safety Vest` va sobre la prenda, como pide
la guía de etiquetado: la proporción alto/ancho mediana es 1,32, igual que el chaleco de
Construction Site Safety (1,27) y lejos de la persona (1,79); se confirmó a ojo en una muestra de
16 imágenes. Trae dos problemas:

| Problema | Tamaño | Qué se hace |
|---|---|---|
| Overoles y trajes completos marcados como `Safety Vest` | En una muestra de 24 de las 403 cajas con alto/ancho > 2,5, un tercio; el resto eran chalecos de perfil o tapados. También aparecen entre 2,0 y 2,5 | **Nada.** Un corte por forma bota chalecos de perfil, que son los que ve una cámara de obra, y deja pasar overoles. Queda como ruido de etiqueta, del orden del 2 % de las cajas |
| Los cascos no tienen caja: un casco visible enseñaría que es fondo | Todo el dataset | El modelo EPP (`--pesos-epp` de `preparar_dataset.py`) completa casco y chaleco donde la fuente no los marca siempre, como el detector COCO con las personas (#37) |

También trae fotos de catálogo con maniquí; se dejan, porque enseñan la prenda. Los nombres de
archivo no muestran cuadros de video (uno solo dice `mp4`), así que no se declaran `grupos`.

**Lo que se usó en la v1:** **Hard Hat Detection + Construction Site Safety**, como dice la tabla
de arriba. Reemplaza a la decisión propuesta del 2026-09-22 (Hard Hat Workers + Construction Site
Safety + SHWD): Hard Hat Detection ya trae las imágenes de Hard Hat Workers. SHWD, *Safety Vests*
y Helmet Detection quedan para la segunda ronda (#37), si falta volumen de casco o de chaleco.
Las atribuciones de los CC BY van en el README del repositorio y en el informe final.

**epp-v3, 2026-10-26: evidencia positiva (ADR-013).** Las categorías de cabeza sin casco y de
persona sin chaleco, que hasta la v2 se descartaban, se mapean a `cabeza` y `sin_chaleco`. Antes
de mapearlas se midió cuánto solapan con el EPP de la misma imagen: `head` 4 de 5.785 cajas,
`NO-Hardhat` ninguna de 402 y `NO-Safety Vest` 3 de 2.024 (Safety Vests), así que no son cascos ni
chalecos mal etiquetados. Conteo del dataset armado (`resumen.json` de epp-v3):

| Partición | Imágenes | `persona` | `casco` | `chaleco` | `cabeza` | `sin_chaleco` |
|---|---|---|---|---|---|---|
| Entrenamiento | 6.765 | 20.435 | 18.597 | 4.346 | 4.747 | 1.759 |
| Validación | 1.239 | 3.669 | 3.032 | 1.182 | 701 | 404 |
| Prueba | 957 | 3.007 | 2.507 | 709 | 716 | 309 |

Etiquetado parcial conocido: Hard Hat Detection no marca `sin_chaleco` y Safety Vests no marca
`cabeza`, y nada las completa (`completar_clases` no completa clases de evidencia). Una persona
sin chaleco de Hard Hat Detection enseña que eso es fondo. Se entrena una vez tal cual y se mide
sobre el video de prueba antes de corregirlo (#31).

## 3. El video propio

Es el activo insustituible del proyecto. Protocolo mínimo:

| Punto | Criterio |
|---|---|
| Duración | 20-30 min continuos, no clips sueltos — hacen falta tracks largos |
| Cámara | **Fija**, en trípode. Una cámara que se mueve invalida las zonas ([V8](06-verificaciones-criticas.md)) |
| Encuadre | A la distancia que resulte de la tabla de V2, no a la que sea cómoda |
| Contenido | Personas con y sin casco, con y sin chaleco, entrando y saliendo de zona |
| Registro | Anotar distancia cámara-sujeto, altura de montaje, resolución y fps reales |

**Autorización — dos papeles distintos, los dos necesarios:**

1. **De la empresa:** autorización escrita para grabar en la obra, con fecha y alcance.
2. **De las personas grabadas:** consentimiento informado, por escrito, que diga uso académico,
   plazo de conservación y derecho a retirarse.

Ambos se guardan **fuera del repositorio** —`.gitignore` bloquea video, pesos y datos
personales— y en el repositorio queda solo la constancia de que existen.

Sigue aplicando el [ADR-006](../arquitectura/adr/006-sin-identificacion.md): rostro difuminado
antes de escribir cualquier recorte, `track_id` efímeros, sin inferencia de atributos.

**Lo que este material *no* dispara:** el trámite de cinco semanas del Reglamento Interno. Ese
plazo rige para *instalar vigilancia permanente*, no para una grabación puntual y consentida con
fines académicos. Si el proyecto llegara a operar de forma continua en la obra, el trámite
vuelve — y hay que arrancarlo con cinco semanas de anticipación.

## 4. Qué queda por hacer

| # | Tarea | Cuándo | Estado |
|---|---|---|---|
| 1 | **Conseguir más video largo y de cámara fija** — hay 1,8 min de los 20-30 | **S5** | 🟢 Reemplazado por el video de YouTube (decisión del 2026-10-01) |
| 2 | Grabar los 20-30 min con el protocolo de arriba (#10) | S5 | ⚪ No se hará (decisión del 2026-10-01) |
| 3 | Recortar los verticales a 16:9 o dejarlos fuera del conjunto de prueba | S5 | 🟠 Excepción, decisión de Edgar del 2026-10-17: el lote 4 es vertical y queda en prueba como **medición aparte**, que nunca se suma a la cifra del lote 3. Recortarlo a 16:9 cortaría a las personas, que llenan el alto del cuadro |
| 4 | Conseguir los dos papeles de autorización antes de grabar | Antes de grabar | 🟢 Lote 4: consentimiento y permiso declarados por Edgar el 2026-10-17; los papeles quedan fuera del repositorio |
| 5 | Repetir la medición de píxeles sobre el video propio | Tras grabar | 🟠 |
| 6 | Anotar cada lote nuevo en el inventario, con el script | Continuo | 🟡 |
