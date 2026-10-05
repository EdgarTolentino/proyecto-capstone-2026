"""Unión de datasets públicos para entrenar (PT-08, #31).

Lo que se cuida aquí es lo que, si falla, no avisa: una clase mal traducida, una persona
sin etiquetar que el modelo aprende como fondo, o una imagen repetida entre entrenamiento y
validación que infla la métrica.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_vision.dataset import UMBRAL_DUPLICADO, Particion
from gepp_vision.entrenamiento import (
    CLASES_V1,
    CategoriaDesconocida,
    Fuente,
    _asignar,
    a_coco,
    acierto_por_id,
    acuerdo_de_clases,
    cargar_fuentes,
    completar,
    desde_coco,
    desde_voc,
    emparejar,
    grupo,
    muestra_estratificada,
    pares_con_verdad,
    particion_estable,
    quitar_fugas,
)

P, C, V = ClaseDetectada.PERSONA, ClaseDetectada.CASCO, ClaseDetectada.CHALECO

FUENTE = Fuente(
    nombre="css",
    licencia="CC BY 4.0",
    clases={"Hardhat": C, "Safety Vest": V, "Person": P, "NO-Hardhat": None},
    exhaustivas=frozenset({C, V}),
)


def _coco(*anotaciones: tuple[int, list[float]], categorias: dict[int, str] | None = None) -> dict:
    cats = categorias or {
        0: "workers",
        1: "Hardhat",
        2: "NO-Hardhat",
        3: "Person",
        4: "Safety Vest",
    }
    return {
        "images": [{"id": 7, "file_name": "a.jpg", "width": 200, "height": 100}],
        "categories": [{"id": i, "name": n} for i, n in cats.items()],
        "annotations": [
            {"id": k, "image_id": 7, "category_id": cat, "bbox": bbox}
            for k, (cat, bbox) in enumerate(anotaciones)
        ],
    }


# --- traducción de clases -------------------------------------------------------------


def test_traduce_las_clases_y_normaliza_las_cajas() -> None:
    [img] = desde_coco(_coco((1, [20, 10, 40, 30]), (4, [0, 0, 200, 100])), FUENTE)
    assert img.archivo == "a.jpg"
    assert img.cajas == [(C, Caja(0.1, 0.1, 0.3, 0.4)), (V, Caja(0.0, 0.0, 1.0, 1.0))]


def test_una_clase_mapeada_a_nada_se_descarta_a_proposito() -> None:
    [img] = desde_coco(_coco((2, [20, 10, 40, 30])), FUENTE)
    assert img.cajas == []


def test_una_categoria_que_la_fuente_no_declara_detiene_todo() -> None:
    coco = _coco((1, [0, 0, 10, 10]), (5, [0, 0, 10, 10]), categorias={1: "Hardhat", 5: "Mask"})
    with pytest.raises(CategoriaDesconocida, match="Mask"):
        desde_coco(coco, FUENTE)


def test_una_categoria_agrupadora_sin_anotaciones_no_cuenta_como_desconocida() -> None:
    # Roboflow exporta la categoría 0 ("workers") como padre de las demás, sin cajas.
    [img] = desde_coco(_coco((1, [20, 10, 40, 30])), FUENTE)
    assert len(img.cajas) == 1


@pytest.mark.parametrize("bbox", [[10, 10, 0, 5], [10, 10, 5, 0], [250, 10, 5, 5]])
def test_las_cajas_vacias_o_fuera_del_cuadro_se_descartan(bbox: list[float]) -> None:
    [img] = desde_coco(_coco((1, bbox)), FUENTE)
    assert img.cajas == []


def test_una_caja_que_se_sale_del_cuadro_se_recorta_al_borde() -> None:
    [img] = desde_coco(_coco((1, [180, 90, 40, 30])), FUENTE)
    assert img.cajas == [(C, Caja(0.9, 0.9, 1.0, 1.0))]


VOC = """<annotation><filename>h1.png</filename><size><width>400</width><height>200</height>
<depth>3</depth></size>
<object><name>helmet</name><bndbox><xmin>40</xmin><ymin>20</ymin><xmax>80</xmax><ymax>60</ymax>
</bndbox></object>
<object><name>head</name><bndbox><xmin>0</xmin><ymin>0</ymin><xmax>10</xmax><ymax>10</ymax>
</bndbox></object></annotation>"""


def test_voc_se_traduce_igual_que_coco() -> None:
    fuente = Fuente("hhd", "CC0 1.0", {"helmet": C, "head": None, "person": P}, frozenset({C}))
    img = desde_voc(VOC, fuente)
    assert img.archivo == "h1.png"
    assert (img.ancho, img.alto) == (400, 200)
    assert img.cajas == [(C, Caja(0.1, 0.1, 0.2, 0.3))]


def test_voc_con_una_clase_no_declarada_detiene_todo() -> None:
    fuente = Fuente("hhd", "CC0 1.0", {"helmet": C}, frozenset({C}))
    with pytest.raises(CategoriaDesconocida, match="head"):
        desde_voc(VOC, fuente)


# --- archivo de fuentes ---------------------------------------------------------------


def test_el_archivo_de_fuentes_del_repo_es_valido() -> None:
    fuentes = cargar_fuentes(Path(__file__).resolve().parents[1] / "scripts/fuentes.yaml")
    assert fuentes, "sin fuentes no hay entrenamiento"
    for f in fuentes:
        assert f.licencia, f"{f.nombre} sin licencia: no entra (07-datasets)"
        assert set(f.clases.values()) - {None} <= set(CLASES_V1)


def test_una_clase_propia_inexistente_en_el_archivo_falla(tmp_path: Path) -> None:
    ruta = tmp_path / "f.yaml"
    ruta.write_text(
        "fuentes:\n  - nombre: x\n    licencia: CC0\n    origen: {}\n"
        "    clases: {helmet: kasco}\n    exhaustivas: []\n"
    )
    with pytest.raises(ValueError, match="kasco"):
        cargar_fuentes(ruta)


# --- completar personas ---------------------------------------------------------------


def test_completar_agrega_solo_las_propuestas_que_no_estan_ya_etiquetadas() -> None:
    existente = Caja(0.0, 0.0, 0.5, 0.5)
    ya_esta = Caja(0.01, 0.01, 0.5, 0.5)  # IoU ~0,96 con la existente
    nueva = Caja(0.6, 0.6, 0.9, 0.9)
    assert completar([existente], [ya_esta, nueva]) == [nueva]


@pytest.mark.parametrize(
    ("desplazamiento", "se_agrega"),
    # Valores diádicos: el IoU sale exacto en coma flotante (1; 0,5; 0,2).
    [(0.0, False), (0.25, False), (0.5, True)],
)
def test_completar_en_el_umbral_de_solapamiento(desplazamiento: float, se_agrega: bool) -> None:
    existente = Caja(0.0, 0.0, 0.75, 0.5)
    propuesta = Caja(desplazamiento, 0.0, 0.75 + desplazamiento, 0.5)
    assert (completar([existente], [propuesta]) == [propuesta]) is se_agrega


def test_completar_sin_nada_previo_agrega_todo() -> None:
    propuestas = [Caja(0.1, 0.1, 0.2, 0.2), Caja(0.5, 0.5, 0.7, 0.9)]
    assert completar([], propuestas) == propuestas


# --- fugas entre particiones ----------------------------------------------------------


E, VA, PR = Particion.ENTRENAMIENTO, Particion.VALIDACION, Particion.PRUEBA


def test_una_imagen_de_entrenamiento_casi_igual_a_una_de_validacion_se_va() -> None:
    hashes = [0b1111, 0b1110, 0xFFFF_FFFF_0000_0000]  # el tercero, a 30+ bits de los otros
    assert quitar_fugas(hashes, [E, VA, E]) == {0}


def test_entre_validacion_y_prueba_cede_validacion() -> None:
    assert quitar_fugas([0b1111, 0b1110], [VA, PR]) == {0}


def test_dos_casi_iguales_en_la_misma_particion_no_son_fuga() -> None:
    assert quitar_fugas([0b1111, 0b1110], [E, E]) == set()


@pytest.mark.parametrize(
    ("bits", "es_fuga"), [(UMBRAL_DUPLICADO, True), (UMBRAL_DUPLICADO + 1, False)]
)
def test_fuga_en_el_umbral_exacto(bits: int, es_fuga: bool) -> None:
    lejano = (1 << bits) - 1  # difiere de 0 en exactamente `bits` bits
    assert (quitar_fugas([0, lejano], [E, PR]) == {0}) is es_fuga


def test_fugas_con_hashes_de_64_bits_completos() -> None:
    alto = (1 << 64) - 1
    assert quitar_fugas([alto, alto ^ 1], [E, VA]) == {0}


# --- partición y salida ---------------------------------------------------------------


def test_la_particion_estable_no_depende_del_orden_ni_de_la_corrida() -> None:
    nombres = [f"img_{i}.jpg" for i in range(2000)]
    primera = [particion_estable(n) for n in nombres]
    assert primera == [particion_estable(n) for n in nombres]
    proporcion = {p: primera.count(p) / len(nombres) for p in Particion}
    assert 0.75 < proporcion[E] < 0.85
    assert 0.07 < proporcion[VA] < 0.13
    assert 0.07 < proporcion[PR] < 0.13


def test_a_coco_usa_las_tres_clases_v1_y_marca_lo_automatico() -> None:
    [img] = desde_coco(_coco((1, [20, 10, 40, 30])), FUENTE)
    coco = a_coco([(img, "css__a.jpg", [Caja(0.5, 0.5, 1.0, 1.0)])])
    assert [c["name"] for c in coco["categories"]] == ["persona", "casco", "chaleco"]
    casco, persona = coco["annotations"]
    assert casco["bbox"] == pytest.approx([20, 10, 40, 30])
    assert casco["category_id"] == CLASES_V1[C]
    assert casco["automatica"] is False
    assert persona["category_id"] == CLASES_V1[P]
    assert persona["automatica"] is True
    assert persona["area"] == pytest.approx(100 * 50)
    assert coco["images"] == [{"id": 1, "file_name": "css__a.jpg", "width": 200, "height": 100}]


# --- grupos de imágenes que vienen del mismo video -------------------------------------


PATRONES = (r"(?i)^(.*?)_(?:mp4|mov)-\d+_", r"^(youtube)-")


@pytest.mark.parametrize(
    ("nombre", "clave"),
    [
        ("IMG_0871_mp4-11_jpg.rf.ab12.jpg", "img_0871"),
        ("IMG_0871_MOV-12_jpg.rf.cd34.jpg", "img_0871"),  # mismo video, otra extensión
        ("youtube-153_jpg.rf.ef56.jpg", "youtube"),
        ("construction-12-_jpg.rf.0a.jpg", None),
    ],
)
def test_grupo_reune_los_cuadros_de_un_mismo_video(nombre: str, clave: str | None) -> None:
    assert grupo(nombre, Fuente("x", "CC0", {}, frozenset(), grupos=PATRONES)) == clave


def test_sin_patrones_ninguna_imagen_tiene_grupo() -> None:
    assert grupo("IMG_0871_mp4-11_jpg", FUENTE) is None


def test_los_cuadros_de_un_video_caen_todos_en_la_misma_particion() -> None:
    fuente = Fuente("css", "CC BY 4.0", {}, frozenset(), grupos=PATRONES)
    nombres = [f"IMG_0871_mp4-{i}_jpg.rf.{i:04x}.jpg" for i in range(40)]
    claves = {grupo(n, fuente) for n in nombres}
    assert claves == {"img_0871"}
    assert len({particion_estable(f"css/{c}") for c in claves}) == 1


def test_un_patron_invalido_en_el_archivo_falla_al_cargar(tmp_path: Path) -> None:
    ruta = tmp_path / "f.yaml"
    ruta.write_text(
        "fuentes:\n  - nombre: x\n    licencia: CC0\n    origen: {}\n"
        "    clases: {}\n    exhaustivas: []\n    grupos: ['(sin cerrar']\n"
    )
    with pytest.raises(ValueError, match="x: patrón de grupo inválido"):
        cargar_fuentes(ruta)


def test_un_patron_sin_grupo_de_captura_falla_al_cargar(tmp_path: Path) -> None:
    ruta = tmp_path / "f.yaml"
    ruta.write_text(
        "fuentes:\n  - nombre: x\n    licencia: CC0\n    origen: {}\n"
        "    clases: {}\n    exhaustivas: []\n    grupos: ['_mp4-']\n"
    )
    with pytest.raises(ValueError, match="grupo de captura"):
        cargar_fuentes(ruta)


# --- verificación del modelo exportado -------------------------------------------------


def _det(clase: ClaseDetectada, caja: Caja, confianza: float = 0.9) -> Deteccion:
    return Deteccion(datetime(2026, 10, 1, tzinfo=UTC), 0, clase, caja, confianza)


def test_emparejar_solo_dentro_de_la_misma_clase() -> None:
    caja = Caja(0.1, 0.1, 0.5, 0.5)
    a, b = [_det(P, caja)], [_det(C, caja)]
    assert emparejar(a, b) == []
    assert emparejar(a, [_det(P, caja)]) == [(a[0], _det(P, caja))]


def test_emparejar_exige_iou_alto() -> None:
    a = [_det(P, Caja(0.0, 0.0, 0.75, 0.5))]
    b = [_det(P, Caja(0.25, 0.0, 1.0, 0.5))]  # IoU 0,5 exacto
    assert emparejar(a, b) == []
    assert emparejar(a, b, umbral_iou=0.5) == [(a[0], b[0])]


def test_asignar_maximiza_la_cantidad_de_pares_sobre_el_umbral() -> None:
    # Por suma de IoU gana (0,1)+(1,0) = 0,672, pero ninguno llega a 0,5: el único par válido
    # es (1,1) con 0,553, aunque su asignación sume menos (0,082 + 0,553 = 0,635).
    iou = np.array([[0.082, 0.411], [0.261, 0.553]])
    assert _asignar(iou, 0.5) == [(1, 1)]


def test_asignar_a_igual_cantidad_prefiere_mas_iou() -> None:
    # Dos asignaciones de 2 pares válidos: la diagonal suma 1,5 y la cruzada 1,75.
    iou = np.array([[0.75, 0.75], [1.0, 0.75]])
    assert _asignar(iou, 0.5) == [(0, 1), (1, 0)]
    assert _asignar(iou, 0.875) == [(1, 0)]
    assert _asignar(np.zeros((0, 3)), 0.5) == []


def test_pares_con_verdad_ignora_la_clase_y_respeta_el_umbral() -> None:
    verdad = [(C, Caja(0.0, 0.0, 0.75, 0.5)), (V, Caja(0.8, 0.8, 0.9, 0.9))]
    predichas = [(1, Caja(0.25, 0.0, 1.0, 0.5)), (7, Caja(0.0, 0.9, 0.1, 1.0))]
    # La primera se solapa justo 0,5 con el casco; la segunda no toca nada.
    assert pares_con_verdad(predichas, verdad) == [(1, C)]
    assert pares_con_verdad(predichas, verdad, umbral_iou=0.51) == []
    assert pares_con_verdad([], verdad) == []


def test_acuerdo_de_clases() -> None:
    mapa = {0: P, 1: C, 2: V}
    assert acuerdo_de_clases([(0, P), (1, C)], mapa) == 1.0
    assert acuerdo_de_clases([(1, P), (0, C)], mapa) == 0.0
    assert acuerdo_de_clases([(1, C), (9, C)], mapa) == 0.5  # un id fuera del mapa no acierta


def test_sin_pares_no_hay_acuerdo_que_medir() -> None:
    with pytest.raises(ValueError, match="sin pares"):
        acuerdo_de_clases([], {0: P})


def test_acierto_por_id_cuenta_cada_id_del_mapa_aunque_no_aparezca() -> None:
    mapa = {0: P, 1: C, 2: V}
    pares = [(1, C)] * 3 + [(0, P), (0, V)]
    assert acierto_por_id(pares, mapa) == {0: (1, 2), 1: (3, 3), 2: (0, 0)}


def test_un_mapa_con_clases_intercambiadas_no_pasa_por_id() -> None:
    # Solo cascos en la muestra: el acuerdo global es 100 %, pero persona y chaleco
    # nunca se contrastaron. Es el caso que la revisión reprodujo.
    intercambiado = {0: V, 1: C, 2: P}
    pares = [(1, C)] * 14
    assert acuerdo_de_clases(pares, intercambiado) == 1.0
    por_id = acierto_por_id(pares, intercambiado)
    assert por_id[0] == (0, 0) and por_id[2] == (0, 0)
    # Con evidencia de las tres clases, el intercambio se ve.
    pares += [(0, P)] * 5 + [(2, V)] * 5
    assert acierto_por_id(pares, intercambiado) == {0: (0, 5), 1: (14, 14), 2: (0, 5)}


def test_muestra_estratificada_cubre_cada_clase() -> None:
    imagenes = [(f"c{i}", [C]) for i in range(100)] + [("p", [P]), ("v", [V])]
    elegidas = muestra_estratificada(imagenes, n=10, minimo_por_clase=1)
    clases = {c for _, cs in imagenes if _ in elegidas for c in cs}
    assert clases == {P, C, V}
    assert len(elegidas) == 10


def test_muestra_estratificada_es_reproducible() -> None:
    imagenes = [(f"c{i}", [C if i % 3 else P]) for i in range(50)]
    assert muestra_estratificada(imagenes, 10, 2) == muestra_estratificada(imagenes, 10, 2)
