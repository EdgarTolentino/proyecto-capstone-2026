"""Salida del nivel 1 (#31): JSON reproducible y tabla para el issue."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from gepp_vision.evaluacion.acuerdo import SIN_CAJA, acuerdo
from gepp_vision.evaluacion.coco import ArchivoCoco, CajaPx
from gepp_vision.evaluacion.deteccion import MAX_DETS, evaluar
from gepp_vision.evaluacion.reporte import (
    estado_git,
    limitacion_videos,
    reporte,
    reporte_acuerdo,
    sha256,
    tabla_acuerdo,
    tabla_markdown,
    videos_de_origen,
)

HD = (1920, 1080)
GIT = {"commit": "a" * 40, "cambios_sin_confirmar": False}


def _datos(
    tmp_path: Path,
    origen: str,
    score_minimo: float | None = 0.05,
    imagenes: tuple[str, ...] = ("a.jpg",),
) -> dict[str, Any]:
    entrada = tmp_path / "verdad.json"
    entrada.write_text("{}", encoding="utf-8")
    persona = CajaPx("a.jpg", "persona", 0, 0, 50, 100)
    region = evaluar([persona], [CajaPx("a.jpg", "persona", 0, 0, 50, 100, 0.9)], {"a.jpg": HD})
    return reporte(
        {"dentro": region, "fuera": evaluar([], [], {"a.jpg": HD})},
        origen_verdad=origen,
        modelo="rfdetr-n-epp-v1",
        imagenes=list(imagenes),
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


def _acuerdo_de_prueba(tmp_path: Path, segunda_casco: str, img: str = "a.jpg") -> dict[str, Any]:
    entrada = tmp_path / "segunda.json"
    entrada.write_text("{}", encoding="utf-8")
    hd = {img: (1920, 1080)}
    primera = ArchivoCoco(
        hd,
        (CajaPx(img, "persona", 0, 0, 50, 100), CajaPx(img, "casco", 500, 0, 20, 20)),
        "",
    )
    segunda = ArchivoCoco(
        hd,
        (CajaPx(img, "persona", 0, 0, 50, 100), CajaPx(img, segunda_casco, 500, 0, 20, 20)),
        "",
    )
    return reporte_acuerdo(acuerdo(primera, segunda), entradas={"segunda": entrada}, git=GIT)


def test_el_json_del_acuerdo_lleva_lo_necesario_para_reproducir(tmp_path: Path) -> None:
    datos = _acuerdo_de_prueba(tmp_path, "casco")
    json.dumps(datos)
    assert datos["nivel"] == 0 and datos["commit"] == "a" * 40
    assert datos["entradas"]["segunda"]["sha256"] == hashlib.sha256(b"{}").hexdigest()
    assert datos["parametros"] == {"umbral_iou": 0.5, "kappa_minimo": 0.7, "imagenes": 1}
    assert datos["resultado"]["kappa"] == 1.0
    assert any("pre-etiquetas" in linea for linea in datos["limitaciones"])


def test_la_tabla_del_acuerdo_muestra_la_matriz_y_la_alerta(tmp_path: Path) -> None:
    sin_alerta = tabla_acuerdo(_acuerdo_de_prueba(tmp_path, "casco"))
    assert "| 1,000 | 1,000 | 2 | 0 | 0 |" in sin_alerta
    assert "Alerta" not in sin_alerta
    con_alerta = tabla_acuerdo(_acuerdo_de_prueba(tmp_path, "chaleco"))
    assert "Alerta" in con_alerta and "0,333" in con_alerta
    assert "| casco | 0 | 0 | 1 | 0 |" in con_alerta  # filas: primera; columnas: segunda
    assert SIN_CAJA in con_alerta


def test_la_tabla_del_acuerdo_dice_cuando_el_kappa_es_indefinido() -> None:
    datos: dict[str, Any] = {
        "parametros": {"imagenes": 1, "umbral_iou": 0.5, "kappa_minimo": 0.7},
        "resultado": {
            "kappa": None,
            "iou_medio": None,
            "pares": 0,
            "solo_primera": 0,
            "solo_segunda": 0,
            "matriz": {},
        },
        "commit": "a" * 40,
        "cambios_sin_confirmar": False,
        "limitaciones": [],
    }
    tabla = tabla_acuerdo(datos)
    assert "| — | — | 0 | 0 | 0 |" in tabla and "indefinido" in tabla


@pytest.mark.parametrize(
    ("nombre", "video"),
    [
        ("celular-01_000000.jpg", "celular-01"),
        ("yt_GPCHfE_min020_000150.jpg", "yt_GPCHfE_min020"),  # el video lleva «_» en su nombre
        ("lote/celular-02_001260.jpg", "celular-02"),  # con carpeta delante
        ("camara_999999.jpg", "camara"),  # el último índice de seis dígitos
        ("camara_1000000.jpg", "camara"),  # `:06d` es ancho mínimo: desde aquí salen siete
    ],
)
def test_el_video_sale_del_nombre_que_pone_lote0(nombre: str, video: str) -> None:
    assert videos_de_origen([nombre]) == [video]


@pytest.mark.parametrize(
    "nombre",
    [
        "celular-01_00000.jpg",
        "celular-01_0000000.jpg",
        "a.jpg",
        "celular-01_000000.png",
        "celular-02_000000.jpg\n",
        # dígitos de ancho completo, U+FF11 a U+FF16
        "celular-02_\uff11\uff12\uff13\uff14\uff15\uff16.jpg",
    ],
)
def test_un_nombre_fuera_del_formato_no_dice_de_que_video_sale(nombre: str) -> None:
    # 5 dígitos, y 7 con cero delante, que `:06d` nunca escribe; un nombre suelto, otra
    # extensión, un salto de línea al final y dígitos que no son ASCII
    assert videos_de_origen(["celular-01_000000.jpg", nombre]) is None


def test_sin_imagenes_no_se_sabe_el_origen() -> None:
    assert videos_de_origen([]) is None


def test_la_limitacion_cuenta_los_videos_de_verdad() -> None:
    lote4 = ["celular-03_000000.jpg", "celular-01_000000.jpg", "celular-02_000000.jpg"]
    assert limitacion_videos(lote4).startswith(
        "Los cuadros salen de 3 archivos de video (celular-01, celular-02, celular-03):"
    )
    uno = ["celular-01_000000.jpg", "celular-01_000090.jpg"]
    assert limitacion_videos(uno).startswith(
        "Los cuadros salen de 1 archivo de video (celular-01):"
    )
    assert limitacion_videos(["a.jpg"]).startswith("No se sabe de qué archivos de video")


def test_el_reporte_y_el_acuerdo_llevan_la_limitacion_de_sus_imagenes(tmp_path: Path) -> None:
    lote4 = ("celular-01_000000.jpg", "celular-02_000000.jpg", "celular-03_000000.jpg")
    nivel1 = _datos(tmp_path, "sin-preetiquetas", imagenes=lote4)["limitaciones"]
    assert nivel1[0].startswith("Los cuadros salen de 3 archivos de video")
    assert not any("4 tramos" in linea for linea in nivel1)
    nivel0 = _acuerdo_de_prueba(tmp_path, "casco", img="celular-02_000090.jpg")["limitaciones"]
    assert any(
        linea.startswith("Los cuadros salen de 1 archivo de video (celular-02)") for linea in nivel0
    )
    assert not any("un solo video" in linea for linea in nivel0)
