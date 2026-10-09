"""Escritor de la vista en vivo (`gepp_worker.vivo`): un anillo en memoria, atómico y efímero."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import cv2
import numpy as np
import pytest
from gepp_core import Caja, ClaseDetectada, Deteccion
from gepp_vision import MascaraPrivacidad
from gepp_worker import vivo as modulo
from gepp_worker.fuente import Cuadro
from gepp_worker.vivo import (
    CARPETA_POR_DEFECTO,
    MAXIMO_CUADROS,
    EscritorVivo,
    VistaDeVideo,
    carpeta_configurada,
    carpeta_de_residuos,
    fps_configurado,
)

from .conftest import T0

NOMBRE = re.compile(r"^(\d{8})_(\d{9})\.jpg$")


def cuadro(indice: int, fps_origen: float = 30.0, valor: int = 200) -> Cuadro:
    return Cuadro(
        indice=indice,
        capture_ts=T0 + timedelta(seconds=indice / fps_origen),
        imagen=np.full((48, 64, 3), valor, dtype=np.uint8),
    )


def sin_mascara(imagen: np.ndarray) -> np.ndarray:
    return imagen


def abrir(
    carpeta: Path,
    *,
    fps_vivo: float = 25.0,
    fps_origen: float = 30.0,
    video_id: int = 7,
    enmascarar: Callable[[np.ndarray], np.ndarray] = sin_mascara,
) -> VistaDeVideo:
    return EscritorVivo(carpeta, fps=fps_vivo).abrir(
        video_id, fps_origen=fps_origen, inicio_captura=T0, enmascarar=enmascarar
    )


def escribir_todos(vista: VistaDeVideo, cuantos: int, fps_origen: float = 30.0) -> int:
    """Un cuadro SALTADO por cada cuadro de origen (los que la vista quiere). Devuelve cuántos."""
    n = 0
    for i in range(cuantos):
        if vista.quiere(i):
            vista.al_saltar(cuadro(i, fps_origen))
            n += 1
    return n


def nombres(carpeta: Path) -> list[str]:
    return sorted(p.name for p in carpeta.iterdir())


@pytest.fixture
def mundo(tmp_path: Path) -> Path:
    """`tmp_path` con una carpeta hermana para comprobar que nada se escribe fuera."""
    (tmp_path / "afuera").mkdir()
    return tmp_path


# ── Apagada por defecto ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("valor", [None, "", "0", "true", "si", "11", " 0 "])
def test_apagada_salvo_con_exactamente_1(valor: str | None) -> None:
    entorno = {} if valor is None else {"GEPP_VISTA_EN_VIVO": valor}
    assert carpeta_configurada(entorno) is None


def test_encendida_usa_la_carpeta_por_defecto_o_la_configurada() -> None:
    assert carpeta_configurada({"GEPP_VISTA_EN_VIVO": "1"}) == Path(CARPETA_POR_DEFECTO)
    assert CARPETA_POR_DEFECTO == "/dev/shm/gepp-vivo"
    entorno = {"GEPP_VISTA_EN_VIVO": "1", "GEPP_CARPETA_VIVO": "/x/y"}
    assert carpeta_configurada(entorno) == Path("/x/y")
    entorno = {"GEPP_VISTA_EN_VIVO": "1", "GEPP_CARPETA_VIVO": "  "}
    assert carpeta_configurada(entorno) == Path(CARPETA_POR_DEFECTO)


def test_la_carpeta_de_residuos_no_depende_de_que_la_vista_este_prendida() -> None:
    assert carpeta_de_residuos({}) == Path(CARPETA_POR_DEFECTO)
    assert carpeta_de_residuos({"GEPP_CARPETA_VIVO": "/x/y"}) == Path("/x/y")
    assert carpeta_de_residuos({"GEPP_VISTA_EN_VIVO": "0", "GEPP_CARPETA_VIVO": "/x/y"}) == Path(
        "/x/y"
    )
    assert carpeta_de_residuos({"GEPP_CARPETA_VIVO": "  "}) == Path(CARPETA_POR_DEFECTO)


# ── GEPP_VIVO_FPS ───────────────────────────────────────────────────────────────────────


def test_sin_la_variable_son_25_fps() -> None:
    assert fps_configurado({}) == 25.0
    assert fps_configurado({"GEPP_VIVO_FPS": "  "}) == 25.0


@pytest.mark.parametrize("texto,valor", [("25", 25.0), ("10", 10.0), (" 30 ", 30.0), ("0.5", 0.5)])
def test_un_valor_valido_se_lee(texto: str, valor: float) -> None:
    assert fps_configurado({"GEPP_VIVO_FPS": texto}) == valor


@pytest.mark.parametrize("texto", ["0", "-1", "-25", "abc", "25,5", "nan", "inf", "-inf"])
def test_un_valor_invalido_falla_con_un_mensaje_claro(texto: str) -> None:
    with pytest.raises(ValueError, match="GEPP_VIVO_FPS"):
        fps_configurado({"GEPP_VIVO_FPS": texto})


@pytest.mark.parametrize("texto", ["0", "-1", "abc"])
def test_al_arrancar_el_trabajador_un_valor_invalido_detiene_el_proceso(
    texto: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from gepp_worker.__main__ import _fps_vivo

    monkeypatch.setenv("GEPP_VIVO_FPS", texto)
    with pytest.raises(SystemExit, match="GEPP_VIVO_FPS"):
        _fps_vivo()
    monkeypatch.delenv("GEPP_VIVO_FPS")
    assert _fps_vivo() == 25.0


@pytest.mark.parametrize("fps", [0, -1, float("nan"), float("inf")])
def test_el_escritor_tampoco_acepta_fps_invalidos(mundo: Path, fps: float) -> None:
    with pytest.raises(ValueError, match="fps"):
        EscritorVivo(mundo / "vivo", fps=fps)


def test_25_fps_de_un_origen_a_30_da_25_por_segundo(mundo: Path) -> None:
    vista = abrir(mundo / "vivo", fps_vivo=25, fps_origen=30)
    assert escribir_todos(vista, 30) == 25  # un segundo de video: 25 cuadros, no 15 ni 30
    assert escribir_todos(abrir(mundo / "otro", fps_vivo=25, fps_origen=30), 300) == 250


def test_con_un_limite_mayor_al_origen_se_escriben_todos_los_cuadros(mundo: Path) -> None:
    vista = abrir(mundo / "vivo", fps_vivo=60, fps_origen=30)
    assert escribir_todos(vista, 30) == 30
    assert len(nombres(mundo / "vivo" / "7")) == 30


def test_un_limite_menor_baja_el_ritmo_por_segundo_de_video(mundo: Path) -> None:
    assert escribir_todos(abrir(mundo / "vivo", fps_vivo=10, fps_origen=30), 30) == 10


# ── La carpeta y la subcarpeta ──────────────────────────────────────────────────────────


def test_la_carpeta_y_la_subcarpeta_son_0700(mundo: Path) -> None:
    abrir(mundo / "vivo")
    assert stat.S_IMODE((mundo / "vivo").stat().st_mode) == 0o700
    assert stat.S_IMODE((mundo / "vivo" / "7").stat().st_mode) == 0o700


def test_una_carpeta_existente_con_permisos_abiertos_se_cierra(mundo: Path) -> None:
    (mundo / "vivo").mkdir(mode=0o755)
    (mundo / "vivo").chmod(0o755)
    EscritorVivo(mundo / "vivo")
    assert stat.S_IMODE((mundo / "vivo").stat().st_mode) == 0o700


def test_un_enlace_simbolico_no_se_acepta_como_carpeta(mundo: Path) -> None:
    (mundo / "real").mkdir()
    (mundo / "vivo").symlink_to(mundo / "real")
    with pytest.raises(ValueError, match="carpeta propia"):
        EscritorVivo(mundo / "vivo")


# ── El anillo: nombres, posición y secuencia ────────────────────────────────────────────


def test_nombres_seq_consecutivos_y_pos_ms_correctos(mundo: Path) -> None:
    vista = abrir(mundo / "vivo", fps_vivo=30, fps_origen=30)
    escribir_todos(vista, 6)
    esperado = [
        "00000001_000000000.jpg",
        "00000002_000000033.jpg",
        "00000003_000000067.jpg",
        "00000004_000000100.jpg",
        "00000005_000000133.jpg",
        "00000006_000000167.jpg",
    ]
    assert nombres(mundo / "vivo" / "7") == esperado


def test_la_posicion_es_la_del_video_y_no_la_del_reloj(mundo: Path) -> None:
    """Un cuadro del segundo 3723,5 del video (1 h 2 min): la posición sale de su fecha de
    captura menos el inicio, no del momento en que se escribe."""
    vista = abrir(mundo / "vivo", fps_vivo=30, fps_origen=30)
    lejano = Cuadro(
        indice=0, capture_ts=T0 + timedelta(seconds=3723.5), imagen=np.zeros((8, 8, 3), np.uint8)
    )
    vista.al_saltar(lejano)
    assert nombres(mundo / "vivo" / "7") == ["00000001_003723500.jpg"]


def test_seq_y_pos_ms_son_crecientes_en_todo_el_anillo(mundo: Path) -> None:
    vista = abrir(mundo / "vivo", fps_vivo=30)
    escribir_todos(vista, 45)
    partes = [NOMBRE.match(n) for n in nombres(mundo / "vivo" / "7")]
    assert all(partes)
    seqs = [int(m.group(1)) for m in partes if m]
    posiciones = [int(m.group(2)) for m in partes if m]
    assert seqs == list(range(1, len(seqs) + 1)) and posiciones == sorted(set(posiciones))


def test_el_anillo_nunca_pasa_de_60_y_conserva_los_ultimos(mundo: Path) -> None:
    assert MAXIMO_CUADROS == 60
    vista = abrir(mundo / "vivo", fps_vivo=30, fps_origen=30)
    sub = mundo / "vivo" / "7"
    for i in range(150):
        vista.al_saltar(cuadro(i))
        assert len(nombres(sub)) <= 60  # en ningún momento, no solo al final
    final = nombres(sub)
    assert len(final) == 60
    assert final[0].startswith("00000091_") and final[-1].startswith("00000150_")


def test_cada_intento_parte_de_cero_con_seq_en_1(mundo: Path) -> None:
    escritor = EscritorVivo(mundo / "vivo", fps=30)
    primera = escritor.abrir(7, fps_origen=30, inicio_captura=T0, enmascarar=sin_mascara)
    escribir_todos(primera, 5)
    segunda = escritor.abrir(7, fps_origen=30, inicio_captura=T0, enmascarar=sin_mascara)
    assert nombres(mundo / "vivo" / "7") == []  # lo del intento anterior no sobrevive
    escribir_todos(segunda, 2)
    assert [n[:8] for n in nombres(mundo / "vivo" / "7")] == ["00000001", "00000002"]


def test_escribe_jpegs_0600_y_nada_fuera_de_la_subcarpeta(mundo: Path) -> None:
    vista = abrir(mundo / "vivo", fps_vivo=30)
    escribir_todos(vista, 3)
    assert nombres(mundo / "vivo") == ["7"]
    assert nombres(mundo / "afuera") == []
    sub = mundo / "vivo" / "7"
    assert all(NOMBRE.match(n) for n in nombres(sub))  # sin temporales a medias
    primero = sub / nombres(sub)[0]
    assert cv2.imdecode(np.fromfile(primero, np.uint8), 1).shape == (48, 64, 3)
    assert stat.S_IMODE(primero.stat().st_mode) == 0o600


def test_se_publica_con_replace_desde_un_temporal_oculto_de_la_misma_subcarpeta(
    mundo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pasos: list[tuple[Path, Path]] = []
    real = os.replace

    def espia(origen: Path, destino: Path) -> None:
        pasos.append((Path(origen), Path(destino)))
        real(origen, destino)

    monkeypatch.setattr(modulo.os, "replace", espia)
    vista = abrir(mundo / "vivo", fps_vivo=30)
    vista.al_saltar(cuadro(0))
    ((origen, destino),) = pasos
    assert origen.parent == destino.parent == mundo / "vivo" / "7"
    assert origen.name.startswith(".") and not destino.name.startswith(".")


# ── Cajas y privacidad ──────────────────────────────────────────────────────────────────

CHALECO = Deteccion(T0, 0, ClaseDetectada.CHALECO, Caja(0.10, 0.10, 0.60, 0.80), 0.9)


def leer(ruta: Path) -> np.ndarray:
    imagen = cv2.imdecode(np.fromfile(ruta, np.uint8), cv2.IMREAD_COLOR)
    assert imagen is not None
    return imagen


def hay_caja(imagen: np.ndarray) -> bool:
    """El borde de la caja del chaleco (BGR 255,160,0) es azul; el fondo gris no."""
    borde = imagen[round(0.10 * imagen.shape[0]), round(0.35 * imagen.shape[1])]
    return int(borde[0]) - int(borde[2]) > 100


def test_los_saltados_llevan_las_cajas_del_ultimo_analisis(mundo: Path) -> None:
    vista = abrir(mundo / "vivo", fps_vivo=30, fps_origen=30)
    sub = mundo / "vivo" / "7"
    vista.al_saltar(cuadro(0))  # antes del primer análisis: sin cajas ni puntos
    vista.analizado(cuadro(1), cuadro(1).imagen, [CHALECO])
    vista.al_saltar(cuadro(2))  # después: las del análisis de 1
    vista.al_saltar(cuadro(3))
    antes, analizado, saltado1, saltado2 = (leer(sub / n) for n in nombres(sub))
    assert not hay_caja(antes)
    assert hay_caja(analizado) and hay_caja(saltado1) and hay_caja(saltado2)


def test_un_nuevo_analisis_reemplaza_las_cajas_de_los_saltados(mundo: Path) -> None:
    vista = abrir(mundo / "vivo", fps_vivo=30, fps_origen=30)
    sub = mundo / "vivo" / "7"
    vista.analizado(cuadro(0), cuadro(0).imagen, [CHALECO])
    vista.analizado(cuadro(1), cuadro(1).imagen, [])  # el modelo ya no ve nada
    vista.al_saltar(cuadro(2))
    assert not hay_caja(leer(sub / nombres(sub)[-1]))


def test_a_un_cuadro_saltado_se_le_aplica_la_mascara_de_privacidad(mundo: Path) -> None:
    mascara = MascaraPrivacidad([[(0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)]])
    vista = abrir(mundo / "vivo", fps_vivo=30, enmascarar=mascara.aplicar)
    original = cuadro(0, valor=230)
    vista.al_saltar(original)
    (nombre,) = nombres(mundo / "vivo" / "7")
    salida = leer(mundo / "vivo" / "7" / nombre)
    assert salida[:, :28].max() < 30 and salida[:, 40:].min() > 180
    assert (original.imagen == 230).all()  # y el cuadro original no se tocó


# ── Borrar y vaciar ─────────────────────────────────────────────────────────────────────


def test_cerrar_borra_la_subcarpeta_entera(mundo: Path) -> None:
    vista = abrir(mundo / "vivo", fps_vivo=30)
    escribir_todos(vista, 10)
    vista.cerrar()
    assert nombres(mundo / "vivo") == []
    vista.cerrar()  # una segunda vez no es un error


def test_vaciar_quita_las_subcarpetas_del_anillo_y_no_sigue_enlaces(mundo: Path) -> None:
    carpeta = mundo / "vivo"
    escritor = EscritorVivo(carpeta)
    (carpeta / "12").mkdir()
    (carpeta / "12" / "00000001_000000000.jpg").write_bytes(b"viejo")
    (carpeta / "12" / ".00000002.tmp").write_bytes(b"a medias")
    ajeno = mundo / "afuera" / "dato.txt"
    ajeno.write_text("no tocar")
    (carpeta / "13").symlink_to(mundo / "afuera")  # un enlace con nombre de video: ni se sigue
    escritor.vaciar()
    assert nombres(carpeta) == ["13"]  # solo quedó el enlace, sin seguir
    assert (carpeta / "13").is_symlink()
    assert ajeno.read_text() == "no tocar"


def test_vaciar_deja_lo_que_no_es_del_anillo_y_avisa_una_vez(
    mundo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    carpeta = mundo / "vivo"
    escritor = EscritorVivo(carpeta)
    (carpeta / "12").mkdir()
    (carpeta / "12" / "00000001_000000000.jpg").write_bytes(b"viejo")
    (carpeta / "notas.txt").write_text("mis notas")
    (carpeta / "fotos").mkdir()
    (carpeta / "fotos" / "a.jpg").write_bytes(b"mia")
    (carpeta / "12a").mkdir()  # casi un id, pero no lo es
    escritor.vaciar()
    assert nombres(carpeta) == ["12a", "fotos", "notas.txt"]
    assert (carpeta / "notas.txt").read_text() == "mis notas"
    assert (carpeta / "fotos" / "a.jpg").read_bytes() == b"mia"
    err = capsys.readouterr().err
    assert err.count("no son del anillo") == 1


def test_vaciar_una_carpeta_solo_del_anillo_no_avisa(
    mundo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    carpeta = mundo / "vivo"
    escritor = EscritorVivo(carpeta)
    (carpeta / "12").mkdir()
    escritor.vaciar()
    assert nombres(carpeta) == []
    assert capsys.readouterr().err == ""


# ── Fallas: avisan y no detienen ─────────────────────────────────────────────────────────


def test_si_codificar_falla_lo_dice_una_sola_vez_y_no_levanta(
    mundo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def roto(*_: object, **__: object) -> bytes:
        raise RuntimeError("sin memoria")

    monkeypatch.setattr(modulo, "cuadro_en_vivo", roto)
    vista = abrir(mundo / "vivo", fps_vivo=30)
    escribir_todos(vista, 20)
    err = capsys.readouterr().err
    assert err.count("no se pudo escribir la vista en vivo") == 1  # 20 fallos, un aviso
    assert nombres(mundo / "vivo" / "7") == []


def test_un_fallo_no_consume_numeros_de_secuencia(
    mundo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = modulo.cuadro_en_vivo
    fallos = iter([True, False, False])

    def a_veces(*a: object, **k: object) -> bytes:
        if next(fallos):
            raise RuntimeError("una vez")
        return real(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(modulo, "cuadro_en_vivo", a_veces)
    vista = abrir(mundo / "vivo", fps_vivo=30)
    escribir_todos(vista, 3)
    assert [n[:8] for n in nombres(mundo / "vivo" / "7")] == ["00000001", "00000002"]


def test_si_publicar_falla_no_queda_el_temporal(
    mundo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def roto(*_: object) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(modulo.os, "replace", roto)
    abrir(mundo / "vivo", fps_vivo=30).al_saltar(cuadro(0))
    assert "disco lleno" in capsys.readouterr().err
    assert nombres(mundo / "vivo" / "7") == []


def test_si_no_se_puede_preparar_la_subcarpeta_la_vista_no_hace_nada(
    mundo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    escritor = EscritorVivo(mundo / "vivo")

    def roto(*_: object, **__: object) -> None:
        raise OSError("sin espacio")

    monkeypatch.setattr(Path, "mkdir", roto)
    vista = escritor.abrir(7, fps_origen=30, inicio_captura=T0, enmascarar=sin_mascara)
    assert "no se pudo preparar la vista en vivo" in capsys.readouterr().err
    assert vista.quiere(0) is False  # el muestreador no decodifica nada para ella
    vista.al_saltar(cuadro(0))  # y si igual llegara un cuadro, no escribe ni levanta
    vista.cerrar()


def test_si_borrar_falla_lo_dice_y_no_levanta(
    mundo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    vista = abrir(mundo / "vivo")

    def roto(*_: object, **__: object) -> None:
        raise PermissionError("no")

    monkeypatch.setattr(modulo.shutil, "rmtree", roto)
    vista.cerrar()
    assert "no se pudo borrar la vista en vivo" in capsys.readouterr().err
