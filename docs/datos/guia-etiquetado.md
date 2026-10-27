# Guía de etiquetado — dataset v0.1

> PT-03 (#26). Se escribe **antes** de abrir CVAT y la revisan Miguel y Lian antes de la primera
> sesión. Si un caso no está aquí, se anota en la sección 7 y se decide entre los tres; nadie lo
> resuelve solo en el momento.

## 1. Para qué sirve esta guía

El modelo aprende lo que las etiquetas dicen, incluidos sus errores. Si una persona marca el
chaleco abierto y otra no, el modelo aprende las dos cosas a la vez y la métrica se cae sin que
nadie sepa por qué. Por eso el 10 % de cada lote lo etiquetan dos personas y se mide el acuerdo
(sección 6). Según `02-plan-de-evaluacion.md`, si los humanos coinciden en 0,75, ningún modelo
puede reportar 0,95 con honestidad.

## 2. Las tres clases de la v1

Son las de `ClaseDetectada` en `gepp-core`. Arnés, guantes y lentes quedan fuera de la v1 (V9).

| Clase | Qué es | La caja abarca |
|---|---|---|
| `persona` | Un ser humano real, de cuerpo entero o parcial | Todo lo visible del cuerpo, de la cabeza (o el casco) a los pies |
| `casco` | Casco de seguridad rígido, de cualquier color | Solo el casco, sin la cabeza |
| `chaleco` | Chaleco o prenda reflectante de alta visibilidad | Solo la prenda visible |

**Se etiqueta el objeto, no el cumplimiento.** El casco en la mano también es `casco`. Si está
puesto o no lo decide el sistema al asociar el casco con la franja de la cabeza de la persona
(`gepp_core.asociacion`). Para medir esa asociación, cada casco lleva el atributo `puesto`
(sección 3).

Las clases `cabeza` (cabeza sin casco) y `sin_chaleco` del [ADR-013](../arquitectura/adr/013-incumplimiento-por-evidencia.md)
**no se etiquetan en la verdad de prueba** (lotes 3 y 4, proyecto `guardian-epp-v01`). Esa verdad
sigue marcando el objeto, para que las mediciones sigan siendo comparables. Las aprende el modelo
desde datasets públicos que ya las traen y, desde el 2026-10-27, también desde el lote 5, que se
etiqueta aparte y solo para entrenar (sección 9).

## 3. Atributos

| Clase | Atributo | Valores | Para qué |
|---|---|---|---|
| `casco` | `puesto` | `si` · `no` | Experimento V6 de la S8: ¿la heurística de franjas basta o hace falta pose? |
| `chaleco` | `puesto` | `si` · `no` | Igual que el casco |
| `persona` | `ocluida` | `no` · `parcial` · `mayor` | Separar los errores del modelo de los casos imposibles |

## 4. Reglas de la caja

1. **Ajustada al borde visible**, sin margen. Si una parte está tapada, la caja cubre solo lo que
   se ve; no se adivina lo que hay detrás.
2. **Tamaño mínimo: 10 píxeles de lado** en la imagen original, y **8 píxeles para el casco**
   (decisión del 2026-10-08, sección 7). Lo más chico se deja sin caja y la imagen se marca con
   la etiqueta de imagen `tiene_pequenos`. V2 (#3) mide que bajo ~20 px
   en la entrada del detector no hay nada que aprender.
3. **Una persona, una caja**, aunque la tape otra persona o una máquina.
4. Personas **cortadas por el borde** de la imagen: se etiquetan si se ve al menos la cabeza o
   el torso.

## 5. Casos límite ya resueltos

Salen de la lista de `02-plan-de-evaluacion.md`, "Calidad del dato".

| Caso | Qué se hace |
|---|---|
| Casco colgando del brazo o en la mano | `casco`, `puesto = no` |
| Casco sin barbiquejo, puesto | `casco`, `puesto = si`. El barbiquejo no es de la v1 |
| Gorro de tela, jockey, capucha | **Nada.** No es casco |
| Casco en un perchero, en el suelo o sobre una máquina | `casco`, `puesto = no`. Es un negativo útil: el sistema no debe asociarlo a nadie |
| Chaleco abierto o desabrochado, puesto | `chaleco`, `puesto = si` |
| Chaleco en la mano o colgado | `chaleco`, `puesto = no` |
| Polera o chaqueta naranja **sin** cinta reflectante | **Nada.** Es el negativo que enseña que "chaleco" no es "cualquier cosa naranja" |
| Persona a más de ~30 m, con el casco bajo 8 px | `persona` sí; el casco no. Etiqueta de imagen `tiene_pequenos` |
| Reflejo en un vidrio o espejo | **Nada** |
| Persona en un afiche, letrero o pantalla | **Nada** |
| Maniquí | **Nada** |
| Conos, bidones, extintores, señalética | **Nada**. Si la imagen tiene muchos, etiqueta de imagen `negativo_duro` |
| Persona de espaldas | Se etiqueta igual; el casco se ve por detrás |
| Grupo apretado donde no se distingue quién es quién | Una caja por persona distinguible y etiqueta de imagen `grupo_denso` |

## 6. Cómo se trabaja

**Sesiones de los tres** (PT-04, S6-S8), no etiquetado a solas: las dudas se resuelven en el
momento y quedan escritas en la sección 7.

- **Herramienta:** CVAT autoalojado en la máquina de Edgar (Docker). No se usan plataformas
  gratuitas en la nube: publican el dataset en su catálogo (`00-arquitectura.md` §6.bis).
- **Proyecto CVAT:** `guardian-epp-v01`, con las tres clases y los atributos de la sección 3
  configurados antes de la primera sesión.
- **Exportación:** COCO 1.0. Nunca se edita el JSON a mano.
- **Doble etiquetado:** el 10 % de cada lote, elegido al azar por el script, lo etiquetan dos
  personas sin ver el trabajo de la otra. Se reportan el **kappa de Cohen** (acuerdo en las
  clases) y el **IoU medio** de las cajas emparejadas. Si el kappa baja de 0,7, se para, se
  discuten las diferencias y se agrega el caso a la sección 7 antes de seguir.
- **Revisión:** Edgar audita el 10 % restante de cada lote antes de exportarlo.

**Privacidad** (ADR-006): las imágenes del video propio **no salen de la máquina de CVAT** ni
entran al repositorio. Al repositorio llega solo el manifiesto `datos/lote0.csv`, con archivo,
video, partición y hash perceptual; el hash no permite reconstruir la imagen.

### CVAT en la máquina de Edgar (instalado el 2026-10-01)

| Qué | Dónde |
|---|---|
| CVAT 2.77.0 | `~/tools/cvat`, fuera del repositorio. `docker compose up -d` lo levanta desde esa carpeta, donde están el override y el `.env` |
| Dirección | <http://localhost:8180>. El 8080 lo ocupa otro proyecto: el puerto se cambia en `docker-compose.override.yml`. Miguel y Lian entran por el nombre de Tailscale de la máquina (`CVAT_HOST` en el `.env` de CVAT), no por `localhost` |
| Al abrir Docker Desktop | `traefik` y `cvat_vector` pueden quedar en `Exited (127)`. `traefik` monta el socket de Docker y se reinicia antes de que exista en WSL (`error mounting .../docker.sock ... not a directory`); la causa en `cvat_vector` no quedó registrada. Los dos vuelven con otro `docker compose up -d`, que no borra nada |
| Usuario administrador | `edgar`; la clave está en `~/.config/gepp/cvat.env` (permisos 600, nunca en el repositorio) |
| Proyecto | `guardian-epp-v01`: `persona` (`ocluida`), `casco` y `chaleco` (`puesto`), y la etiqueta de imagen `tiene_pequenos` |
| Tarea | `prueba-youtube-lote0`: los 240 cuadros de `datos/lote0.csv`, en **4 trabajos de 60, uno por tramo**, para repartirlos |

**Pre-etiquetas.** `scripts/preetiquetar.py` corre el modelo con `DetectorMosaico` sobre el foso
y el modelo normal fuera de él, descarta las cajas bajo el mínimo (§4: 10 px, 8 px el casco) y escribe COCO 1.0. Se
importa en la tarea con *Actions → Upload annotations → COCO 1.0*. **Son sugerencias:** se
revisa cada caja, se agrega lo que falta y se fijan los atributos, que el modelo no infiere
(todas llegan con el valor por defecto: `puesto = si`, `ocluida = no`). Corregir una
pre-etiqueta no exime de mirar la imagen entera. Las primeras pre-etiquetas del lote de
prueba traen **71 pares de cajas repetidas** sobre la misma persona o casco: se borra una de
cada par.

## 7. Casos decididos en sesión

Se completa en cada sesión: fecha, caso, decisión y quiénes estaban.

| Fecha | Caso | Decisión | Presentes |
|---|---|---|---|
| 2026-10-08 | Cascos de 8 y 9 px | Se etiquetan; el mínimo del casco baja a 8 px. Persona y chaleco siguen en 10 px | Edgar, Miguel |
| 2026-10-15 | Cascos del doble etiquetado (#112): el mismo casco con cajas de distinto tamaño, y cascos que marcó uno solo | Todo casco visible desde 8 px lleva su caja, aunque la persona ya tenga la suya. La caja va justa al casco, sin la cabeza y sin margen (§2 y §4.1). Chaleco, persona tapada y personas bajo el toldo quedan para la próxima sesión | Edgar |
| 2026-10-22 | Casco levantado sobre la cabeza, con pelo a la vista entre el casco y la frente (lote 4, trabajo 10, cuadro 106) | `casco`, `puesto = no`, porque ya no se apoya en la cabeza: es el mismo criterio del casco en la mano (§5). Si sigue apoyado en la cabeza, aunque la mano lo esté ajustando (cuadro 105), va `puesto = si` | Edgar, Miguel (en #189) |
| 2026-10-22 | Chaleco que se ve solo como una franja, tapado por otra persona, sin que se sepa si está puesto (lote 4, trabajo 10, cuadro 101) | Sin caja. Sigue abierto desde qué porción visible un chaleco parcial sí lleva caja | Edgar, Miguel (en #189) |

## 8. Lote 0 y partición

`scripts/lote0.py` toma un cuadro cada 2 s de los videos propios, descarta los casi duplicados
(dHash, distancia ≤ 6 de 64 bits) y escribe el manifiesto. La partición la decide una persona en
`particion.yaml`, **por video y nunca por cuadro**, con al menos dos cámaras completas y un día
completo en prueba (`02-plan-de-evaluacion.md`). CI verifica el manifiesto en cada empuje: falla si
un video o una escena aparecen en dos particiones.

```bash
uv run python scripts/lote0.py ~/datos/videos ~/datos/lote0 \
    --particion ~/datos/particion.yaml --manifiesto datos/lote0.csv
```

## 9. Lote 5: etiquetado de entrenamiento (2026-10-27)

El lote 5 de [`07-datasets.md`](../producto/07-datasets.md) (video público CC BY de cámaras en
altura) es **solo entrenamiento**. Por eso aquí **sí** se corrigen `cabeza` y `sin_chaleco`, que en
la verdad de prueba (secciones 2 a 8) no se etiquetan. Las dos cosas no se mezclan:

| | Verdad de prueba (lotes 3 y 4) | Entrenamiento del lote 5 |
|---|---|---|
| Proyecto CVAT | `guardian-epp-v01` | **Otro, separado**: `guardian-epp-lote5-entrenamiento` (nombre propuesto; Edgar puede cambiarlo) |
| Clases | `persona`, `casco`, `chaleco` | Esas tres más `cabeza` y `sin_chaleco` |
| Punto de partida | Sin pre-etiquetas (lote 4) | Pre-marcado con epp-v3 |
| Para qué | Medir | Entrenar |

**Por qué un proyecto separado.** La verdad de prueba no debe heredar el pre-marcado: el lote 4
ya se etiqueta «sin pre-etiquetas» para no heredar los errores del modelo que se mide. Y
`guardian-epp-v01` tiene solo las tres clases; importar una `cabeza` ahí falla con
`Label 'cabeza' is not registered`.

**Configuración del proyecto del lote 5.** Lleva **todo lo de `guardian-epp-v01`** más lo nuevo.
Si falta algo, CVAT descarta el atributo o rechaza la etiqueta al importar (por ejemplo
`Label 'tiene_pequenos' is not registered`).

| Qué | Cómo se llama | Origen |
|---|---|---|
| Etiquetas de objeto | `persona`, `casco`, `chaleco` | Las de `guardian-epp-v01` |
| Etiquetas de objeto | `cabeza`, `sin_chaleco` | Nuevas del lote 5 (ADR-013) |
| Atributo `puesto` (`si` · `no`) | En `casco` y en `chaleco` | Sección 3 |
| Atributo `ocluida` (`no` · `parcial` · `mayor`) | En `persona` | Sección 3 |
| Atributo `origen` (`manual` · `sugerida` · `predicha`, por defecto `manual`) | En las cinco etiquetas de objeto. Una caja dibujada a mano queda `manual`, no `sugerida` | Nuevo del lote 5 |
| Etiquetas de imagen | `tiene_pequenos` (sección 4.2), `negativo_duro` y `grupo_denso` (sección 5) | Las que pide la guía. La instalación de CVAT (sección 6) solo registra `tiene_pequenos` en `guardian-epp-v01`; si `negativo_duro` y `grupo_denso` no existen allí, se crean en el proyecto del lote 5 igual |

Las etiquetas hay que crearlas **con** sus atributos: CVAT descarta al importar un atributo que la
etiqueta no declara. `cabeza` y `sin_chaleco` no llevan `puesto` ni `ocluida`.

**Las secciones 4 y 5 valen enteras.** No hay ninguna regla que se deje fuera para el lote 5. Dos
puntos que conviene tener presentes: el mínimo de 10 px (8 px el casco) de la sección 4.2 se mide
en el cuadro original, y en cuadros de cámara en altura habrá muchas personas y cascos bajo ese
mínimo, que se dejan sin caja con `tiene_pequenos`; y el caso de la persona lejana de la sección 5
(`persona` sí, casco no) será frecuente. Ambos se aplican como están.

**Cómo se corrige.**
- La `cabeza` se sugiere en las personas sin casco asociado; quien etiqueta la confirma, la mueve o
  la borra, y agrega las que falten. Misma idea con `sin_chaleco`.
- Las demás reglas de caja (sección 4) y los casos de la sección 5 valen igual.
- Un cuadro sin corregir no entra al entrenamiento.

**Cómo llega el pre-marcado.** (1) `preetiquetar.py --umbral 0.05 --con-evidencia` saca las
predicciones crudas, que no van a CVAT. (2) `premarcar_cabezas.py PRED.coco.json MODELO.clases.json
SALIDA.coco.json` filtra con el umbral de la regla, sugiere las cabezas y escribe `origen` en
`attributes`; esa SALIDA es la que se importa. El paso 2 llega con el PR de `premarcar_cabezas.py`
(rama `feat/premarcar-cabezas`): hasta entonces no existe en `main`.
