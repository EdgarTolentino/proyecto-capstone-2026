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

## 3. Atributos

| Clase | Atributo | Valores | Para qué |
|---|---|---|---|
| `casco` | `puesto` | `si` · `no` | Experimento V6 de la S8: ¿la heurística de franjas basta o hace falta pose? |
| `chaleco` | `puesto` | `si` · `no` | Igual que el casco |
| `persona` | `ocluida` | `no` · `parcial` · `mayor` | Separar los errores del modelo de los casos imposibles |

## 4. Reglas de la caja

1. **Ajustada al borde visible**, sin margen. Si una parte está tapada, la caja cubre solo lo que
   se ve; no se adivina lo que hay detrás.
2. **Tamaño mínimo: 10 píxeles de lado** en la imagen original. Lo más chico se deja sin caja y
   la imagen se marca con la etiqueta de imagen `tiene_pequenos`. V2 (#3) mide que bajo ~20 px
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
| Persona a más de ~30 m, con el casco bajo 10 px | `persona` sí; el casco no. Etiqueta de imagen `tiene_pequenos` |
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

## 7. Casos decididos en sesión

Se completa en cada sesión: fecha, caso, decisión y quiénes estaban.

| Fecha | Caso | Decisión | Presentes |
|---|---|---|---|
| | | | |

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
