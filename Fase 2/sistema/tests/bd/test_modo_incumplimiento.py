"""El modo de incumplimiento va por faena: columna, migración 0008, semilla y `en_fuente` (#31)."""

from __future__ import annotations

import pytest
from gepp_bd import transaccion
from gepp_bd.migrar import bajar, subir
from gepp_bd.modelos import Fuente
from gepp_bd.modelos import Regla as FilaRegla
from gepp_bd.repositorios import reglas
from gepp_bd.semilla import PerfilInvalido, cargar, leer
from gepp_core import ModoIncumplimiento
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from .test_ingesta import PERFIL

pytestmark = pytest.mark.integration


def _modo_de_la_camara_1(bd: Engine) -> ModoIncumplimiento:
    with transaccion(bd) as s:
        fila, fuente = s.get(FilaRegla, 1), s.get(Fuente, 1)
        assert fila is not None and fuente is not None
        regla = reglas.en_fuente(s, fila, fuente)
        assert regla is not None
        return regla.modo


def test_la_migracion_0008_sube_y_baja_con_las_dos_columnas(url_bd: str, bd: Engine) -> None:
    try:
        bajar(url_bd, "0007")
        for tabla in ("faena", "video"):
            assert "modo_incumplimiento" not in {c["name"] for c in inspect(bd).get_columns(tabla)}
        subir(url_bd)
        faena = {c["name"]: c for c in inspect(bd).get_columns("faena")}
        video = {c["name"]: c for c in inspect(bd).get_columns("video")}
        assert faena["modo_incumplimiento"]["nullable"] is False
        assert video["modo_incumplimiento"]["nullable"] is True  # NULL = procesado antes
    finally:
        subir(url_bd)


def test_la_base_rechaza_un_modo_desconocido_en_el_video(bd: Engine) -> None:
    _video(bd)
    with pytest.raises(IntegrityError, match="modo_incumplimiento"), bd.begin() as c:
        c.execute(text("UPDATE video SET modo_incumplimiento = 'otro'"))
    with bd.begin() as c:  # los dos valores y NULL sí
        for v in ("ausencia", "evidencia", None):
            c.execute(text("UPDATE video SET modo_incumplimiento = :v"), {"v": v})


def _video(bd: Engine) -> None:
    with bd.begin() as c:
        c.execute(text("INSERT INTO faena (nombre) VALUES ('f')"))
        c.execute(text("INSERT INTO area (faena_id, nombre) VALUES (1, 'a')"))
        c.execute(
            text("INSERT INTO fuente (area_id, nombre, tipo, uri) VALUES (1,'c','carpeta','/x')")
        )
        c.execute(
            text(
                "INSERT INTO video (fuente_id, ruta, hash_sha256, bytes, capture_ts_inicio,"
                " origen_capture_ts) VALUES (1, '/x.mp4', repeat('a', 64), 1, now(), 'manual')"
            )
        )


def test_un_video_nuevo_nace_sin_modo(bd: Engine) -> None:
    _video(bd)
    with bd.connect() as c:
        assert c.execute(text("SELECT modo_incumplimiento FROM video")).scalar_one() is None


def test_una_faena_sin_modo_queda_en_ausencia(bd: Engine) -> None:
    with bd.begin() as c:
        c.execute(text("INSERT INTO faena (nombre) VALUES ('f')"))
        modo = c.execute(text("SELECT modo_incumplimiento FROM faena")).scalar_one()
    assert modo == "ausencia"


def test_la_base_rechaza_un_modo_desconocido(bd: Engine) -> None:
    with pytest.raises(IntegrityError, match="modo_incumplimiento"), bd.begin() as c:
        c.execute(text("INSERT INTO faena (nombre, modo_incumplimiento) VALUES ('f', 'otro')"))


def test_la_base_admite_los_dos_modos(bd: Engine) -> None:
    with bd.begin() as c:
        c.execute(text("INSERT INTO faena (nombre, modo_incumplimiento) VALUES ('a', 'ausencia')"))
        c.execute(text("INSERT INTO faena (nombre, modo_incumplimiento) VALUES ('e', 'evidencia')"))


def test_el_perfil_de_construccion_declara_ausencia(bd: Engine) -> None:
    perfil = leer(PERFIL)
    assert perfil["faena"]["modo_incumplimiento"] == "ausencia"
    with transaccion(bd) as s:
        assert cargar(s, perfil).modo_incumplimiento == "ausencia"


