"""Revisión de una exportación «CVAT for images 1.1» (annotations.xml).

Los umbrales se prueban justo en el borde, a cada lado y con entradas inválidas. Las cifras son
diádicas (0,25; 0,5; 0,75; mitades de píxel) para que la aritmética sea exacta.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gepp_vision.etiquetado import MINIMO_PX, minimo_px
from gepp_vision.revision_etiquetas import (
    CajaEtiquetada,
    ErrorExportacion,
    Regla,
    contiene_persona,
    iou,
    leer_cvat_xml,
    resumen,
    revisar,
)

from scripts.revisar_etiquetas import main  # type: ignore[import-not-found]

#: (clase, x1, y1, x2, y2) o con `puesto` al final. Sin él, casco y chaleco salen con `si`.
Caja = tuple[str, float, float, float, float] | tuple[str, float, float, float, float, str]


def _xml(*cuadros: tuple[list[Caja], list[str]]) -> str:
    """Un annotations.xml mínimo. Cada cuadro: (cajas, etiquetas de imagen)."""
    partes = ['<?xml version="1.0" encoding="utf-8"?><annotations><version>1.1</version>']
    for i, (cajas, etiquetas) in enumerate(cuadros):
        partes.append(f'<image id="{i}" name="f{i}.jpg" width="1920" height="1080">')
        for caja in cajas:
            clase, x1, y1, x2, y2 = caja[:5]
            puesto = caja[5] if len(caja) == 6 else "si"
            atributo = f'<attribute name="puesto">{puesto}</attribute>'
            if clase == "persona":
                atributo = ""
            partes.append(
                f'<box label="{clase}" source="manual" occluded="0" '
                f'xtl="{x1}" ytl="{y1}" xbr="{x2}" ybr="{y2}" z_order="0">{atributo}</box>'
            )
        partes.extend(f'<tag label="{e}" source="manual"/>' for e in etiquetas)
        partes.append("</image>")
    partes.append("</annotations>")
    return "".join(partes)


def _reglas(xml: str, **kw: float) -> list[Regla]:
    return [h.regla for h in revisar(leer_cvat_xml(xml), **kw)]


def _caja(clase: str, cx: float, cy: float, ancho: float = 16, alto: float = 16) -> Caja:
    return (clase, cx - ancho / 2, cy - alto / 2, cx + ancho / 2, cy + alto / 2)


PERSONA: Caja = ("persona", 100, 100, 140, 180)  # alto 80


# --- lectura ---------------------------------------------------------------------------------


def test_lee_cajas_puesto_y_etiquetas() -> None:
    xml = (
        '<annotations><image id="3" name="a.jpg" width="1920" height="1080">'
        '<box label="casco" source="file" occluded="0" xtl="1.5" ytl="2" xbr="11.5" ybr="12" '
        'z_order="0"><attribute name="puesto">si</attribute></box>'
        '<tag label="tiene_pequenos" source="manual"/></image></annotations>'
    )
    [cuadro] = leer_cvat_xml(xml)
    assert (cuadro.id, cuadro.nombre) == (3, "a.jpg")
    assert cuadro.cajas == (CajaEtiquetada("casco", 1.5, 2, 11.5, 12, "si"),)
    assert cuadro.etiquetas == {"tiene_pequenos"}


@pytest.mark.parametrize(
    "xml",
    [
        "<annotations><image id='0'",  # mal formado
        "<otra/>",  # raíz equivocada
        _xml(([("persona", 10, 10, 5, 20)], [])),  # xbr < xtl
        _xml(([("persona", 10, 20, 20, 10)], [])),  # ybr < ytl
        _xml(([("arnes", 0, 0, 20, 20)], [])),  # clase de caja desconocida
        _xml(([], ["inventada"])),  # etiqueta de imagen desconocida
        '<annotations><image id="0"><box label="casco" xtl="a" ytl="0" xbr="1" ybr="1"/>'
        "</image></annotations>",  # coordenada no numérica
        '<annotations><image id="0"><box label="casco" ytl="0" xbr="1" ybr="1"/>'
        "</image></annotations>",  # falta una coordenada
        '<annotations><image name="x"/></annotations>',  # imagen sin id
        '<annotations><version>1.1</version><track id="0" label="casco"/></annotations>',
        "<annotations><version>1.1</version></annotations>",  # ningún <image>
        '<annotations><image id="0"><box label="casco" xtl="0" ytl="0" xbr="20" ybr="20"/>'
        "</image></annotations>",  # casco sin puesto
        _xml(([("casco", 0, 0, 20, 20, "quizas")], [])),  # puesto inválido
        _xml(([("chaleco", 0, 0, 20, 20, "")], [])),  # puesto vacío
    ],
)
def test_una_exportacion_invalida_se_rechaza_en_vez_de_revisarse(xml: str) -> None:
    with pytest.raises(ErrorExportacion):
        leer_cvat_xml(xml)


def test_una_caja_de_ancho_cero_es_valida_y_cae_bajo_el_minimo() -> None:
    assert _reglas(_xml(([("casco", 5, 5, 5, 25)], ["tiene_pequenos"]))) == [
        Regla.CAJA_MINIMA,
        Regla.SIN_PERSONA,
    ]


# --- 1. pares repetidos ------------------------------------------------------------------------


def test_iou_exacto() -> None:
    a = CajaEtiquetada("casco", 0, 0, 16, 16)
    assert iou(a, CajaEtiquetada("casco", 0, 0, 16, 8)) == 0.5
    assert iou(a, CajaEtiquetada("casco", 16, 0, 32, 16)) == 0.0  # se tocan por el borde
    assert iou(a, CajaEtiquetada("casco", 0, 0, 0, 0)) == 0.0  # unión sin área propia
    sin_area = CajaEtiquetada("casco", 4, 4, 4, 4)
    assert iou(sin_area, sin_area) == 0.0  # dos cajas sin área: 0, no una división por cero


@pytest.mark.parametrize(
    ("alto_b", "hay_par"),
    [(4, False), (8, True), (12, True)],  # IoU 0,25 | 0,5 (justo el umbral) | 0,75
)
def test_par_repetido_en_el_umbral_y_a_cada_lado(alto_b: float, hay_par: bool) -> None:
    xml = _xml(([("casco", 0, 0, 16, 16), ("casco", 0, 0, 16, alto_b)], ["tiene_pequenos"]))
    todos = revisar(leer_cvat_xml(xml), umbral_iou=0.5)
    hallazgos = [h for h in todos if h.regla is Regla.PAR_REPETIDO]
    assert bool(hallazgos) is hay_par
    if hay_par:
        assert hallazgos[0].iou == 16 * alto_b / 256
        assert len(hallazgos[0].cajas) == 2


@pytest.mark.parametrize(
    ("alto_b", "hay_par"),
    [(15, False), (16, True), (17.5, True)],  # IoU 0,75 | 0,8 justo (320/400) | 0,875
)
def test_par_repetido_por_defecto_en_0_8_justo(alto_b: float, hay_par: bool) -> None:
    # A = 20x20 (400) y B = 20 x alto_b con el mismo origen: IoU = min(alto_b, 20) / 20
    xml = _xml(([("persona", 0, 0, 20, 20), ("persona", 0, 0, 20, alto_b)], []))
    assert (Regla.PAR_REPETIDO in _reglas(xml)) is hay_par


def test_par_repetido_con_el_umbral_por_defecto_sobre_0_8() -> None:
    xml = _xml(([("casco", 0, 0, 16, 16), ("casco", 0, 0, 16, 14)], []))  # IoU 14/16 = 0,875
    [h] = [h for h in revisar(leer_cvat_xml(xml)) if h.regla is Regla.PAR_REPETIDO]
    assert h.iou == 0.875


def test_el_par_trae_las_coordenadas_de_las_dos_cajas_distintas() -> None:
    xml = _xml(([("casco", 0, 0, 16, 16), ("casco", 2, 0, 18, 16)], ["tiene_pequenos"]))
    [h] = [h for h in revisar(leer_cvat_xml(xml), umbral_iou=0.75) if h.regla is Regla.PAR_REPETIDO]
    assert [(c.x1, c.y1, c.x2, c.y2) for c in h.cajas] == [(0, 0, 16, 16), (2, 0, 18, 16)]
    assert h.iou == 14 * 16 / (2 * 256 - 14 * 16)  # 224 / 288


def test_par_repetido_no_cruza_clases_ni_cuadros() -> None:
    misma_caja = ("casco", 0, 0, 16, 16)
    otra_clase = ("chaleco", 0, 0, 16, 16)
    xml = _xml(([misma_caja, otra_clase, PERSONA], []), ([misma_caja], []))
    assert Regla.PAR_REPETIDO not in _reglas(xml)


def test_par_repetido_por_defecto_pide_0_8() -> None:
    # IoU 0,75: por debajo del 0,8 por defecto, por encima de un 0,5 explícito
    xml = _xml(([("casco", 0, 0, 16, 16), ("casco", 0, 0, 16, 12)], []))
    assert Regla.PAR_REPETIDO not in _reglas(xml)
    assert Regla.PAR_REPETIDO in _reglas(xml, umbral_iou=0.5)


@pytest.mark.parametrize("umbral", [0, -0.5, 1.5])
def test_umbral_iou_invalido(umbral: float) -> None:
    with pytest.raises(ValueError, match="umbral_iou"):
        revisar([], umbral_iou=umbral)


def test_umbral_iou_1_exige_cajas_identicas() -> None:
    xml = _xml(([("casco", 0, 0, 16, 16), ("casco", 0, 0, 16, 16)], []))
    assert Regla.PAR_REPETIDO in _reglas(xml, umbral_iou=1)


# --- 2. y 3. mínimo por clase y tiene_pequenos ------------------------------------------------


def test_el_minimo_es_el_de_a_coco() -> None:
    # si cambia la guía (§4.2), estos casos de borde se reescriben a propósito
    assert MINIMO_PX == 10
    assert (minimo_px("persona"), minimo_px("chaleco"), minimo_px("casco")) == (10, 10, 8)


@pytest.mark.parametrize(
    ("clase", "ancho", "alto", "bajo"),
    [
        ("persona", 10, 10, False),
        ("persona", 9.75, 30, True),
        ("persona", 30, 9.75, True),
        ("chaleco", 10, 30, False),
        ("chaleco", 9.75, 30, True),
        ("casco", 8, 8, False),  # justo en el mínimo del casco
        ("casco", 8.25, 30, False),
        ("casco", 9.75, 9.75, False),  # bajo 10 pero no bajo 8
        ("casco", 7.75, 30, True),
        ("casco", 30, 7.75, True),
    ],
)
def test_caja_minima_justo_en_el_borde_y_a_cada_lado(
    clase: str, ancho: float, alto: float, bajo: bool
) -> None:
    xml = _xml(([(clase, 0, 0, ancho, alto)], []))
    assert (Regla.CAJA_MINIMA in _reglas(xml)) is bajo


def test_el_minimo_vale_para_todas_las_clases() -> None:
    xml = _xml(([("persona", 0, 0, 5, 5), ("chaleco", 0, 0, 5, 5), ("casco", 0, 0, 5, 5)], []))
    clases = [h.clase for h in revisar(leer_cvat_xml(xml)) if h.regla is Regla.CAJA_MINIMA]
    assert clases == ["persona", "chaleco", "casco"]


@pytest.mark.parametrize(
    ("etiquetas", "hay_hallazgo"),
    [([], True), (["tiene_pequenos"], False), (["grupo_denso"], True)],
)
def test_casco_chico_pide_tiene_pequenos(etiquetas: list[str], hay_hallazgo: bool) -> None:
    xml = _xml(([PERSONA, _caja("casco", 120, 100, 7.5, 7.5)], etiquetas))
    assert (Regla.FALTA_TIENE_PEQUENOS in _reglas(xml)) is hay_hallazgo


@pytest.mark.parametrize("clase", ["persona", "chaleco", "casco"])
def test_tiene_pequenos_se_exige_por_cualquier_clase_bajo_el_minimo(clase: str) -> None:
    sin = _xml(([(clase, 0, 0, 5, 5)], []))
    [h] = [h for h in revisar(leer_cvat_xml(sin)) if h.regla is Regla.FALTA_TIENE_PEQUENOS]
    assert (h.clase, h.cajas[0].ancho) == (clase, 5)
    con = _xml(([(clase, 0, 0, 5, 5)], ["tiene_pequenos"]))
    assert Regla.FALTA_TIENE_PEQUENOS not in _reglas(con)


def test_tiene_pequenos_una_caja_chica_basta_y_las_normales_no_la_piden() -> None:
    assert Regla.FALTA_TIENE_PEQUENOS not in _reglas(_xml(([PERSONA], [])))
    chica = ("persona", 0, 0, 5, 5)
    assert _reglas(_xml(([PERSONA, chica], []))).count(Regla.FALTA_TIENE_PEQUENOS) == 1


@pytest.mark.parametrize("lado", [8, 8.25, 9.75, 10])
def test_casco_desde_8_px_no_pide_tiene_pequenos(lado: float) -> None:
    xml = _xml(([PERSONA, _caja("casco", 120, 100, lado, lado)], []))
    assert Regla.FALTA_TIENE_PEQUENOS not in _reglas(xml)


def test_casco_de_8_px_exactos_con_coordenadas_decimales_no_es_bajo_el_minimo() -> None:
    assert 8.2 - 0.2 < 8  # el defecto de flotantes: 7,999999999999999
    xml = (
        '<annotations><image id="0" name="a.jpg">'
        '<box label="persona" xtl="0" ytl="0" xbr="40" ybr="100"/>'
        '<box label="casco" xtl="0.2" ytl="0" xbr="8.2" ybr="20">'
        '<attribute name="puesto">si</attribute></box></image></annotations>'
    )
    assert _reglas(xml) == []


def test_casco_de_7_75_px_si_pide_tiene_pequenos() -> None:
    xml = _xml(([PERSONA, _caja("casco", 120, 100, 7.75, 7.75)], []))
    assert Regla.FALTA_TIENE_PEQUENOS in _reglas(xml)


def test_tiene_pequenos_se_evalua_por_cuadro() -> None:
    chico = _caja("casco", 120, 100, 7.5, 7.5)
    xml = _xml(([PERSONA, chico], ["tiene_pequenos"]), ([PERSONA, chico], []))
    hallazgos = [h for h in revisar(leer_cvat_xml(xml)) if h.regla is Regla.FALTA_TIENE_PEQUENOS]
    assert [h.cuadro for h in hallazgos] == [1]


# --- 4. casco o chaleco sin persona ----------------------------------------------------------


def test_contiene_persona_con_margen_hacia_arriba() -> None:
    p = CajaEtiquetada(*PERSONA)  # y1=100, alto 80 -> con 0,25, tope en 80

    def obj(cy: float) -> CajaEtiquetada:
        return CajaEtiquetada("casco", 110, cy - 4, 130, cy + 4)

    assert contiene_persona(p, obj(80), margen_cabeza=0.25)  # justo en el tope
    assert not contiene_persona(p, obj(79.5), margen_cabeza=0.25)  # medio píxel más arriba
    assert contiene_persona(p, obj(80.5), margen_cabeza=0.25)
    assert not contiene_persona(p, obj(99.5), margen_cabeza=0)  # sin margen, bajo y1 no vale
    assert contiene_persona(p, obj(100), margen_cabeza=0)


@pytest.mark.parametrize(
    ("cx", "cy", "dentro"),
    [
        (120, 80, True),  # tope con margen 0,25
        (120, 79.5, False),
        (120, 180, True),  # pie de la persona
        (120, 180.5, False),  # no se amplía hacia abajo
        (100, 120, True),  # borde izquierdo
        (99.5, 120, False),
        (140, 120, True),  # borde derecho
        (140.5, 120, False),  # no se amplía hacia los lados
    ],
)
@pytest.mark.parametrize("clase", ["casco", "chaleco"])
def test_sin_persona_en_los_bordes(clase: str, cx: float, cy: float, dentro: bool) -> None:
    xml = _xml(([PERSONA, _caja(clase, cx, cy)], []))
    assert (Regla.SIN_PERSONA not in _reglas(xml, margen_cabeza=0.25)) is dentro


def test_sin_persona_sin_ninguna_persona_en_el_cuadro() -> None:
    assert _reglas(_xml(([_caja("casco", 120, 120)], []))) == [Regla.SIN_PERSONA]


def test_la_persona_de_otro_cuadro_no_cuenta() -> None:
    xml = _xml(([PERSONA], []), ([_caja("casco", 120, 120)], []))
    assert [h.cuadro for h in revisar(leer_cvat_xml(xml))] == [1]


def test_basta_una_persona_que_lo_contenga() -> None:
    lejos = ("persona", 500, 500, 540, 580)
    assert Regla.SIN_PERSONA not in _reglas(_xml(([lejos, PERSONA, _caja("casco", 120, 120)], [])))


@pytest.mark.parametrize(
    ("clase", "puesto", "hay_hallazgo"),
    [
        ("casco", "si", True),
        ("casco", "no", False),
        ("chaleco", "si", True),
        ("chaleco", "no", False),
    ],
)
def test_sin_persona_solo_para_lo_puesto(clase: str, puesto: str, hay_hallazgo: bool) -> None:
    """Guía §5: el casco en el suelo o en un perchero es `puesto = no` y no se asocia a nadie."""
    xml = _xml(([(*_caja(clase, 500, 500), puesto)], []))
    assert (Regla.SIN_PERSONA in _reglas(xml)) is hay_hallazgo


def test_lo_no_puesto_con_persona_tampoco_es_hallazgo() -> None:
    assert _reglas(_xml(([PERSONA, (*_caja("casco", 120, 120), "no")], []))) == []


def test_una_persona_sola_no_es_hallazgo() -> None:
    assert _reglas(_xml(([PERSONA], []))) == []


@pytest.mark.parametrize("margen", [-0.25, float("nan"), float("inf"), float("-inf")])
def test_margen_cabeza_invalido(margen: float) -> None:
    with pytest.raises(ValueError, match="margen_cabeza"):
        revisar([], margen_cabeza=margen)


@pytest.mark.parametrize("umbral", [float("nan"), float("inf"), float("-inf")])
def test_umbral_iou_no_finito(umbral: float) -> None:
    with pytest.raises(ValueError, match="umbral_iou"):
        revisar([], umbral_iou=umbral)


@pytest.mark.parametrize("valor", ["nan", "inf", "-inf"])
@pytest.mark.parametrize("atributo", ["xtl", "ytl", "xbr", "ybr"])
def test_coordenada_no_finita_se_rechaza(atributo: str, valor: str) -> None:
    caja = {"xtl": "0", "ytl": "0", "xbr": "20", "ybr": "20", atributo: valor}
    xml = (
        '<annotations><image id="0"><box label="casco" '
        + " ".join(f'{k}="{v}"' for k, v in caja.items())
        + "/></image></annotations>"
    )
    with pytest.raises(ErrorExportacion, match="no finito"):
        leer_cvat_xml(xml)


# --- resumen y script --------------------------------------------------------------------------


def _exportacion(tmp_path: Path) -> Path:
    xml = _xml(
        ([PERSONA, _caja("casco", 120, 100, 7.5, 7.5)], []),  # chico sin tiene_pequenos
        ([_caja("chaleco", 300, 300)], ["tiene_pequenos"]),  # sin persona
    )
    ruta = tmp_path / "annotations.xml"
    ruta.write_text(xml, encoding="utf-8")
    return ruta


def test_resumen_cuenta_hallazgos_y_cuadros_distintos() -> None:
    hallazgos = revisar(leer_cvat_xml(_xml(([_caja("casco", 0, 0), _caja("casco", 0, 0)], []))))
    assert resumen(iter(hallazgos)) == {
        "par_repetido": {"hallazgos": 1, "cuadros": 1},
        "caja_minima": {"hallazgos": 0, "cuadros": 0},
        "falta_tiene_pequenos": {"hallazgos": 0, "cuadros": 0},
        "sin_persona": {"hallazgos": 2, "cuadros": 1},
    }


def test_script_json_trae_cuadro_clase_y_coordenadas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(_exportacion(tmp_path)), "--json"]) == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["cuadros"] == 2
    assert salida["resumen"]["caja_minima"] == {"hallazgos": 1, "cuadros": 1}
    por_regla = {h["regla"]: h for h in salida["hallazgos"]}
    assert por_regla["falta_tiene_pequenos"]["cuadro"] == 0
    assert por_regla["falta_tiene_pequenos"]["clase"] == "casco"
    assert por_regla["falta_tiene_pequenos"]["cajas"] == [[116.25, 96.25, 123.75, 103.75]]
    assert por_regla["sin_persona"]["cuadro"] == 1


def test_script_json_trae_las_dos_cajas_distintas_del_par(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ruta = tmp_path / "par.xml"
    ruta.write_text(
        _xml(([("casco", 0, 0, 16, 16), ("casco", 2, 0, 18, 16)], ["tiene_pequenos"])),
        encoding="utf-8",
    )
    assert main([str(ruta), "--iou", "0.75", "--json"]) == 0
    hallazgos = json.loads(capsys.readouterr().out)["hallazgos"]
    [h] = [h for h in hallazgos if h["regla"] == "par_repetido"]
    assert h["cajas"] == [[0, 0, 16, 16], [2, 0, 18, 16]]


@pytest.mark.parametrize(
    "contenido",
    [
        '<annotations><version>1.1</version><track id="0" label="persona"/></annotations>',
        "<annotations><version>1.1</version></annotations>",
    ],
)
def test_script_formato_incompatible_sale_con_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], contenido: str
) -> None:
    ruta = tmp_path / "video.xml"
    ruta.write_text(contenido, encoding="utf-8")
    assert main([str(ruta)]) == 2
    assert "error:" in capsys.readouterr().err


def test_el_error_de_video_nombra_el_formato_correcto() -> None:
    with pytest.raises(ErrorExportacion, match=r"CVAT for images 1\.1"):
        leer_cvat_xml("<annotations><track id='0'/></annotations>")


def test_script_tabla_y_parametros(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(_exportacion(tmp_path)), "--iou", "0.5", "--margen-cabeza", "0.25"]) == 0
    salida = capsys.readouterr().out
    assert "falta_tiene_pequenos" in salida
    assert "116.25,96.25,123.75,103.75" in salida
    assert "2 cuadros, IoU >= 0.5, margen de cabeza 0.25" in salida


def test_script_sin_hallazgos_no_imprime_tabla(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ruta = tmp_path / "limpio.xml"
    ruta.write_text(_xml(([PERSONA], [])), encoding="utf-8")
    assert main([str(ruta)]) == 0
    salida = capsys.readouterr().out
    assert salida.startswith("1 cuadros")
    assert " 0 hallazgos" in salida


@pytest.mark.parametrize(
    "argumentos",
    [["--iou", "0"], ["--iou", "nan"], ["--margen-cabeza", "-0.25"], ["--margen-cabeza", "nan"]],
)
def test_script_umbral_invalido_sale_con_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argumentos: list[str]
) -> None:
    assert main([str(_exportacion(tmp_path)), *argumentos]) == 2
    assert "error:" in capsys.readouterr().err


def test_script_xml_malo_o_ausente_sale_con_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    malo = tmp_path / "malo.xml"
    malo.write_text("<annotations><image", encoding="utf-8")
    assert main([str(malo)]) == 2
    assert main([str(tmp_path / "no_existe.xml")]) == 2
    assert capsys.readouterr().err.count("error:") == 2


# --- de la revisión de Lucca (salida y lectura) ------------------------------------------------


def _par(tmp_path: Path) -> Path:
    # dos cascos idénticos de 16x16 con una persona que los contiene, una etiqueta y tildes
    xml = _xml(([PERSONA, _caja("casco", 120, 100), _caja("casco", 120, 100)], ["grupo_denso"]))
    ruta = tmp_path / "ñandú.xml"
    ruta.write_text(xml.replace("f0.jpg", "cámara.jpg"), encoding="utf-8")
    return ruta


def test_json_trae_parametros_nombre_e_iou(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(_par(tmp_path)), "--iou", "0.5", "--margen-cabeza", "0.25", "--json"]) == 0
    bruto = capsys.readouterr().out
    salida = json.loads(bruto)
    assert (salida["umbral_iou"], salida["margen_cabeza"]) == (0.5, 0.25)
    [h] = [h for h in salida["hallazgos"] if h["regla"] == "par_repetido"]
    assert (h["nombre"], h["iou"], len(h["cajas"])) == ("cámara.jpg", 1.0, 2)
    assert "cámara" in bruto  # sin escapar la á


def test_json_redondea_el_iou_a_4_decimales(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 12x12 contra 12x4: IoU 1/3, que no es exacto y deja ver el corte
    xml = _xml(([("casco", 0, 0, 12, 12), ("casco", 0, 0, 12, 4)], ["tiene_pequenos"]))
    ruta = tmp_path / "a.xml"
    ruta.write_text(xml, encoding="utf-8")
    assert main([str(ruta), "--iou", "0.25", "--json"]) == 0
    salida = json.loads(capsys.readouterr().out)
    [h] = [h for h in salida["hallazgos"] if h["regla"] == "par_repetido"]
    assert h["iou"] == 0.3333


def test_tabla_muestra_iou_y_ambas_cajas_del_par(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(_par(tmp_path)), "--iou", "0.5"]) == 0
    fila = next(f for f in capsys.readouterr().out.splitlines() if f.startswith("par_repetido"))
    assert fila.split()[1:3] == ["0", "casco"]  # columnas: cuadro, clase
    assert fila.count("|") == 1
    assert fila.endswith("(IoU 1.00)")


def test_el_script_pasa_margen_cabeza_a_la_regla(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # casco con centro 10 px sobre la persona (alto 80): lo contiene con margen 0,25, no con 0
    ruta = tmp_path / "a.xml"
    ruta.write_text(_xml(([PERSONA, _caja("casco", 120, 90)], [])), encoding="utf-8")
    main([str(ruta), "--margen-cabeza", "0.25", "--json"])
    con = json.loads(capsys.readouterr().out)["resumen"]["sin_persona"]["hallazgos"]
    main([str(ruta), "--margen-cabeza", "0", "--json"])
    sin = json.loads(capsys.readouterr().out)["resumen"]["sin_persona"]["hallazgos"]
    assert (con, sin) == (0, 1)


def test_iou_de_una_caja_plana_en_y_no_divide_por_cero() -> None:
    plana = CajaEtiquetada("casco", 0, 5, 16, 5)  # alto 0, ancho > 0
    assert iou(plana, plana) == 0.0


def test_todas_las_etiquetas_de_imagen_se_leen() -> None:
    [cuadro] = leer_cvat_xml(_xml(([], ["tiene_pequenos", "grupo_denso", "negativo_duro"])))
    assert cuadro.etiquetas == {"tiene_pequenos", "grupo_denso", "negativo_duro"}


def test_tiene_pequenos_no_es_la_primera_etiqueta() -> None:
    chico = _caja("casco", 120, 100, 7.5, 7.5)
    xml = _xml(([PERSONA, chico], ["grupo_denso", "tiene_pequenos"]))
    assert [h.regla for h in revisar(leer_cvat_xml(xml))] == [Regla.CAJA_MINIMA]
