"""Los 7 días de las series del panel terminan en el último día DENTRO de `[desde, hasta)`."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from gepp_api.servicios.panel import dias_locales

TZ = ZoneInfo("America/Santiago")
#: Lo que manda la web para el rango 1→7-oct: el inicio del día siguiente, en hora de la faena.
MEDIANOCHE = datetime(2026, 10, 8, tzinfo=TZ)
UN_US = timedelta(microseconds=1)


def test_hasta_en_la_medianoche_excluye_ese_dia() -> None:
    dias = dias_locales(MEDIANOCHE, TZ)
    assert dias[0] == date(2026, 10, 1)
    assert dias[-1] == date(2026, 10, 7)


def test_un_microsegundo_antes_de_la_medianoche_sigue_en_el_dia() -> None:
    assert dias_locales(MEDIANOCHE - UN_US, TZ)[-1] == date(2026, 10, 7)


def test_un_microsegundo_despues_de_la_medianoche_ya_es_el_dia_siguiente() -> None:
    assert dias_locales(MEDIANOCHE + UN_US, TZ)[-1] == date(2026, 10, 8)


def test_la_medianoche_se_corta_en_la_zona_de_la_faena_y_no_en_utc() -> None:
    # 2026-10-08 03:00 UTC es la medianoche en Santiago (UTC-3).
    assert dias_locales(MEDIANOCHE.astimezone(ZoneInfo("UTC")), TZ)[-1] == date(2026, 10, 7)


def test_cruza_el_cambio_de_hora_sin_saltar_ni_repetir_dias() -> None:
    # Chile adelanta la hora el 6-sep-2026: el 6 tiene 23 h.
    dias = dias_locales(datetime(2026, 9, 9, tzinfo=TZ), TZ)
    assert dias == [date(2026, 9, 2) + timedelta(days=i) for i in range(7)]
