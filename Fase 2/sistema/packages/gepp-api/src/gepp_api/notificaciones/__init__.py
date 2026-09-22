"""Alertas a dos velocidades (ADR-008, `docs/arquitectura/03-alertas.md`).

El trabajador escribe la notificación en la misma transacción que el hallazgo (outbox); el
despachador de este paquete decide qué se avisa ya, qué va al resumen del turno y lo envía por
un `CanalNotificacion`, con reintentos y acuse de recibo.
"""
