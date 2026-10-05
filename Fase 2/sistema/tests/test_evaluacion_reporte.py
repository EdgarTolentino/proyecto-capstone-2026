"""Salida del nivel 1 (#31): JSON reproducible y tabla para el issue."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from gepp_vision.evaluacion.coco import CajaPx
from gepp_vision.evaluacion.deteccion import MAX_DETS, evaluar
from gepp_vision.evaluacion.reporte import estado_git, reporte, sha256, tabla_markdown

HD = (1920, 1080)
GIT = {"commit": "a" * 40, "cambios_sin_confirmar": False}


def _datos(tmp_path: Path, origen: str, score_minimo: float | None = 0.05) -> dict[str, Any]:
    entrada = tmp_path / "verdad.json"
    entrada.write_text("{}", encoding="utf-8")
    persona = CajaPx("a.jpg", "persona", 0, 0, 50, 100)
    region = evaluar([persona], [CajaPx("a.jpg", "persona", 0, 0, 50, 100, 0.9)], {"a.jpg": HD})
    return reporte(
        {"dentro": region, "fuera": evaluar([], [], {"a.jpg": HD})},
        origen_verdad=origen,
        modelo="rfdetr-n-epp-v1",
        imagenes=["a.jpg"],
        recorte=(600.0, 220.0, 1400.0, 730.0),
        umbral=0.45,
        score_minimo=score_minimo,
        entradas={"verdad": entrada},
        git=GIT,
    )


def test_el_sesgo_se_declara_solo_si_la_verdad_viene_de_pre_etiquetas(tmp_path: Path) -> None:
    con = _datos(tmp_path, "con-preetiquetas")["limitaciones"]
    sin = _datos(tmp_path, "sin-preetiquetas")["limitaciones"]
    assert any("pre-etiquetas" in linea for linea in con)
    assert not any("pre-etiquetas" in linea for linea in sin)


def test_origen_desconocido_detiene(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="origen"):
        _datos(tmp_path, "cvat")


def test_el_json_lleva_lo_necesario_para_reproducir(tmp_path: Path) -> None:
    datos = _datos(tmp_path, "con-preetiquetas")
    json.dumps(datos)  # serializable tal cual
    assert datos["commit"] == "a" * 40
    assert datos["entradas"]["verdad"]["sha256"] == hashlib.sha256(b"{}").hexdigest()
    assert datos["parametros"] == {
        "recorte_px": [600.0, 220.0, 1400.0, 730.0],
        "umbral_confianza": 0.45,
        "score_minimo": 0.05,
        "umbral_iou": 0.5,
        "max_dets": 300,
        "imagenes": 1,
    }
    assert datos["regiones"]["fuera"]["clases"][0]["map50"] is None


def test_la_tabla_usa_coma_decimal_y_raya_para_lo_que_no_existe(tmp_path: Path) -> None:
    tabla = tabla_markdown(_datos(tmp_path, "con-preetiquetas"))
    assert "| dentro | persona | 1 | 1 | 1,000 | 1,000 |" in tabla
    assert "| dentro | **total** | 1 | 1 | 1,000 | 1,000 |" in tabla
    assert "| fuera | persona | 0 | 0 | — | — | — | — | — | — | — |" in tabla
    assert "| fuera | **total** | 0 | 0 | — | — | — | — | — | — | — |" in tabla
    assert "aaaaaaa" in tabla and "con-preetiquetas" in tabla


def test_el_aviso_de_max_dets_solo_si_se_pasa(tmp_path: Path) -> None:
    datos = _datos(tmp_path, "con-preetiquetas")
    datos["regiones"]["fuera"]["max_predicciones"] = MAX_DETS
    assert not any(li.startswith("Aviso") for li in tabla_markdown(datos).splitlines())
    datos["regiones"]["fuera"]["max_predicciones"] = MAX_DETS + 1
    aviso = [li for li in tabla_markdown(datos).splitlines() if li.startswith("Aviso")]
    assert len(aviso) == 1
    assert "fuera" in aviso[0] and str(MAX_DETS + 1) in aviso[0] and "no se evaluaron" in aviso[0]


@pytest.mark.parametrize(
    ("score_minimo", "avisa"),
    [
        (None, False),
        (0.05, False),
        (0.050000179, False),  # el mínimo real de un archivo hecho con --umbral 0.05 (float32)
        (0.0546875, False),  # 7/128, justo bajo el aviso
        (0.0625, True),  # 1/16: desde aquí avisa
        (0.40, True),  # el --umbral por defecto de preetiquetar.py
    ],
)
def test_el_aviso_de_score_minimo_solo_si_la_curva_quedo_cortada(
    tmp_path: Path, score_minimo: float | None, avisa: bool
) -> None:
    datos = _datos(tmp_path, "con-preetiquetas", score_minimo)
    assert datos["parametros"]["score_minimo"] == score_minimo
    aviso = [li for li in tabla_markdown(datos).splitlines() if li.startswith("Aviso")]
    assert len(aviso) == (1 if avisa else 0)
    if avisa:
        assert "preetiquetar.py --umbral 0.05" in aviso[0] and "subestimado" in aviso[0]


def test_la_tabla_dice_que_predichas_cuenta_sobre_el_umbral(tmp_path: Path) -> None:
    tabla = tabla_markdown(_datos(tmp_path, "con-preetiquetas"))
    assert "| Predichas ≥ umbral |" in tabla
    assert "· confianza ≥ 0.45 ·" in tabla


def test_sha256_lee_por_bloques(tmp_path: Path) -> None:
    grande = tmp_path / "grande.bin"
    grande.write_bytes(b"x" * (3 << 20))
    assert sha256(grande) == hashlib.sha256(b"x" * (3 << 20)).hexdigest()


def test_estado_git_detecta_cambios_sin_confirmar(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    limpio = estado_git(tmp_path)
    assert len(limpio["commit"]) == 40 and limpio["cambios_sin_confirmar"] is False
    (tmp_path / "nuevo.txt").write_text("x", encoding="utf-8")
    assert estado_git(tmp_path)["cambios_sin_confirmar"] is True
