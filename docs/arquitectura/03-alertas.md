# Arquitectura de alertas

> **El canal no es el problema. El volumen sí.**
>
> La evidencia histórica es brutal: en el accidente de una refinería en 1994, dos operadores
> recibieron 275 alarmas en 11 minutos. En unidades de cuidados intensivos se documenta cerca de
> un 89 % de falsos positivos en las alarmas. En sistemas de seguridad electrónica en EE.UU. se
> reporta que hasta el 98 % de las activaciones son falsas.
>
> Un sistema que emite una alerta por detección está muerto al segundo turno. No porque falle:
> porque **el prevencionista lo apaga mentalmente y no vuelve**.

## El presupuesto de alertas

Es un **requisito no funcional con número**, no una aspiración:

| | |
|---|---|
| **Meta** | ≤ 6 avisos por prevencionista por turno de 12 h |
| **Techo duro** | 1 alerta cada 10 minutos por persona |
| **Distribución objetivo** | 5 % crítica · 15 % alta · 80 % baja |

El umbral de confirmación **se calibra para respetar el presupuesto**, no para maximizar el
recall. Si se excede, el sistema degrada solo: sube el umbral, agrupa por zona y baja a resumen.

## Las dos velocidades

| Condición | Canal | Latencia |
|---|---|---|
| Peligro inminente | Aviso inmediato, con validación humana antes de escalar | Segundos |
| Incumplimiento de EPP **grave** (supera duración o se repite N veces en el turno) | Aviso inmediato | Segundos |
| Incumplimiento de EPP corriente | **Resumen por turno** — el canal por defecto | Fin de turno |

> Dato que conviene tener a mano: en un despliegue real con más de 1.600 trabajadores, **el
> resumen diario por correo le ganó al panel web**. La métrica de éxito del producto no son las
> visitas al panel, es la **tasa de disposición del resumen** (atendido / descartado / no
> concluyente).

## La cadena de supresión: seis etapas

Todas configurables en la base de datos, igual que las reglas de EPP.

```
detección
   │
   ├─ 1. CONFIRMACIÓN TEMPORAL    N de M cuadros con la persona visible y no ocluida
   │                              (no "N cuadros seguidos": el parpadeo es la norma)
   ├─ 2. DEDUPLICACIÓN            clave = hash(area, tipo_epp, track) · ventana 15 min
   │
   ├─ 3. AGRUPACIÓN               espera 45 s · intervalo 5 min · repetición 2 h
   │                              agrupa por (área, tipo de EPP)
   │                              "tres personas sin casco en Chancado" = UN mensaje
   ├─ 4. INHIBICIÓN               área en mantención o cámara caída → silencio total
   │
   ├─ 5. VENTANAS DE SILENCIO     cambio de turno, colación, tronadura programada
   │
   └─ 6. PRESUPUESTO              si el destinatario superó su cuota, degrada a resumen
          │
          ▼
        aviso
```

Sin la etapa 3 el sistema es inusable en cuanto haya más de una persona en cuadro.

## Canales: qué usar en la v1

| Canal | Rol en v1 | Por qué |
|---|---|---|
| **ntfy autoalojado** | Canal de terreno | Un contenedor, licencia permisiva, sin costo y **sin aprobación de terceros**. Sus botones de acción dan acuse de recibo de un toque — con guantes puestos |
| **Web Push / PWA** | Panel de sala de control | Sin infraestructura adicional |
| **Correo** | Solo el resumen | Barato y asíncrono por naturaleza |
| **Telegram** | Plan B | Implementable en un día |
| **WhatsApp Cloud API** | **Diseñado, no desplegado** | Exige verificación de negocio con Meta y revisión de plantillas de hasta 24 h. Es un riesgo que no se corre en la semana 17 de un proyecto de título |

**Se escribe el adaptador de WhatsApp y sus pruebas, pero no se despliega.** Esa es la diferencia
entre tener la puerta abierta y apostar el cronograma.