def test_la_semilla_sin_la_clave_deja_ausencia(bd: Engine) -> None:
    perfil = leer(PERFIL)
    del perfil["faena"]["modo_incumplimiento"]
    with transaccion(bd) as s:
        assert cargar(s, perfil).modo_incumplimiento == "ausencia"


def test_la_semilla_con_evidencia_la_guarda(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["faena"]["modo_incumplimiento"] = "evidencia"
    with transaccion(bd) as s:
        assert cargar(s, perfil).modo_incumplimiento == "evidencia"


def _modo_guardado(bd: Engine) -> str:
    with bd.connect() as c:
        return c.execute(text("SELECT modo_incumplimiento FROM faena")).scalar_one()


def test_recargar_el_perfil_con_otro_modo_cambia_la_faena_ya_sembrada(bd: Engine) -> None:
    """Revisión de Codex: `cargar` volvía antes de leer el modo y la faena no cambiaba."""
    perfil = leer(PERFIL)
    with transaccion(bd) as s:
        cargar(s, perfil)
    perfil["faena"]["modo_incumplimiento"] = "evidencia"
    with transaccion(bd) as s:
        cargar(s, perfil)
    assert _modo_guardado(bd) == "evidencia"
    perfil["faena"]["modo_incumplimiento"] = "ausencia"
    with transaccion(bd) as s:
        cargar(s, perfil)
    assert _modo_guardado(bd) == "ausencia"


def test_recargar_un_perfil_sin_la_clave_no_toca_el_modo_de_la_faena(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["faena"]["modo_incumplimiento"] = "evidencia"
    with transaccion(bd) as s:
        cargar(s, perfil)
    del perfil["faena"]["modo_incumplimiento"]
    with transaccion(bd) as s:
        cargar(s, perfil)
    assert _modo_guardado(bd) == "evidencia"


def test_recargar_un_perfil_con_un_modo_invalido_falla_y_no_cambia_nada(bd: Engine) -> None:
    perfil = leer(PERFIL)
    with transaccion(bd) as s:
        cargar(s, perfil)
    perfil["faena"]["modo_incumplimiento"] = "otro"
    with pytest.raises(PerfilInvalido, match="modo_incumplimiento"), transaccion(bd) as s:
        cargar(s, perfil)
    assert _modo_guardado(bd) == "ausencia"


def test_la_semilla_con_un_modo_invalido_falla_con_su_nombre(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["faena"]["modo_incumplimiento"] = "otro"
    with pytest.raises(PerfilInvalido, match="modo_incumplimiento"), transaccion(bd) as s:
        cargar(s, perfil)


def test_la_semilla_con_la_clave_vacia_falla(bd: Engine) -> None:
    """Revisión de Codex: `modo_incumplimiento:` sin valor (null en YAML) pasaba como ausente."""
    perfil = leer(PERFIL)
    perfil["faena"]["modo_incumplimiento"] = None
    with pytest.raises(PerfilInvalido, match="modo_incumplimiento"), transaccion(bd) as s:
        cargar(s, perfil)


def test_recargar_un_perfil_con_la_clave_vacia_falla_y_no_cambia_nada(bd: Engine) -> None:
    perfil = leer(PERFIL)
    perfil["faena"]["modo_incumplimiento"] = "evidencia"
    with transaccion(bd) as s:
        cargar(s, perfil)
    perfil["faena"]["modo_incumplimiento"] = None
    with pytest.raises(PerfilInvalido, match="modo_incumplimiento"), transaccion(bd) as s:
        cargar(s, perfil)
    assert _modo_guardado(bd) == "evidencia"


@pytest.mark.parametrize("modo", ["ausencia", "evidencia"])
def test_en_fuente_pone_el_modo_de_la_faena_en_la_regla(bd: Engine, modo: str) -> None:
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
        s.execute(text("UPDATE faena SET modo_incumplimiento = :m"), {"m": modo})
    assert _modo_de_la_camara_1(bd) is ModoIncumplimiento(modo)


def test_para_fuente_entrega_el_modo_en_todas_las_reglas(bd: Engine) -> None:
    """El trabajador y el recálculo de la API usan `para_fuente`: ven lo mismo que `en_fuente`."""
    with transaccion(bd) as s:
        cargar(s, leer(PERFIL))
        s.execute(text("UPDATE faena SET modo_incumplimiento = 'evidencia'"))
    with transaccion(bd) as s:
        fuente = s.get(Fuente, 1)
        assert fuente is not None
        aplicables = reglas.para_fuente(s, fuente)
        assert aplicables
        assert {r.modo for r in aplicables} == {ModoIncumplimiento.EVIDENCIA}
