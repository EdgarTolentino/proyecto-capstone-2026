"""Recall de `cabeza` con la cabeza esperada derivada de la verdad (ADR-013).

Cuadro de 1024 x 1024 para que los px normalicen sin error. La persona base mide 128 x 256 en
(128, 256): su franja de casco es el 30 % superior, y = 256 .. 332,8, x = 128 .. 256. El 30 % no es
diádico, así que en y el borde se prueba a 0,8 px de cada lado; en x (borde 128 y 256) sí es exacto.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_vision.entrenamiento import CLASES_V3
from gepp_vision.etiquetado import a_coco
from gepp_vision.evaluacion import CajaPx, evaluar_cabeza, leer_coco
from gepp_vision.evaluacion.coco import EntradaInvalida

from scripts.evaluar import main  # type: ignore[import-not-found]

TAM = {"a.jpg": (1024, 1024)}
TODO = (0.0, 0.0, 1024.0, 1024.0)


def _persona(x: float = 128, y: float = 256, archivo: str = "a.jpg") -> CajaPx:
    return CajaPx(archivo, "persona", x, y, 128, 256)


def _casco(cx: float, cy: float, archivo: str = "a.jpg") -> CajaPx:
    return CajaPx(archivo, "casco", cx - 8, cy - 8, 16, 16)


def _cabeza(cx: float, cy: float, score: float = 0.75, archivo: str = "a.jpg") -> CajaPx:
    return CajaPx(archivo, "cabeza", cx - 8, cy - 8, 16, 16, score)


def _medir(
    verdad: list[CajaPx],
    predichas: list[CajaPx],
    umbral: float = 0.5,
    recorte: tuple[float, float, float, float] = TODO,
    tam: dict[str, tuple[int, int]] | None = None,
) -> dict[str, Any]:
    return evaluar_cabeza(verdad, predichas, tam or TAM, recorte, umbral)


# -- la cabeza esperada: persona sin casco asociado ------------------------------------------


@pytest.mark.parametrize(
    ("cy", "esperadas"),
    [
        (332.0, 0),  # casco justo dentro de la franja: la persona lo lleva
        (334.0, 1),  # justo fuera: ese casco no es de esta persona
    ],
)
def test_el_casco_asociado_es_el_de_la_franja_y_en_sus_dos_lados(cy: float, esperadas: int) -> None:
    m = _medir([_persona(), _casco(192, cy)], [])["total"]
    assert m.esperadas == esperadas


@pytest.mark.parametrize(("cx", "esperadas"), [(128.0, 0), (256.0, 0), (127.0, 1), (257.0, 1)])
def test_el_borde_en_x_de_la_franja_cuenta_como_dentro(cx: float, esperadas: int) -> None:
    assert _medir([_persona(), _casco(cx, 280)], [])["total"].esperadas == esperadas


def test_sin_personas_no_hay_cabezas_esperadas_y_el_recall_es_none() -> None:
    m = _medir([_casco(192, 280)], [_cabeza(192, 280)])["total"]
    assert (m.esperadas, m.recall, m.sin_persona) == (0, None, 1)


def test_un_casco_de_otra_imagen_no_se_asocia() -> None:
    tam = {"a.jpg": (1024, 1024), "b.jpg": (1024, 1024)}
    m = _medir([_persona(), _casco(192, 280, "b.jpg")], [], tam=tam)["total"]
    assert m.esperadas == 1


# -- el emparejamiento de la predicción -------------------------------------------------------


@pytest.mark.parametrize(
    ("cx", "cy", "aciertos", "sin_persona"),
    [
        (192.0, 332.0, 1, 0),  # centro justo dentro de la franja (abajo)
        (192.0, 334.0, 0, 1),  # justo fuera
        (128.0, 280.0, 1, 0),  # borde izquierdo exacto: dentro
        (127.0, 280.0, 0, 1),
        (256.0, 280.0, 1, 0),  # borde derecho exacto: dentro
        (257.0, 280.0, 0, 1),
    ],
)
def test_la_prediccion_se_empareja_por_el_centro_en_la_franja_no_por_iou(
    cx: float, cy: float, aciertos: int, sin_persona: int
) -> None:
    m = _medir([_persona()], [_cabeza(cx, cy)])["total"]
    assert (m.aciertos, m.sin_persona, m.predichas) == (aciertos, sin_persona, 1)
    assert m.recall == (1.0 if aciertos else 0.0)


def test_el_iou_contra_la_persona_no_cuenta() -> None:
    # Una caja de cabeza mide 16 x 16 contra 128 x 256: IoU 0,008. Acierta igual.
    m = _medir([_persona()], [_cabeza(192, 280)])["total"]
    assert m.aciertos == 1


def test_dos_cabezas_sobre_la_misma_persona_son_un_acierto_y_una_duplicada() -> None:
    m = _medir([_persona()], [_cabeza(180, 280, 0.75), _cabeza(200, 290, 0.5)])["total"]
    assert (m.esperadas, m.aciertos, m.duplicadas, m.predichas) == (1, 1, 1, 2)
    assert m.recall == 1.0  # el recall no sube por duplicar


def test_cabeza_sobre_persona_con_casco_es_falso_positivo_y_no_acierta_a_nadie() -> None:
    m = _medir([_persona(), _casco(192, 280)], [_cabeza(192, 280)])["total"]
    assert (m.esperadas, m.aciertos, m.falsos_positivos) == (0, 0, 1)


def test_con_dos_personas_encimadas_gana_la_franja_de_centro_mas_cercano() -> None:
    # B está 64 px a la derecha de A: las franjas se solapan en x = 192..256. Un casco en la franja
    # de A la deja con casco; la cabeza en x = 200 cae en las dos, pero su centro está más cerca de
    # la franja de B (centro x = 256) que de la de A (192): es de B, que no tiene casco.
    a, b = _persona(128), _persona(192)
    m = _medir([a, b, _casco(150, 280)], [_cabeza(240, 280)])["total"]
    assert (m.esperadas, m.aciertos, m.falsos_positivos) == (1, 1, 0)


# -- el umbral de confianza de la predicción -------------------------------------------------


@pytest.mark.parametrize(("score", "cuenta"), [(0.5, 1), (0.4375, 0), (0.5625, 1)])
def test_el_umbral_incluye_el_score_justo_y_deja_fuera_el_de_abajo(
    score: float, cuenta: int
) -> None:
    m = _medir([_persona()], [_cabeza(192, 280, score)], umbral=0.5)["total"]
    assert (m.predichas, m.aciertos) == (cuenta, cuenta)


@pytest.mark.parametrize("umbral", [0.0, -0.25, 1.5])
def test_umbral_invalido_detiene(umbral: float) -> None:
    with pytest.raises(ValueError, match="umbral"):
        _medir([_persona()], [], umbral=umbral)


def test_prediccion_sin_score_detiene() -> None:
    sin_score = CajaPx("a.jpg", "cabeza", 184, 272, 16, 16)
    with pytest.raises(ValueError, match="score"):
        _medir([_persona()], [sin_score])


def test_solo_cuentan_las_predicciones_de_clase_cabeza() -> None:
    otra = CajaPx("a.jpg", "casco", 184, 272, 16, 16, 0.75)
    assert _medir([_persona()], [otra])["total"].predichas == 0


# -- regiones ------------------------------------------------------------------------------


def test_cada_persona_va_a_la_region_de_su_centro_y_el_total_suma_las_dos() -> None:
    dentro, fuera = _persona(128), _persona(640)
    m = _medir(
        [dentro, fuera],
        [_cabeza(192, 280), _cabeza(704, 280), _cabeza(900, 900)],
        recorte=(0, 0, 512, 1024),
    )
    assert (m["dentro"].esperadas, m["dentro"].aciertos) == (1, 1)
    assert (m["fuera"].esperadas, m["fuera"].aciertos, m["fuera"].sin_persona) == (1, 1, 1)
    assert m["total"].esperadas == 2
    assert m["total"].predichas == m["dentro"].predichas + m["fuera"].predichas == 3


# -- lectura del COCO ---------------------------------------------------------------------


def _coco_con_categorias(nombres: list[str], anotaciones: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "categories": [{"id": i, "name": n} for i, n in enumerate(nombres, start=1)],
        "images": [{"id": 1, "file_name": "a.jpg", "width": 1024, "height": 1024}],
        "annotations": anotaciones,
    }


def _anotacion(categoria: int, score: float | None = None) -> dict[str, Any]:
    a: dict[str, Any] = {"id": 1, "image_id": 1, "category_id": categoria, "bbox": [1, 2, 30, 40]}
    if score is not None:
        a["score"] = score
    return a


def test_las_categorias_de_evidencia_se_leen_aparte_y_no_entran_a_las_cajas() -> None:
    # Con `preetiquetar.py --con-evidencia`, `a_coco` lista las cinco categorías de la v3.
    nombres = ["persona", "casco", "chaleco", "cabeza", "sin_chaleco"]
    coco = leer_coco(_coco_con_categorias(nombres, [_anotacion(4, 0.75)]), predicciones=True)
    assert coco.cajas == ()
    assert [(c.clase, c.score) for c in coco.evidencia] == [("cabeza", 0.75)]


def test_un_nombre_desconocido_sigue_deteniendo() -> None:
    with pytest.raises(EntradaInvalida, match="desconocida"):
        leer_coco(_coco_con_categorias(["persona", "gorro"], []), predicciones=False)


# -- el comando ---------------------------------------------------------------------------


def _escribir(tmp_path: Path, clases: dict[str, str], cabezas: bool = False) -> list[str]:
    persona = {"id": 1, "image_id": 1, "category_id": 1, "bbox": [128, 256, 128, 256]}
    nombres = ["persona", "casco", "chaleco", "cabeza", "sin_chaleco"]
    propia = {"id": 2, "image_id": 1, "category_id": 4, "bbox": [184, 272, 16, 16]}
    verdad = _coco_con_categorias(
        nombres[:3] + (["cabeza"] if cabezas else []), [persona, *([propia] if cabezas else [])]
    )
    pred = _coco_con_categorias(nombres, [{**_anotacion(4, 0.75), "bbox": [184, 272, 16, 16]}])
    pred["info"] = {"description": "pre-etiquetas prueba / cuadro-entero"}
    rutas = {n: tmp_path / f"{n}.json" for n in ("verdad", "pred", "clases")}
    rutas["verdad"].write_text(json.dumps(verdad), encoding="utf-8")
    rutas["pred"].write_text(json.dumps(pred), encoding="utf-8")
    rutas["clases"].write_text(json.dumps({"version": "m", "clases": clases}), encoding="utf-8")
    return [
        "cabeza",
        str(rutas["verdad"]),
        str(rutas["pred"]),
        "--clases",
        str(rutas["clases"]),
        "--recorte",
        "0,0,1024,1024",
        "--salida",
        str(tmp_path / "cabeza-salida.json"),
    ]


V3 = {"0": "persona", "1": "casco", "2": "chaleco", "3": "cabeza", "4": "sin_chaleco"}


def test_de_punta_a_punta(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(_escribir(tmp_path, V3)) == 0
    datos = json.loads((tmp_path / "cabeza-salida.json").read_text(encoding="utf-8"))
    total = datos["regiones"]["total"]
    assert (total["esperadas"], total["aciertos"], total["recall"]) == (1, 1, 1.0)
    assert "| total | 1 | 1 | 1,000 |" in capsys.readouterr().out


def test_un_modelo_sin_la_clase_cabeza_detiene_en_vez_de_dar_cero(tmp_path: Path) -> None:
    v2 = {"0": "persona", "1": "casco", "2": "chaleco"}
    with pytest.raises(SystemExit, match="no tiene la clase `cabeza`"):
        main(_escribir(tmp_path, v2))
    assert not (tmp_path / "cabeza-salida.json").exists()


def test_unas_predicciones_que_no_declaran_la_categoria_cabeza_detienen(tmp_path: Path) -> None:
    # Sin `--con-evidencia`, `preetiquetar.py` escribe con las clases de CVAT (`a_coco` por
    # defecto): descarta la cabeza y no declara la categoría. Con ese archivo el recall saldría 0
    # por el escritor y no por el modelo. Este caso usa el escritor real.
    ts = datetime(2000, 1, 1, tzinfo=UTC)
    cabeza = Deteccion(ts, 1, ClaseDetectada.CABEZA, Caja(0.1, 0.1, 0.2, 0.2), 0.9)
    args = _escribir(tmp_path, V3)
    escrito = a_coco([("a.jpg", 1024, 1024, [cabeza])])
    escrito["info"] = {"description": "pre-etiquetas x / cuadro-entero"}
    Path(args[2]).write_text(json.dumps(escrito), encoding="utf-8")
    with pytest.raises(SystemExit, match="no declara la categoría `cabeza`"):
        main(args)


def test_lo_que_escribe_preetiquetar_con_evidencia_se_mide(tmp_path: Path) -> None:
    """El escritor real con las clases v3 (`preetiquetar.py --con-evidencia`) da el acierto."""
    ts = datetime(2000, 1, 1, tzinfo=UTC)
    caja = Caja(184 / 1024, 272 / 1024, 200 / 1024, 288 / 1024)  # en la franja de la persona
    cabeza = Deteccion(ts, 1, ClaseDetectada.CABEZA, caja, 0.75)
    args = _escribir(tmp_path, V3)
    escrito = a_coco([("a.jpg", 1024, 1024, [cabeza])], CLASES_V3)
    escrito["info"] = {"description": "pre-etiquetas x / cuadro-entero"}
    Path(args[2]).write_text(json.dumps(escrito), encoding="utf-8")
    assert main(args) == 0
    datos = json.loads((tmp_path / "cabeza-salida.json").read_text(encoding="utf-8"))
    total = datos["regiones"]["total"]
    assert (total["esperadas"], total["aciertos"]) == (1, 1)


def test_una_verdad_que_ya_trae_cabeza_detiene(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="ya trae la categoría `cabeza`"):
        main(_escribir(tmp_path, V3, cabezas=True))


# -- revisión de Codex (2026-10-26): cada caso reproducía un recall equivocado -----------------

HD = {"a.jpg": (1920, 1080)}


def test_la_franja_mas_cercana_se_mide_en_px_no_normalizada() -> None:
    # A y B encimadas, solo B con casco. La cabeza está a 50 px del centro de la franja de A y a
    # 60 px de la de B; normalizando cada eje por una dimensión distinta ganaba B.
    a = CajaPx("a.jpg", "persona", 400, 390, 200, 400)
    b = CajaPx("a.jpg", "persona", 340, 440, 200, 400)
    m = _medir([a, b, _casco(360, 500)], [_cabeza(500, 500)], tam=HD)["total"]
    assert (m.esperadas, m.aciertos, m.falsos_positivos) == (1, 1, 0)


@pytest.mark.parametrize(("cy", "acierta"), [(147.0, True), (148.0, True), (149.0, False)])
def test_el_borde_inferior_exacto_de_la_franja_cuenta_aunque_el_flotante_no_cierre(
    cy: float, acierta: bool
) -> None:
    # Franja de 100 a 100 + 0,3·160 = 148 px; normalizada en 1080 px quedaba un ulp bajo 148.
    persona = CajaPx("a.jpg", "persona", 128, 100, 128, 160)
    m = _medir([persona], [_cabeza(192, cy)], tam=HD)["total"]
    assert (m.aciertos, m.sin_persona) == ((1, 0) if acierta else (0, 1))


def test_un_empate_no_depende_del_orden_del_coco() -> None:
    a, b = _persona(128), _persona(192)  # el casco es de A; la cabeza equidista de las dos
    casco, cabeza = _casco(150, 280), _cabeza(224, 280)
    ab = _medir([a, b, casco], [cabeza])["total"]
    ba = _medir([b, a, casco], [cabeza])["total"]
    assert ab == ba
    assert (ab.aciertos, ab.falsos_positivos) == (0, 1)  # gana la caja de menor x: A


@pytest.mark.parametrize("score", [1.5, -0.25, math.nan, math.inf])
def test_un_score_fuera_de_rango_o_no_finito_detiene(score: float) -> None:
    with pytest.raises(ValueError, match="score fuera de"):
        _medir([_persona()], [_cabeza(192, 280, score)])


@pytest.mark.parametrize(("score", "umbral", "aciertos"), [(0.0, 0.5, 0), (1.0, 1.0, 1)])
def test_los_extremos_validos_del_score_y_del_umbral(
    score: float, umbral: float, aciertos: int
) -> None:
    assert _medir([_persona()], [_cabeza(192, 280, score)], umbral=umbral)["total"].aciertos == (
        aciertos
    )


def test_una_verdad_que_declara_cabeza_sin_anotarla_tambien_detiene(tmp_path: Path) -> None:
    args = _escribir(tmp_path, V3)
    verdad = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    verdad["categories"].append({"id": 9, "name": "cabeza"})
    Path(args[1]).write_text(json.dumps(verdad), encoding="utf-8")
    with pytest.raises(SystemExit, match="ya trae la categoría `cabeza`"):
        main(args)
    assert not (tmp_path / "cabeza-salida.json").exists()


def test_la_limitacion_declara_los_dos_sesgos_y_no_dice_piso(tmp_path: Path) -> None:
    assert main(_escribir(tmp_path, V3)) == 0
    datos = json.loads((tmp_path / "cabeza-salida.json").read_text(encoding="utf-8"))
    texto = " ".join(datos["limitaciones"])
    assert "a la baja" in texto and "al alza" in texto
    assert "piso" not in texto
