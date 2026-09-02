# Bitácora · 2 de septiembre de 2026 — Definición técnica de Guardián EPP

> Sesión de arquitectura. Se eligió la propuesta, se investigaron doce frentes, se tomaron las
> decisiones de fondo y se dejó el repositorio listo para desarrollar.

## 1. Decisión de proyecto

De las tres propuestas sobre la mesa, se elige **B · Guardián EPP** (uso de EPP y condiciones
inseguras sobre video de faena minera). Quedan descartadas FlujoVial y CheckAuto.

## 2. Cómo se llegó a las decisiones

Se investigaron doce frentes en paralelo, cada uno con búsqueda web y lectura de fuentes
primarias: proyectos open source de EPP · datasets públicos · estado del arte 2026 en detectores,
seguidores y VLM · arquitectura de grabado a vivo · productos comerciales del rubro · marco legal
chileno · canales de alerta y fatiga de alarmas · métricas y plan de pruebas · repositorio y CI ·
diseño de interfaz · por qué fracasan estos proyectos · y un **crítico adversarial** que buscó lo
que faltaba.

El crítico fue el que más valor aportó: encontró **cinco huecos que invalidan supuestos** y
**once contradicciones** entre los frentes. Están recogidos en
[`06-verificaciones-criticas.md`](../producto/06-verificaciones-criticas.md).

## 3. Decisiones tomadas

| # | Decisión | Documento |
|---|---|---|
| 1 | Dos etapas: el detector decide, el VLM describe | [ADR-001](../arquitectura/adr/001-dos-etapas.md) |
| 2 | **RF-DETR en vez de Ultralytics YOLO** — la licencia AGPL alcanza a los pesos propios | [ADR-002](../arquitectura/adr/002-detector-y-licencias.md) |
| 3 | **FastAPI + React en vez de Django + HTMX** — revierte la propuesta inicial | [ADR-003](../arquitectura/adr/003-fastapi-y-react.md) |
| 4 | El evento es la unidad; se persisten las detecciones crudas | [ADR-004](../arquitectura/adr/004-el-evento-es-la-unidad.md) |
| 5 | Puerto `FrameSource` y reloj de captura | [ADR-005](../arquitectura/adr/005-fuente-y-reloj.md) |
| 6 | El sistema no identifica personas ni infiere atributos | [ADR-006](../arquitectura/adr/006-sin-identificacion.md) |
| 7 | Monorepo `uv` con cuatro paquetes | [ADR-007](../arquitectura/adr/007-monorepo-uv.md) |
| 8 | Alertas a dos velocidades, con presupuesto de alertas | [ADR-008](../arquitectura/adr/008-alertas-dos-velocidades.md) |
| 9 | Pipeline propio, copiando las ideas de Frigate | [ADR-009](../arquitectura/adr/009-pipeline-propio.md) |
| 10 | Cómputo partido: nube para lo público, local para la faena | [ADR-010](../arquitectura/adr/010-computo-partido.md) |

### El cambio de rumbo más importante

**Se abandona Django + HTMX en favor de FastAPI + React.** El criterio no es técnico sino
organizacional: con plantillas dentro del backend, los dos compañeros de frontend no pueden
avanzar hasta que exista el modelo. Con un contrato OpenAPI congelado y un servidor simulado,
construyen desde la S6 sin esperar a nadie.

### El descubrimiento que más dinero ahorra

**Ultralytics YOLO es AGPL-3.0 y su licenciante sostiene que la licencia alcanza a los pesos que
uno mismo entrena.** El paquete cómodo para los seguidores (`boxmot`) también es AGPL, y una de
las alternativas que los agregadores publicitan como Apache tiene en realidad licencia
propietaria no comercial. Descubrirlo en la S15 habría significado reescribir el backend.

Ya hay un trabajo de CI que falla si alguna de esas dependencias aparece en el *lockfile*.

## 4. Contradicciones resueltas

| Contradicción | Resolución |
|---|---|
| ¿Qué dataset para preentrenar? | **CCTV industrial real**, no el dataset de 17 clases que dos fuentes recomendaban: tiene menos de mil instancias de casco |
| ¿Pipeline propio o envolver Frigate? | **Propio**, copiando sus ideas. El valor evaluable está en el sistema envuelto, que Frigate no aporta |
| ¿El VLM describe o filtra? | **Describe.** El filtrado adversarial entra como experimento medido en la S13, nunca como supresor automático |
| ¿2 fps o 5 fps? | **5 fps.** A 2 fps una persona se desplaza más de un ancho de caja y el seguidor fragmenta los tracks |
| ¿Los compañeros corren el pipeline o usan simuladores? | **Simuladores.** No se instala CUDA en máquinas de 8 GB sin GPU |
| ¿Nube gratuita o privacidad? | **Ambas, partidas**: nube solo con datasets públicos, faena solo local |
| ¿Plazo de 72 h para notificar brechas? | **No existe en la ley chilena.** Es del reglamento europeo. Purgado del informe |

