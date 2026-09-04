# Manifiesto de datos — origen, licencia y uso

> Existe por coherencia. Descartamos Ultralytics YOLO porque su AGPL alcanza a los pesos propios
> ([ADR-002](../arquitectura/adr/002-detector-y-licencias.md)) y hay un trabajo de CI que falla si
> reaparece en el *lockfile*. Sería absurdo tener rigor quirúrgico con el código y ninguno con los
> datos: un dataset no comercial contamina los pesos entrenados exactamente igual.

**La regla: ningún dato entra al entrenamiento ni a la evaluación sin una fila en este
documento.** Si no se pudo determinar la licencia, la respuesta es *no*, no *probablemente*.

## 1. Qué licencias se aceptan

| Veredicto | Licencias | Razón |
|---|---|---|
| ✅ Se acepta | CC0, CC BY 4.0, Apache-2.0, MIT, BSD | Permiten uso y obra derivada; basta atribuir |
| ⚠️ Caso a caso | CC BY-SA | Contagio posible sobre el dataset derivado, no sobre los pesos. Se evalúa antes de usar |
| ❌ Se rechaza | CC BY-NC (y cualquier `-NC`), CC ND, "solo investigación" | El capstone se presenta como producto; un uso comercial futuro quedaría bloqueado |
| ❌ Se rechaza | **Sin licencia declarada** | Sin licencia no hay permiso. El silencio no es autorización |

Nota sobre los agregadores tipo Roboflow Universe: la licencia que muestra la ficha **no siempre
es la del material original**. Se verifica contra la fuente primaria, no contra la tarjeta.

## 2. La división que manda

Sale del [ADR-011](../arquitectura/adr/011-dominio-configurable.md) y no se negocia:

| | Origen | Tipo | Para qué |
|---|---|---|---|
| **Entrenamiento** | Datasets públicos | Imágenes | Preentrenar el detector de persona / casco / chaleco |
| **Prueba y demostración** | Grabación propia en obra | **Video** | Conjunto de prueba, tracks, eventos, defensa de S15 |

**Por qué importa la columna "tipo":** un dataset de imágenes sueltas no tiene tiempo. No produce
tracks, no permite reglas en segundos, no puede correr
`test_la_regla_en_segundos_es_invariante_a_la_cadencia` y no evalúa un solo evento. Es material de
entrenamiento y **jamás** conjunto de prueba. Confundir las dos cosas es el error que dejaría el
proyecto sin nada que defender.

## 3. Inventario

Se llena a medida que se verifica cada fuente. **Pendiente: ninguna fuente verificada aún.**

| Fuente | Tipo | Licencia | Verificada contra | Uso | Estado |
|---|---|---|---|---|---|
| *(pendiente)* | | | | | |

Campos obligatorios de cada fila: URL de la fuente primaria · fecha de descarga · número de
imágenes o minutos · clases presentes · quién verificó la licencia.

## 4. El video propio

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

## 5. Qué queda por hacer

| # | Tarea | Cuándo |
|---|---|---|
| 1 | Verificar licencia de las fuentes candidatas y llenar el inventario | Antes de la primera descarga |
| 2 | Conseguir los dos papeles de autorización | Antes de grabar |
| 3 | Grabar los 20-30 min con el protocolo de arriba | S5 |
| 4 | Evaluar si el manifiesto merece un trabajo de CI, como el de licencias de código | S8 |