## El contrato que deja la puerta abierta

```python
class CanalNotificacion(Protocol):
    nombre: str
    def enviar(self, aviso: Aviso, destino: Destino) -> ResultadoEnvio: ...
```

Con exactamente **tres** resultados posibles: `ACEPTADO` (con identificador externo),
`RECHAZADO_PERMANENTE` y `FALLO_TRANSITORIO` (con instante de reintento).

> **Ninguna función `enviar_whatsapp()` puede aparecer en el dominio.** Añadir un canal debe ser
> una clase nueva y una fila en la tabla `canal`. Nada más.

El `Aviso` incorpora desde la v1 los límites del canal más restrictivo (título ≤ 60 caracteres,
cuerpo ≤ 1024), aunque ese canal no se use todavía: así el día que se encienda no hay que
reescribir el formateador. La URL de evidencia es **siempre firmada y con expiración**, nunca la
imagen embebida.

## Entrega confiable: patrón outbox

El hallazgo y sus filas de salida se escriben **en la misma transacción**. Un despachador aparte
las envía con reintentos.

- Restricción `UNIQUE(aviso_id, canal, destino)` — **esa restricción es la idempotencia**.
- El despachador toma trabajo con `SELECT ... FOR UPDATE SKIP LOCKED`, de modo que dos procesos
  nunca envían el mismo aviso.
- Si el canal se cae, no se pierde nada: se reintenta.

## Ciclo de vida del aviso

```
EMITIDO ──▶ ENTREGADO ──▶ ACUSADO ──▶ RESUELTO
   │            │            │         (acción tomada │ falso positivo │ no aplica)
   │            │            └─ detiene el escalamiento
   │            └─ "entregado" NO es "alguien miró"
   └──────────────────────────────▶ CADUCADO
```

> **Nunca se usa el "entregado" o "leído" del canal como acuse de recibo.** Entregado no es que
> alguien mirara, y leído no es que alguien fuera. El acuse es un acto explícito: un toque en un
> botón, con un token de un solo uso para que una URL filtrada no sirva para falsear acuses.

## Escalamiento

Solo para severidad **crítica y alta**. Media y baja jamás despiertan a nadie: van al resumen.

| Nivel | Cuándo | A quién |
|---|---|---|
| 0 | t = 0 | Prevencionista de turno del área |
| 1 | t + 10 min sin acuse | Supervisor de turno + un segundo prevencionista |
| 2 | t + 25 min sin acuse | Jefe de turno y sala de control |

Diez minutos y no los treinta habituales, porque esto es seguridad. Pero nunca menos de tres
cuando el nivel tiene varios destinatarios.

**Al agotar el escalamiento, el aviso se marca `NO_ATENDIDO` y ese contador es un indicador
visible.** Que un aviso muera en silencio —el comportamiento por defecto de la mayoría de las
herramientas— es inaceptable aquí.

## Qué dice el aviso

Las alertas van **al área y al turno, no a la persona**:

> *"Área 4 · turno noche · 3 personas sin casco entre 02:10 y 02:14"*

Con tres acciones y no más: **Acuso recibo · Ver evidencia · Falso positivo**.

Y la leyenda que la ley exige y que además es verdad: *"Indicio automatizado. Requiere validación
humana."*

## El factor humano, que no es un adorno

Un estudio con cerca de 1.200 participantes midió más de un **30 % de quejas** bajo supervisión
percibida como de inteligencia artificial, frente a un ~7 % bajo supervisión humana — **y peor
desempeño**. El efecto **se revierte** cuando el sistema se enmarca como **formativo** en lugar de
evaluativo.

Traducción a decisiones de producto, no a buenas intenciones:

- El sistema reporta **por área**, jamás por trabajador.
- Existe un **módulo de reconocimiento positivo**: porcentaje de cumplimiento y ranking positivo
  por cuadrilla.
- El lenguaje de la interfaz y de los avisos es de **prevención**, no de infracción.
