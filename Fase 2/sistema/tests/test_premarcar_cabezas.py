"""`scripts/premarcar_cabezas.py`: cabezas sugeridas para CVAT, con la definición de la regla.

Cuadro de 1024 x 1024. La persona base mide 128 x 256 en (128, 256): su franja de casco es el 30 %
superior, y = 256 .. 332,8, x = 128 .. 256. El 30 % no es diádico: el borde se prueba en x (exacto)
y en y a 0,8 px de cada lado. Los scores y el umbral usan valores diádicos (0,5; 2**-10).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from gepp_core import ClaseDetectada
from gepp_vision.entrenamiento import CLASES_V3
from gepp_vision.evaluacion.coco import CajaPx, EntradaInvalida, leer_coco

from scripts.premarcar_cabezas import (  # type: ignore[import-not-found]
    IOU_REPETIDA,
    a_coco,
    cabeza_sugerida,
    main,
    premarcar,
    repite_predicha,
)

TAM = 1024
CLASES_V3_NOMBRES = [str(c) for c in CLASES_V3]
EPS = 2**-10


def _caja(clase: str, bbox: tuple[float, float, float, float], score: float = 0.75) -> dict:
    return {"clase": clase, "bbox": bbox, "score": score}


PERSONA = _caja("persona", (128, 256, 128, 256))


def _casco(cx: float, cy: float, score: float = 0.75) -> dict:
    return _caja("casco", (cx - 8, cy - 8, 16, 16), score)


def _cabeza(cx: float, cy: float, score: float = 0.75) -> dict:
    return _caja("cabeza", (cx - 8, cy - 8, 16, 16), score)


def _coco(cajas: list[dict], categorias: tuple[str, ...] = tuple(CLASES_V3_NOMBRES)) -> dict:
    ids = {n: i for i, n in enumerate(categorias, start=1)}
    return {
        "info": {"description": "modelo-falso"},
        "categories": [{"id": i, "name": n} for n, i in ids.items()],
        "images": [{"id": 1, "file_name": "a.jpg", "width": TAM, "height": TAM}],
        "annotations": [
            {
                "id": k,
                "image_id": 1,
                "category_id": ids[c["clase"]],
                "bbox": list(c["bbox"]),
                "area": c["bbox"][2] * c["bbox"][3],
                "iscrowd": 0,
                "score": c["score"],
            }
            for k, c in enumerate(cajas, start=1)
        ],
    }


def _correr(cajas: list[dict], umbral: float = 0.5, **kw: Any) -> list[tuple[str, str]]:
    """(clase, origen) de lo que sale, en el orden de salida."""
    datos = leer_coco(_coco(cajas, **kw), predicciones=True)
    salida = premarcar(datos, umbral)
    assert len(salida) == 1
    return [(c.clase, o) for c, o in salida[0][2]]


def _cabezas_px(cajas: list[dict]) -> list[tuple[CajaPx, str]]:
    datos = leer_coco(_coco(cajas), predicciones=True)
    return [(c, o) for c, o in premarcar(datos, 0.5)[0][2] if c.clase == "cabeza"]


def _cabezas(salida: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [x for x in salida if x[0] == "cabeza"]


def test_persona_con_casco_no_sugiere_cabeza() -> None:
    assert _cabezas(_correr([PERSONA, _casco(192, 280)])) == []


def test_persona_sin_casco_sugiere_una_cabeza() -> None:
    salida = _correr([PERSONA])
    assert _cabezas(salida) == [("cabeza", "sugerida")]
    assert ("persona", "predicha") in salida


@pytest.mark.parametrize(
    ("cx", "cy", "sugiere"),
    [
        (128.0, 280.0, False),  # borde izquierdo exacto: el casco cuenta
        (256.0, 280.0, False),  # borde derecho exacto
        (127.0, 280.0, True),
        (257.0, 280.0, True),
        (192.0, 332.0, False),  # justo dentro por abajo (332,8)
        (192.0, 334.0, True),  # justo fuera
    ],
)
def test_casco_en_el_borde_de_la_franja(cx: float, cy: float, sugiere: bool) -> None:
    assert bool(_cabezas(_correr([PERSONA, _casco(cx, cy)]))) is sugiere


@pytest.mark.parametrize(
    ("score_persona", "score_casco", "sugiere"),
    [
        (0.75, 0.5, False),  # el casco justo en el umbral cuenta: la persona queda protegida
        (0.5 - EPS, 0.5, None),  # la persona no llega: no hay persona, ni cabeza
        (0.5 + EPS, 0.5 - EPS, True),  # el casco no llega: no cuenta, la persona queda sin casco
        (0.5 + EPS, 0.5 + EPS, False),
    ],
)
def test_score_en_el_umbral_y_a_cada_lado(
    score_persona: float, score_casco: float, sugiere: bool | None
) -> None:
    persona = _caja("persona", PERSONA["bbox"], score_persona)
    salida = _correr([persona, _casco(192, 280, score_casco)], umbral=0.5)
    if sugiere is None:
        assert [c for c, _ in salida if c in ("persona", "cabeza")] == []
    else:
        assert bool(_cabezas(salida)) is sugiere


def test_persona_justo_en_el_umbral_cuenta() -> None:
    assert _cabezas(_correr([_caja("persona", PERSONA["bbox"], 0.5)], umbral=0.5))


@pytest.mark.parametrize("umbral", [0.0, -0.5, 1.0 + EPS, math.nan, math.inf])
def test_umbral_invalido(umbral: float) -> None:
    with pytest.raises(ValueError, match="umbral"):
        premarcar(leer_coco(_coco([PERSONA]), predicciones=True), umbral)


def test_umbral_uno_es_valido() -> None:
    assert _cabezas(_correr([_caja("persona", PERSONA["bbox"], 1.0)], umbral=1.0))


@pytest.mark.parametrize("falta", ["persona", "casco"])
def test_coco_sin_persona_o_casco_es_un_error_claro(falta: str) -> None:
    categorias = tuple(n for n in CLASES_V3_NOMBRES if n != falta)
    with pytest.raises(EntradaInvalida, match="persona y casco"):
        _correr([], categorias=categorias)


@pytest.mark.parametrize("score", [1.0 + EPS, -EPS, math.nan])
def test_score_fuera_de_rango_es_un_error(score: float) -> None:
    with pytest.raises(EntradaInvalida, match="score"):
        _correr([_caja("persona", PERSONA["bbox"], score)])


def test_la_geometria_es_la_medida_en_epp_v3() -> None:
    datos = leer_coco(_coco([PERSONA]), predicciones=True)
    coco = a_coco(premarcar(datos, 0.5), "m")
    sugerida = next(n for n in coco["annotations"] if n["origen"] == "sugerida")
    ancho, alto = 0.444 * 128, 0.18 * 256
    x, y, w, h = sugerida["bbox"]
    assert (w, h) == pytest.approx((ancho, alto))
    assert x + w / 2 == pytest.approx(192)  # centrada en la persona
    assert y == 256  # pegada al borde superior
    assert sugerida["attributes"] == {"origen": "sugerida"}
    assert "score" not in sugerida
    assert sugerida["category_id"] == CLASES_V3[ClaseDetectada.CABEZA]


def test_la_sugerida_se_recorta_a_la_imagen() -> None:
    persona = _caja("persona", (-20, -10, 128, 256))
    datos = leer_coco(_coco([persona]), predicciones=True)
    (caja, _), *_ = (c for c in premarcar(datos, 0.5)[0][2] if c[0].clase == "cabeza")
    assert caja.x >= 0 and caja.y >= 0


def test_la_cabeza_predicha_reemplaza_a_la_sugerida() -> None:
    assert _cabezas(_correr([PERSONA, _cabeza(192, 270)])) == [("cabeza", "predicha")]


def test_una_segunda_predicha_en_la_misma_franja_se_descarta() -> None:
    salida = _correr([PERSONA, _cabeza(192, 270, 0.75), _cabeza(200, 275, 0.625)])
    assert _cabezas(salida) == [("cabeza", "predicha")]


def test_la_predicha_bajo_el_umbral_no_reemplaza() -> None:
    salida = _correr([PERSONA, _cabeza(192, 270, 0.5 - EPS)])
    assert _cabezas(salida) == [("cabeza", "sugerida")]


def test_una_predicha_lejos_de_toda_persona_no_borra_la_sugerida() -> None:
    salida = _correr([PERSONA, _cabeza(700, 700)])
    assert sorted(_cabezas(salida)) == [("cabeza", "predicha"), ("cabeza", "sugerida")]


# Dos personas encimadas, sin cascos: A en x 0..100 (franja de centro (50, 30)), B en x 50..150
# (centro (100, 30)). Una cabeza es de la más cercana de las dos, no de la primera libre.
A = _caja("persona", (0, 0, 100, 200))
B = _caja("persona", (50, 0, 100, 200))


def test_una_duplicada_no_borra_la_sugerida_de_otra_persona() -> None:
    # Las dos cabezas están más cerca de A: la segunda es duplicada y B conserva su sugerida.
    cabezas = _cabezas_px([A, B, _cabeza(60, 25, 0.75), _cabeza(65, 25, 0.625)])
    assert sorted(o for _, o in cabezas) == ["predicha", "sugerida"]
    sugerida = next(c for c, o in cabezas if o == "sugerida")
    assert sugerida.x + sugerida.ancho / 2 == pytest.approx(100)  # la de B, centrada en x=100


def test_la_cabeza_es_de_la_persona_mas_cercana() -> None:
    # Una cabeza en el centro de B: A conserva su sugerida (centrada en x=50), B no.
    cabezas = _cabezas_px([A, B, _cabeza(100, 25)])
    assert sorted(o for _, o in cabezas) == ["predicha", "sugerida"]
    sugerida = next(c for c, o in cabezas if o == "sugerida")
    assert sugerida.x + sugerida.ancho / 2 == pytest.approx(50)


def test_caso_mixto_la_predicha_de_una_con_casco_cubre_a_la_sin_casco() -> None:
    # La cabeza cae en la franja de A (sin casco) y de B (con casco); su dueña es B. A no recibe
    # una sugerida idéntica a la predicha.
    sin = _caja("persona", (0, 100, 125, 200), 0.875)
    con = _caja("persona", (0, 90, 125, 150), 0.875)
    cajas = [sin, con, _caja("casco", (57.5, 90, 10, 10), 0.875)]
    cajas.append(_caja("cabeza", (34.75, 100, 55.5, 36), 0.875))
    assert [o for _, o in _cabezas_px(cajas)] == ["predicha"]


def test_dos_sin_casco_encimadas_no_repiten_la_cabeza() -> None:
    # Caso 10: la dueña es B, que reclama la predicha; la sugerida de A sería idéntica (IoU 1).
    a = _caja("persona", (0, 100, 125, 200), 0.875)
    b = _caja("persona", (0, 90, 125, 150), 0.875)
    cabezas = _cabezas_px([a, b, _caja("cabeza", (34.75, 100, 55.5, 36), 0.875)])
    assert [o for _, o in cabezas] == ["predicha"]


def test_una_predicha_que_no_se_solapa_no_borra_la_sugerida() -> None:
    # Caso 11: la predicha es de B (con casco) y su centro cae en la franja de A, pero IoU 0.
    a = _caja("persona", (0, 100, 200, 400), 0.875)
    b = _caja("persona", (150, 90, 100, 200), 0.875)
    cajas = [a, b, _caja("casco", (200, 90, 10, 10), 0.875)]
    cajas.append(_caja("cabeza", (180, 110, 20, 20), 0.875))
    assert sorted(o for _, o in _cabezas_px(cajas)) == ["predicha", "sugerida"]


@pytest.mark.parametrize(
    ("alto_predicha", "repite"),
    [(8.0 - 1 / 16, False), (8.0, True), (8.0 + 1 / 16, True)],  # IoU 127/256, 128/256, 129/256
)
def test_el_iou_justo_en_el_umbral_y_a_cada_lado(alto_predicha: float, repite: bool) -> None:
    sugerida = CajaPx("a.jpg", "cabeza", 0, 0, 16, 16)
    predicha = CajaPx("a.jpg", "cabeza", 0, 0, 16, alto_predicha, 0.75)
    assert IOU_REPETIDA == 0.5
    assert repite_predicha(sugerida, [predicha]) is repite
    assert not repite_predicha(sugerida, [])


def test_la_sugerida_fuera_de_la_imagen_no_se_escribe_ni_se_corre() -> None:
    afuera = CajaPx("a.jpg", "persona", 1010, 10, 128, 256)
    assert cabeza_sugerida(afuera, TAM, TAM) is None  # x1 = 1045,6 > 1024: ancho negativo antes
    arriba = cabeza_sugerida(CajaPx("a.jpg", "persona", -20, -10, 128, 256), TAM, TAM)
    assert arriba is not None
    assert (arriba.y, arriba.alto) == (0, pytest.approx(0.18 * 256 - 10))  # 36,08 y no 46,08
    borde = cabeza_sugerida(CajaPx("a.jpg", "persona", 950, 10, 128, 256), TAM, TAM)
    assert borde is not None
    assert borde.x + borde.ancho == 1024  # recortada por la derecha, sin correrse


def test_la_predicha_sobre_persona_con_casco_o_sin_persona_se_conserva_marcada() -> None:
    con_casco = _correr([PERSONA, _casco(192, 280), _cabeza(192, 270)])
    suelta = _correr([_cabeza(700, 700)])
    assert _cabezas(con_casco) == [("cabeza", "predicha")]
    assert _cabezas(suelta) == [("cabeza", "predicha")]


def test_main_escribe_un_coco_importable(tmp_path: Path) -> None:
    pred, salida = tmp_path / "p.json", tmp_path / "s.json"
    clases = tmp_path / "m.clases.json"
    pred.write_text(json.dumps(_coco([PERSONA])), encoding="utf-8")
    nombres = {str(i): n for i, n in enumerate(CLASES_V3_NOMBRES)}
    clases.write_text(json.dumps({"version": "m", "clases": nombres}), encoding="utf-8")
    assert main([str(pred), str(clases), str(salida), "--umbral", "0.5"]) == 0
    leido = leer_coco(json.loads(salida.read_text(encoding="utf-8")), predicciones=False)
    assert sorted(c.clase for c in leido.cajas + leido.evidencia) == ["cabeza", "persona"]


def test_main_con_modelo_sin_casco_falla_claro(tmp_path: Path) -> None:
    pred, clases = tmp_path / "p.json", tmp_path / "m.clases.json"
    pred.write_text(json.dumps(_coco([PERSONA])), encoding="utf-8")
    clases.write_text(json.dumps({"version": "m", "clases": {"0": "persona"}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="no tiene"):
        main([str(pred), str(clases), str(tmp_path / "s.json")])