## 5. La decisión sobre el género

El cliente pidió desagregar por género. **No se infiere desde la imagen**, y la negativa se
sostiene en tres frentes independientes: legal (es dato sensible taxativo y el cliente ya está
obligado a mantener registros desde recursos humanos, así que la inferencia no es *necesaria*),
técnico (con casco y antiparras el modelo discriminaría por estatura; con ~15 % de dotación
femenina, un clasificador del 95 % produce en esa clase casi tantos falsos positivos como
aciertos) y ético (la evidencia sobre error desigual por sexo y tono de piel es concluyente).

**La alternativa que sí entrega lo que el cliente busca:** cruzar hallazgos agregados por área,
turno y franja contra la dotación administrativa, con supresión de celdas con n < 5.

Se presenta como decisión de diseño, no como limitación. Y nunca como negativa seca: la
alternativa va en la misma reunión.

## 6. Lo que quedó construido

- Estructura de las tres fases con los **nombres de archivo textuales** que exige el docente, y
  la tercera carpeta de la Fase 2 (*Evidencias Proyecto*) que faltaba.
- Gobernanza del repositorio: 24 etiquetas, plantillas de issue y PR, CODEOWNERS por área,
  `.gitignore` que bloquea video, pesos y datos personales.
- Espacio de trabajo `uv` con cuatro paquetes y `gepp-core` **implementado y probado**:
  geometría, asociación EPP-persona y el agregador de eventos. **24 pruebas, 96,7 % de cobertura,
  mypy estricto.**
- CI con filtros de ruta, matriz de versiones, y el trabajo de higiene de licencias.
- Once documentos de arquitectura y producto.
- El prompt listo para generar el diseño de la interfaz.

### La prueba de la que más conviene hablar en la defensa

`test_la_regla_en_segundos_es_invariante_a_la_cadencia`: el mismo incumplimiento, muestreado a 2,
5, 10 y 15 fps, produce el mismo hallazgo. Es la barrera que impide que la migración a video en
vivo cambie en silencio el significado de todas las reglas ya validadas con el cliente.

## 7. Qué falta, en orden

| Prioridad | Qué | Quién | Cuándo |
|---|---|---|---|
| 🔴 | **V1**: confirmar por escrito el acceso al video de faena | Edgar | **S3** |
| 🔴 | **V2**: tabla de píxeles sobre objetivo por cámara | Edgar | **S3** |
| 🔴 | Presentar estas decisiones al equipo y validarlas | Equipo | Próxima reunión |
| 🟠 | Generar el diseño de la interfaz con el prompt preparado | Frontend | S3 |
| 🟠 | Sumar las horas de Edgar contra las 11 semanas | Edgar | S4 |
| 🟠 | Pedir la matriz de EPP por área del reglamento de la faena | Edgar | S5 |
| 🟠 | Congelar el contrato OpenAPI y levantar el servidor simulado | Edgar | S5 |
| 🟡 | Medir el presupuesto de VRAM en la máquina con GPU | Edgar | S6 |
| 🟡 | Entrevistar a un prevencionista (45 min) | Equipo | S5 |
| 🟡 | Decidir la licencia del repositorio | Equipo | Antes de S15 |
| 🟡 | Competencias del perfil de egreso para la Guía 1.5 | Equipo | S4 |

## 8. Lo que el crítico dejó dicho, y conviene no olvidar

> *"El corpus es fuerte donde es fácil investigar y está vacío donde el proyecto se juega. Nadie
> verificó si hay video de faena. Nadie calculó cuántos píxeles tiene un casco a 30 metros, que es
> lo único capaz de invalidar el caso de uso y cuesta veinte minutos. Nadie definió con qué
> métrica se mide un evento, que es con lo que se defiende el capstone. Y el riesgo grave que
> nadie nombró es el falso negativo: un sistema de seguridad que la faena adopte como cobertura y
> que falle en silencio crea un riesgo de personas que hoy no existe."*
