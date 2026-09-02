# Diseño de interfaz

> Documento de referencia para el equipo de frontend. La conclusión de fondo, y conviene
> interiorizarla antes de dibujar nada:

> **Esto no es un dashboard. Es una bandeja de triage.**

El usuario principal —el prevencionista— no entra a mirar gráficos: entra a revisar hallazgos
pendientes, decidir cuáles son reales y qué hacer con ellos. El panel de indicadores es la
segunda pantalla en importancia, no la primera. Los análogos correctos no son Power BI ni
Google Analytics: son **Sentry** (bandeja de incidencias con estados y prioridad), **Linear
Triage** (aceptar/descartar con una tecla) y **Frigate Review**.

## Las pantallas, por prioridad

| # | Pantalla | Ruta | Prioridad | Por qué |
|---|---|---|---|---|
| 1 | **Bandeja de hallazgos** | `/hallazgos` | P0 | El corazón del producto |
| 2 | **Visor de evidencia** | panel lateral | P0 | Donde se decide si el hallazgo es real |
| 3 | **Ingesta / videos** | `/videos` | P0 | Hace visible el pipeline que el evaluador no puede ver |
| 4 | **Panel general** | `/` | P0 | La foto para la jefatura |
| 5 | **Editor de reglas** | `/reglas` | P0 | El diferenciador técnico |
| 6 | **Reportes** | `/reportes` | P1 | La analítica que pidió el cliente |
| 7 | **Zonas y cámaras** | `/camaras` | P1 | Dibujar polígonos sobre el cuadro de referencia |
| 8 | **Plano de faena** | `/mapa` | P1 | Lo que un gerente entiende en 3 segundos |
| 9 | **Notificaciones y silencios** | `/notificaciones` | P1 | Sin esto, fatiga de alertas en la primera semana |
| 10 | **Administración y auditoría** | `/admin` | P2 | Roles y registro inmutable |

> Si algo se cae del alcance, que sea el **mapa** — nunca la bandeja ni el editor de reglas,
> que son las dos pantallas que demuestran que esto no es una demostración de detección de
> objetos.

## Detalle de las tres que definen el producto

### Bandeja de hallazgos

Tabla densa y virtualizada, con pestañas de triage: **Por revisar** (por defecto) · Confirmados ·
Descartados · Reincidentes · Todos.

Columnas: severidad (icono + palabra) · tipo de incumplimiento como etiquetas · área y zona ·
origen · inicio (hora en tipografía monoespaciada) · duración · cuadros confirmados · confianza
(barra fina) · miniatura 64×36 · estado · asignado a.

- Fila de 40 px, sin cebra, separador de 1 px.
- Selección múltiple con acciones en lote en una barra flotante inferior.
- Atajos: `j`/`k` navegar · `Enter` abrir · `c` confirmar · `x` falso positivo · `d` duplicado ·
  `h` posponer · `a` asignar · `/` buscar.
- Orden por defecto **"Recomendado"** = severidad × recurrencia × recencia, no solo por fecha.
- **Todos los filtros viven en la URL.** Sin eso no hay enlace compartible, y compartir el caso
  por mensaje al supervisor es exactamente cómo se usa esto en faena.

### Visor de evidencia

**Panel deslizante desde la derecha (60 % del ancho), no una página nueva.** El prevencionista
tiene que poder triar 30 hallazgos sin perder su lugar en la lista.

De arriba a abajo: recorte de 5–10 s en bucle, con interruptores para las cajas y para el
difuminado · tira de miniaturas de los cuadros confirmados · mini línea de tiempo (primera
detección → umbral alcanzado → fin) · bloque del modelo de lenguaje visual (título grande,
descripción, confianza como dato secundario) · **bloque "por qué se disparó"**: nombre y versión
de la regla, zona, EPP exigido, umbral configurado y valores observados · metadatos técnicos
plegados (archivo, hash, desplazamiento, cadencia, versión del modelo) · barra de acciones fija.

El "por qué se disparó" es lo que hace auditable el sistema. No es un extra.

### Editor de reglas

