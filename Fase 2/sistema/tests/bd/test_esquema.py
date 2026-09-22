"""El esquema: sube, baja, coincide con los modelos y hace cumplir sus reglas."""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from gepp_bd.migrar import bajar, subir
from gepp_bd.modelos import Base
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from .conftest import TABLAS

pytestmark = pytest.mark.integration


def test_la_migracion_baja_hasta_base_y_vuelve_a_subir(url_bd: str) -> None:
    motor = create_engine(url_bd)
    try:
        bajar(url_bd)
        assert set(inspect(motor).get_table_names()) == {"alembic_version"}
        subir(url_bd)
        assert set(inspect(motor).get_table_names()) == {*TABLAS, "alembic_version"}
    finally:
        motor.dispose()


def test_la_migracion_coincide_con_los_modelos(motor: Engine) -> None:
    """Si alguien cambia `modelos.py` sin migración, esta prueba lo dice."""
    with motor.connect() as c:
        diferencias = compare_metadata(MigrationContext.configure(c), Base.metadata)
    assert diferencias == []


def test_la_auditoria_no_admite_update_ni_delete(bd: Engine) -> None:
    with bd.begin() as c:
        c.execute(
            text("INSERT INTO auditoria (rol, accion, entidad) VALUES ('auditor','leer','x')")
        )
        c.execute(text("UPDATE auditoria SET accion = 'borrar'"))
        c.execute(text("DELETE FROM auditoria"))
    with bd.connect() as c:
        filas = c.execute(text("SELECT accion FROM auditoria")).all()
    assert [f.accion for f in filas] == ["leer"]


def test_la_deteccion_exige_cuatro_coordenadas(bd: Engine) -> None:
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
    with pytest.raises(IntegrityError, match="bbox_cuatro"), bd.begin() as c:
        c.execute(
            text(
                "INSERT INTO deteccion (video_id, cuadro_idx, capture_ts, clase, confianza,"
                " bbox, modelo_version) VALUES (1, 0, now(), 'persona', 0.9,"
                " '{0.1,0.1,0.2}', 'm')"
            )
        )


def test_la_regla_no_admite_umbrales_nulos_ni_sin_epp(bd: Engine) -> None:
    with bd.begin() as c:
        c.execute(text("INSERT INTO faena (nombre) VALUES ('f')"))
        c.execute(text("INSERT INTO area (faena_id, nombre) VALUES (1, 'a')"))
    base = (
        "INSERT INTO regla (area_id, nombre, epp_exigido, severidad, base_licitud,"
        " finalidad_declarada, confirmacion_segundos) VALUES (1, 'r', {epp}, 3,"
        " 'obligacion_legal', 'f', {conf})"
    )
    with pytest.raises(IntegrityError, match="epp_exigido_no_vacio"), bd.begin() as c:
        c.execute(text(base.format(epp="'{}'", conf="2.0")))
    with pytest.raises(IntegrityError, match="umbrales_positivos"), bd.begin() as c:
        c.execute(text(base.format(epp="'{casco}'", conf="0")))
