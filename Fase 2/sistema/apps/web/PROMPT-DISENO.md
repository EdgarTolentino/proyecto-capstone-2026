# Prompt para generar el diseño

Copiar el bloque completo y pegarlo en **Claude Design** (o pedirle a Claude Code
`/design` con este texto). Está escrito para que salga un diseño usable a la primera:
lleva el contexto, las pantallas, el estilo y datos de ejemplo realistas.

> Consejo: genera **primero solo la bandeja y el visor**. Son las dos pantallas que definen
> el producto. Si esas dos quedan bien, el resto es consecuencia.

---

```
Diseña la interfaz de "Guardián EPP", una plataforma web que detecta automáticamente el
incumplimiento en el uso de Elementos de Protección Personal sobre video de CCTV de una faena
minera chilena, y convierte cada incumplimiento en un hallazgo gestionable.

CONCEPTO CLAVE — léelo antes de decidir nada:
Esto NO es un dashboard de analítica. Es una BANDEJA DE TRIAGE. El usuario principal es un
prevencionista de riesgos que entra a revisar hallazgos pendientes, decidir cuáles son reales y
asignar quién actúa. Los referentes correctos son la bandeja de incidencias de Sentry, el triage
de Linear y la vista de revisión de Frigate NVR — no Power BI ni Google Analytics. El panel de
indicadores es la segunda pantalla en importancia, nunca la primera.

USUARIOS
- Prevencionista de riesgos: tría hallazgos todo el día. Es quien manda en el diseño.
- Supervisor de área: recibe alertas de su zona y las cierra. Entra poco y con prisa.
- Jefatura de seguridad: mira tendencias una vez por semana.
- Administrador: configura zonas, reglas y destinatarios.

PANTALLAS (genera un artboard por cada una)

1. BANDEJA DE HALLAZGOS — la principal
   Tabla densa con pestañas de triage: "Por revisar" (activa) · Confirmados · Descartados ·
   Reincidentes · Todos, cada una con su contador.
   Columnas: severidad (icono con forma + palabra) · tipo de incumplimiento como etiquetas
   ("sin casco", "sin chaleco") · área y zona · cámara de origen · hora de inicio en tipografía
   monoespaciada · duración · cuadros confirmados · confianza como barra fina de 0 a 1 ·
   miniatura del recorte 64×36 · estado · asignado a.
   Filas de 40 px, sin cebra, separador de 1 px, cabecera pegajosa, checkbox de selección
   múltiple. Al seleccionar filas aparece una barra flotante inferior con acciones en lote.
   Barra de filtros horizontal de 44 px sobre la tabla: rango de fechas, área, severidad, tipo de
   EPP, estado, cámara. Muestra los atajos de teclado en la esquina (j/k navegar, c confirmar,
   x falso positivo, Enter abrir).

2. VISOR DE EVIDENCIA — panel deslizante desde la derecha, 60 % del ancho, SOBRE la bandeja
   (que sigue visible detrás, atenuada). No es una página nueva: el prevencionista debe triar
   30 hallazgos sin perder su lugar.
   De arriba a abajo:
   - Recorte de video de 8 s en bucle, con dos interruptores: "mostrar cajas" y "difuminar rostro"
     (este último ACTIVADO por defecto y así debe verse en el diseño).
   - Tira horizontal de 6 miniaturas de los cuadros confirmados.
   - Mini línea de tiempo del evento con tres marcas: primera detección, umbral alcanzado, fin.
   - Bloque de descripción automática: un título grande y una descripción de dos líneas, con la
     confianza como dato secundario pequeño.
   - Bloque "POR QUÉ SE DISPARÓ": nombre y versión de la regla, zona, EPP exigido, umbral
     configurado ("4 de 5 cuadros en 2,0 s") y valores observados. Este bloque es importante:
     es lo que hace auditable el sistema.
   - Metadatos técnicos plegados: archivo de origen, hash, segundo del video, cadencia de
     muestreo, versión del modelo.
   - Barra de acciones fija abajo: Confirmar · Falso positivo · Duplicado · Posponer · Asignar.

3. COLA DE INGESTA — /videos
   Tabla de los videos de la carpeta vigilada: archivo, hash abreviado, duración, tamaño, fecha
   de captura, cámara, estado (En cola · Procesando con barra de progreso · Listo · Error con el
   motivo), cadencia efectiva, cuadros analizados, tiempo de proceso, hallazgos generados, y un
   botón de reprocesar. Arriba, una pestaña "Cámaras en vivo" deshabilitada con la etiqueta
   "v2" — el diseño ya deja el sitio para la ingesta en tiempo real.

4. PANEL GENERAL — /
   Exactamente tres bandas y nada más:
   - Cinco tarjetas de indicador, con número grande en monoespaciada, variación respecto del
     período anterior con flecha Y signo (no solo color) y un minigráfico de 60×20:
     Hallazgos abiertos · Críticos sin revisar · Cumplimiento de EPP (%) · Zona con más
     incumplimientos · Videos procesados hoy.
   - Dos gráficos, solo dos: tendencia semanal por severidad (líneas, máximo 4 series) y ranking
     de EPP incumplido (barras horizontales, top 5 más "Otros").
   - Los 8 hallazgos críticos más recientes, como lista compacta.
   Cabecera global con selector de faena, rango de fechas y turno que filtra toda la aplicación.
   Todo elemento del panel es clicable y lleva a la bandeja con el filtro aplicado.

5. EDITOR DE REGLAS — /reglas
   Maestro-detalle. A la izquierda, la lista de reglas con nombre, zona, estado activa/inactiva y
   hallazgos generados en 30 días. A la derecha, el formulario: zona (selección múltiple), EPP
   exigido como etiquetas conmutables (casco, chaleco, lentes, guantes, arnés, calzado), umbral de
   confirmación en SEGUNDOS con su explicación en lenguaje natural debajo del campo, ventana de
   cierre, severidad resultante, turno y franja horaria, confianza mínima, destinatarios de
   notificación, tiempo de espera entre alertas.
   Abajo, destacado, un botón "Simular sobre los últimos 30 días" y, bajo él, el resultado de la
   simulación: "habría generado 47 hallazgos" más una fila de 6 miniaturas de ejemplo.

6. REPORTES — /reportes
   Cuatro pestañas, cada una con UN gráfico grande y su tabla de respaldo debajo:
   ranking de EPP incumplido · ranking de peligrosidad por zona (tabla con minigráfico de 8
   semanas por fila) · mapa de calor hora × día de la semana · tendencia.
   Un selector de "dimensión de segmentación" (zona · turno · cámara · tipo de EPP). Botones de
   exportar a CSV y PDF.

ESTILO VISUAL — minimalista pero denso en información

- Escala de grises de 10 pasos y UN solo acento azul para lo interactivo. Todo el resto del color
  queda reservado a la severidad.
- Severidad con TRIPLE codificación, obligatorio: color + forma + palabra.
  Crítica = rombo relleno ◆ #D55E00 · Alta = triángulo ▲ #E69F00 · Media = círculo ● #0072B2 ·
  Baja = anillo hueco ○ gris · Conforme = ✓ #009E73.
  Es la paleta Okabe-Ito, segura para daltonismo. Prohibido rojo/verde como única distinción.
  Prueba: si al desaturar la captura no se distinguen los niveles, el diseño está mal.
- NUNCA colorear la fila completa según severidad. La severidad va en su celda con icono y
  palabra, más un filete de 3 px en el borde izquierdo de la fila.
- Espaciado en múltiplos de 4. Filas de 40 px. Relleno de celda 8×12. Radio 6 px. Bordes de 1 px
  en lugar de sombras; sombra solo en el panel deslizante y en los diálogos.
- Tipografía: Inter o la del sistema. Tamaños 11 (etiquetas en mayúscula) / 12 (metadatos) /
  13 (cuerpo de tabla) / 14 (cuerpo) / 20 (título) / 28 (indicador). Máximo tres pesos.
  Monoespaciada con cifras tabulares en horas, duraciones, hashes, identificadores y toda columna
  numérica.
- Modo oscuro para bandeja, visor y mapa; modo claro para reportes y administración. Nunca negro
  puro: fondo #0B0D10, superficie #14171A, borde #26292E.
- Barra lateral fija de 232 px, colapsable a 56 px, con contador de pendientes junto a "Hallazgos".
- Gráficos: solo barras horizontales, líneas, minigráficos y mapas de calor. Prohibidos torta,
  dona, 3D, apilados y arcoíris. Máximo 5 series.

DATOS DE EJEMPLO — úsalos, hacen que el diseño se vea real
Áreas: Chancado Primario · Correa Transportadora 3 · Taller de Mantención · Patio de Camiones ·
Bodega de Insumos.
Cámaras: CAM-01 Acceso Chancado · CAM-04 Correa 3 Norte · CAM-07 Taller · CAM-09 Patio.
Hallazgos de ejemplo:
  ◆ Crítica · sin casco · Chancado Primario · CAM-01 · 02:14:07 · 3 m 12 s · 0,91 · Por revisar
  ▲ Alta · sin chaleco · Patio de Camiones · CAM-09 · 07:41:55 · 48 s · 0,76 · Por revisar
  ▲ Alta · sin casco, sin chaleco · Correa 3 · CAM-04 · 14:02:31 · 1 m 05 s · 0,83 · Confirmado
  ● Media · sin lentes · Taller · CAM-07 · 09:18:44 · 2 m 30 s · 0,64 · Falso positivo
Turnos: A (08:00-20:00) y B (20:00-08:00). Los nombres van en español de Chile.

REGLAS QUE NO SE PUEDEN ROMPER
- Nada de reconocimiento facial ni de identificar trabajadores. El sistema reporta por área y
  turno, jamás por persona. No inventes columnas de nombre, RUT ni foto de trabajador.
- El difuminado de rostro aparece siempre activado en el visor.
- Cada hallazgo lleva visible la leyenda: "Indicio automatizado. Requiere validación humana."
- Severidad y confianza son columnas separadas: no las mezcles en un solo indicador.
```

---

## Después de generar

1. **Revísalo con el equipo completo** antes de escribir una línea de código. Cambiar un diseño
   cuesta minutos; cambiar una interfaz construida cuesta días.
2. Contrasta contra la lista de errores de
   [`docs/producto/05-diseno-interfaz.md`](../../../../docs/producto/05-diseno-interfaz.md).
3. **Prueba de daltonismo:** desatura una captura de la bandeja. Si no se distinguen los niveles
   de severidad, hay que corregir antes de implementar.
4. Exporta las pantallas a PNG y guárdalas en
   `Fase 2/Evidencias Proyecto/Evidencias de documentacion/` — el diseño de interfaz es una
   evidencia exigida por la asignatura.
