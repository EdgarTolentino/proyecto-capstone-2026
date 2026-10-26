# ADR-013 — El incumplimiento se decide por evidencia positiva, no por ausencia

**Estado:** propuesta · **Fecha:** 2026-10-26 · Se acepta o se descarta con la meta fijada en
[#31](https://github.com/EdgarTolentino/proyecto-capstone-2026/issues/31) antes de entrenar.

## Contexto

Hasta hoy la regla razona por **ausencia**: «veo a una persona y no le veo casco, entonces no lo
lleva» (`gepp_core.asociacion.epp_faltante`: lo exigido menos lo puesto). Eso funciona si el
detector ve casi todos los cascos. En el CCTV de obra no los ve:

- El recall de casco por cuadro dentro del foso, con mosaico, es **0,222** (small v2, #31). El
  de chaleco, cercano a 0.
- Con el trabajador real, con mosaico en la GPU y sobre `yt_GPCHfE_min020.mp4`, en **122 de 157**
  hallazgos de casco comparables con la verdad la persona sí tiene casco (#203). Una persona con
  casco pasa varios cuadros seguidos sin que el modelo lo vea, la racha supera
  `confirmacion_segundos` y sale un hallazgo.
- Un modelo más grande (#31) y más fotos de internet (#31, v2) no subieron ese recall.

Por ausencia, cada casco que el modelo no ve es una alerta. Mientras el recall no se acerque a
1, el sistema alerta sobre todo a quien cumple.

## Decisión

**1. La regla tiene dos modos.** `ausencia` es el actual. En `evidencia`, un EPP exigido falta
**solo si** el detector ve la falta: una detección de una clase de evidencia, con confianza
mayor o igual a `confianza_minima`, cuyo centro cae en la franja de la persona donde iría ese
EPP, **y** ese EPP no está puesto.

| Clase de evidencia (`ClaseDetectada`) | Es evidencia de que falta | Franja |
|---|---|---|
| `cabeza` (una cabeza sin casco) | `casco` | La del casco |
| `sin_chaleco` (una persona sin chaleco) | `chaleco` | La del chaleco |

Un EPP sin clase de evidencia (lentes, guantes…) se sigue evaluando por ausencia.

**2. El modo es de la faena**, no de cada regla. Se declara en el perfil
(`faena.modo_incumplimiento`, ADR-011) y se guarda en `faena`. El trabajador y el recálculo sin
GPU lo leen del mismo lugar (`reglas.en_fuente`), así que un video se evalúa igual en los dos. No
se expone en la API: el contrato está congelado.

**3. Las clases de evidencia solo las aprende el modelo.** Salen de datasets públicos que ya las
traen y que tienen su fila en `07-datasets.md`:

- Hard Hat Detection (CC0): `head`;
- Safety Vests v1 (CC BY 4.0): `NO-Safety Vest`;
- Construction Site Safety (CC BY 4.0): `NO-Hardhat` y `NO-Safety Vest`.

**La verdad que etiqueta el equipo en CVAT no cambia:** sigue la guía §2, «se etiqueta el
objeto, no el cumplimiento». Así, las mediciones de #31 y #203 siguen siendo comparables, y la
cifra que decide este ADR sale del cruce de hallazgos con esa misma verdad.

**4. El perfil de construcción queda en `ausencia`** hasta medir. Si se cumple la meta de #31,
pasa a `evidencia` en un PR aparte, y este ADR pasa a «aceptada».

## Por qué

**Porque una alerta tiene que apoyarse en algo que se vio.** Por ausencia, la alerta se apoya en
lo que el modelo no vio, y eso mezcla «no hay casco» con «no lo detecté». La evidencia positiva
separa las dos cosas: si el modelo no está seguro, no alerta.

**Porque el error se vuelve del lado tolerable.** Por evidencia, un modelo débil pierde
incumplimientos (falsos negativos) en vez de inventarlos. Para una herramienta de apoyo al
prevencionista es el error menos dañino: una alerta falsa le quita confianza al sistema entero
(ADR-008, presupuesto de 6 avisos por turno), y una perdida queda para la ronda humana.

**Porque los datos ya existen.** No hay que etiquetar nada nuevo: las tres fuentes están
descargadas y tienen licencia verificada.

## Consecuencias

| Cambia | De | A |
|---|---|---|
| Clases del modelo | `persona`, `casco`, `chaleco` | Además `cabeza` y `sin_chaleco` |
| Cuándo falta un EPP | No se ve puesto | Se ve la falta, y no se ve puesto (modo `evidencia`) |
| Error dominante con un modelo débil | Falsas alarmas | Incumplimientos perdidos |

**Lo que no cambia:** las reglas siguen en segundos (ADR-005), el detector y las reglas deciden
(ADR-001), el evento es la unidad (ADR-004) y no se identifica a nadie (ADR-006). Una cabeza sin
casco es un objeto, no una persona identificada: no se infiere quién es ni ningún atributo suyo.

## El límite, dicho antes de que lo pregunten

- **El etiquetado parcial.** Una fuente que no marca `cabeza` le enseña al modelo que esas
  cabezas son fondo. Se mide al preparar el dataset y se resuelve antes de entrenar.
- **La clase de evidencia en nuestra verdad no tiene caja.** El nivel 1 no puede medir `cabeza`
  ni `sin_chaleco` contra CVAT. Lo que decide es el cruce de hallazgos de #203, que mide
  justamente lo que importa: cuántas alertas son falsas.
- **Si no se cumple la meta, no hay segundo intento.** Queda la regla por ausencia, el informe lo
  dice con sus cifras y este ADR pasa a «descartada».
