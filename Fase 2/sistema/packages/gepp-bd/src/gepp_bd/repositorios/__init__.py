"""Repositorios: la única forma en que la API y el trabajador leen y escriben la base.

Reciben una `Session` abierta y nunca confirman por su cuenta: quien llama decide la
transacción (`gepp_bd.transaccion`). Así el hallazgo y su notificación caen juntos o no
cae ninguno (outbox, ADR-008).
"""
