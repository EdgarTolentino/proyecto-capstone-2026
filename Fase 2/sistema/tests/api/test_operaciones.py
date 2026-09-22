"""Las 18 operaciones del contrato, ni una más ni una menos (lo mismo que `make contrato`)."""

from __future__ import annotations

from scripts.exportar_openapi import (  # type: ignore[import-not-found]
    main,
    openapi_app,
    operaciones_app,
    operaciones_contrato,
)


def test_la_api_sirve_exactamente_las_operaciones_del_contrato() -> None:
    contrato, app = operaciones_contrato(), operaciones_app(openapi_app())
    assert contrato - app == set(), f"faltan: {sorted(contrato - app)}"
    assert app - contrato == set(), f"sobran: {sorted(app - contrato)}"
    assert len(contrato) == 18


def test_make_contrato_falla_si_falta_una(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import scripts.exportar_openapi as mod  # type: ignore[import-not-found]

    original = mod.operaciones_app
    monkeypatch.setattr(mod, "operaciones_app", lambda e: set(list(original(e))[1:]))
    assert main([]) == 1
