"""Guardián EPP — API HTTP.

Regla dura (ADR-007): este paquete NO importa `gepp_vision`. Se comunica con la
visión por la base de datos y la cola. Es lo que permite levantar la API completa
en una máquina sin GPU.
"""

__version__ = "0.1.0"
