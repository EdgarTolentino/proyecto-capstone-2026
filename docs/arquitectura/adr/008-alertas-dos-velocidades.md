# ADR-008 — Alertas a dos velocidades

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

La reacción natural es notificar cada incumplimiento en cuanto se detecta. Es también la forma
más rápida de matar el proyecto: la industria, con cientos de cámaras, produce miles de alertas
por turno con menos del 3 % accionables. A escala de 4–8 cámaras el problema aparece igual si se
notifica por detección en vez de por evento consolidado.

## Decisión

| Condición | Notificación |
|---|---|
| Peligro inminente | Inmediata, con validación humana antes de escalar |
| Incumplimiento de EPP corriente | **Ninguna individual**: entra al resumen por turno |
| Incumplimiento de EPP grave | Inmediata solo si supera duración (p. ej. >120 s en área crítica) o se repite N veces en el turno |

Con: doble tiempo de espera (global y por cámara), agrupación de alertas relacionadas, silencios
por mantenimiento, y **acuse de recibo** que cierra el ciclo.

Las alertas van **al área y al turno**, no a la persona: *"Área 4, turno noche, 3 personas sin
casco entre 02:10 y 02:14"*. Si el cliente pidiera alerta nominativa, es un cambio de alcance
formal que exige nueva base de licitud y modificación del reglamento interno.

## Implementación

Patrón **outbox**: la notificación se escribe en la misma transacción que el hallazgo y un
despachador aparte la envía con reintentos. Si el canal se cae, no se pierde nada. El canal está
detrás de un puerto `CanalNotificacion`; la v1 implementa correo y Telegram, y WhatsApp queda
como implementación futura sin tocar el resto.

## Métrica que hay que medir y que ningún proveedor publica

**Tasa de alertas accionables** = hallazgos que terminan en acción correctiva ÷ hallazgos
emitidos. Es el número que demuestra que el sistema sirve, y sale gratis del flujo de triage.

## Consecuencias

Si en la demostración de la S15 el prevencionista recibe 200 correos, el proyecto está muerto
aunque el modelo sea perfecto. Esta decisión es la que lo evita.