Maestro-detalle. La función que lo convierte en producto: **"Simular sobre los últimos 30 días"**,
que muestra cuántos hallazgos habría generado la regla y una muestra de miniaturas, **sin
publicarla**. Es posible porque se persisten las detecciones crudas (ADR-004).

Cada cambio crea una versión nueva con autor y fecha, y el hallazgo guarda la versión que lo
disparó.

## Estilo visual: minimalista y denso

### Color

Una escala de grises de 10 pasos con rol por paso. **Un solo acento de marca** para lo
interactivo. Todo el resto del color queda reservado a la semántica de severidad. Los colores se
definen como tokens de rol (`--sev-critica-fondo`, `--sev-critica-borde`), nunca un hexadecimal
dentro de un componente.

### Severidad: triple codificación, no es una preferencia estética

Codificar la severidad solo por color es un fallo de accesibilidad catalogado, y en una faena
—población mayoritariamente masculina— cerca del 8 % de los usuarios no lo distinguirá.

| Nivel | Forma | Color | Palabra |
|---|---|---|---|
| Crítica | ◆ rombo relleno | `#D55E00` bermellón | "Crítica" |
| Alta | ▲ triángulo | `#E69F00` naranja | "Alta" |
| Media | ● círculo | `#0072B2` azul | "Media" |
| Baja | ○ anillo hueco | gris 600 | "Baja" |
| Conforme | ✓ | `#009E73` verde azulado | "OK" |

Paleta Okabe-Ito: es segura para daltonismo y escalona **luminancia** además de tono. Prohibido
el par rojo/verde como única distinción. **Prueba de aceptación:** si al desaturar una captura no
se distinguen los niveles, el diseño falló.

### Densidad y tipografía

Espaciado en múltiplos de 4 px · filas de 40 px · relleno de celda 8×12 · radio 6 px · bordes de
1 px en vez de sombras (sombra solo en superposiciones).

Escala tipográfica corta y fija: **11** (etiquetas en mayúscula) / **12** (metadatos) / **13**
(cuerpo de tabla) / **14** (cuerpo) / **20** (título de sección) / **28** (número de indicador).
Máximo tres pesos. Monoespaciada con `font-variant-numeric: tabular-nums` **obligatoria** en
horas, duraciones, hashes, identificadores y toda columna numérica.

> La densidad no viene de apretar: viene de que casi todo mide 13 px y se diferencia por peso y
> color de texto, no por tamaño.

### Modo oscuro

Oscuro por defecto en operación (bandeja, visor, mapa); claro por defecto en reportes y
administración; conmutador que persiste. Nunca negro puro: fondo `#0B0D10`, superficie `#14171A`,
borde `#26292E`. Acentos con croma reducido respecto del tema claro.

### Gráficos

Solo barras horizontales, líneas, minigráficos y mapas de calor. **Prohibidos**: torta, dona, 3D,
apilados y arcoíris. Máximo 5 series. Eje Y desde cero en barras. Etiqueta directa sobre la serie
cuando quepa, en vez de leyenda separada.

## Errores que hay que evitar

| Error | Por qué duele |
|---|---|
| El "muro de gráficos": 12 widgets que nadie mira | Si un gráfico no lleva a una acción, se borra |
| Colorear la fila entera según severidad | Destruye la legibilidad; 40 filas críticas se ven como un bloque rojo sin jerarquía |
| Reproducir el video completo en el visor | Mata el rendimiento y contradice la arquitectura |
| Bandeja sin estados de triage | Sin "confirmado / falso positivo" no hay forma de medir la precisión del modelo — y el falso positivo marcado por un humano es el dato más valioso que produce el sistema |
| Confundir severidad con confianza | Son dos ejes independientes. Columnas separadas, siempre |
| Filtros solo en el estado de React | Sin filtros en la URL no hay enlace compartible |
| Paginación clásica sobre decenas de miles de filas | Cursor y virtualización |
| Diseñar el panel bonito y no la pantalla de ingesta | En un capstone con video grabado, la cola de procesamiento es la pantalla que demuestra que el pipeline existe |
