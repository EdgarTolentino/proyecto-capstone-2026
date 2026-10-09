"""La vista en vivo atravesando el trabajador: todos los cuadros, privacidad, anillo y fallas.

PostgreSQL real, detector falso y un video blanco de 10 fps (el muestreo a 5 fps salta uno de cada
dos). Lo que se mira son los archivos que leería la API, no una función suelta.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import fakeredis
import numpy as np
import pytest
from gepp_bd import transaccion
from gepp_bd.modelos import Fuente, Hallazgo, Video, Zona
from gepp_bd.semilla import cargar, leer
from gepp_vision.detectores import DetectorFalso, Guion
from gepp_vision.evidencia import zona_de_rostro
from gepp_worker import avance as modulo_avance
from gepp_worker import trabajador as modulo_trabajador
from gepp_worker import vivo as modulo_vivo
from gepp_worker.cola import ColaTrabajos
from gepp_worker.trabajador import Configuracion, Trabajador
from gepp_worker.vigilante import Vigilante
from sqlalchemy import Engine, func, select

from .test_avance import Observado, Reloj
from .test_ingesta import GUION, MTIME, PERFIL

pytestmark = pytest.mark.integration

NOMBRE = re.compile(r"^(\d{8})_(\d{9})\.jpg$")
ALTO, ANCHO = 240, 320


def video_blanco(ruta: Path, segundos: int = 3) -> Path:
    escritor = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), 10, (ANCHO, ALTO))
    for _ in range(10 * segundos):
        escritor.write(np.full((ALTO, ANCHO, 3), 235, dtype=np.uint8))
    escritor.release()
    os.utime(ruta, (MTIME.timestamp(), MTIME.timestamp()))
    return ruta


class Mundo:
    def __init__(self, bd: Engine, tmp: Path) -> None:
        with transaccion(bd) as s:
            cargar(s, leer(PERFIL))
        self.bd, self.tmp = bd, tmp
        self.entrada = tmp / "entrada"
        self.entrada.mkdir()
        self.vivo = tmp / "vivo"
        self.cola = ColaTrabajos(fakeredis.FakeRedis())
        self.vigilante = Vigilante(self.entrada, self.cola, fuente_id=1)
        self.reloj = Reloj()

    def privacidad_a_la_izquierda(self) -> None:
        with transaccion(self.bd) as s:
            fuente = s.get(Fuente, 1)
            assert fuente is not None
            s.add(
                Zona(
                    area_id=fuente.area_id,
                    fuente_id=1,
                    nombre="baño",
                    tipo="privacidad",
                    poligono=[[0.0, 0.0], [0.5, 0.0], [0.5, 1.0], [0.0, 1.0]],
                )
            )

    def encolar(self, segundos: int = 3) -> None:
        shutil.copy2(video_blanco(self.tmp / "blanco.mp4", segundos), self.entrada / "blanco.mp4")
        self.vigilante.sondear()
        assert len(self.vigilante.sondear()) == 1

    def trabajador(
        self, antes: Callable[[int], None] = lambda _i: None, *, vivo: bool = True
    ) -> Trabajador:
        config = Configuracion(
            carpeta_evidencia=self.tmp / "evidencia",
            carpeta_vivo=self.vivo if vivo else None,
        )
        guion = Guion.desde_json(GUION)
        return Trabajador(
            self.bd,
            self.cola,
            lambda: Observado(DetectorFalso(guion), antes),  # type: ignore[arg-type,return-value]
            config,
            reloj=self.reloj,
        )

    def anillo(self) -> list[Path]:
        sub = self.vivo / "1"
        return sorted(sub.iterdir()) if sub.is_dir() else []


@pytest.fixture
def mundo(bd: Engine, tmp_path: Path) -> Mundo:
    return Mundo(bd, tmp_path)


def decodificar(ruta: Path) -> np.ndarray:
    imagen = cv2.imdecode(np.fromfile(ruta, np.uint8), cv2.IMREAD_COLOR)
    assert imagen is not None
    return imagen


def es_negro(vista: np.ndarray, x: int, y: int) -> bool:
    return bool(vista[y, x].max() < 40)


def contar_decodificados(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Cuenta cada `recuperar` (decodificación) de la fuente real del trabajador."""
    llamadas: list[int] = []
    real = modulo_trabajador.FuenteArchivo.recuperar

    def con_cuenta(self: Any) -> Any:
        llamadas.append(1)
        return real(self)

    monkeypatch.setattr(modulo_trabajador.FuenteArchivo, "recuperar", con_cuenta)
    return llamadas


# ── Con la vista apagada nada cambia ────────────────────────────────────────────────────


def test_apagada_solo_se_decodifican_los_cuadros_muestreados(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_debe(*_: Any, **__: Any) -> None:
        pytest.fail("con la vista apagada no se prepara ni se escribe nada")

    monkeypatch.setattr(modulo_vivo.EscritorVivo, "abrir", no_debe)
    decodificados = contar_decodificados(monkeypatch)
    mundo.encolar()
    trabajador = mundo.trabajador(vivo=False)
    assert trabajador._vivo is None
    resultado = trabajador.atender_uno()
    assert resultado is not None and resultado.cuadros == 15
    # 30 cuadros de origen, 15 muestreados: 15 decodificados, más 1 por hallazgo (la segunda
    # pasada que extrae su evidencia).
    assert len(decodificados) == 15 + resultado.hallazgos == 16
    assert not mundo.vivo.exists()


def test_prendida_se_decodifican_todos_los_cuadros_una_vez(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    decodificados = contar_decodificados(monkeypatch)
    mundo.encolar()
    resultado = mundo.trabajador().atender_uno()
    assert resultado is not None and resultado.cuadros == 15  # el análisis no cambia
    assert len(decodificados) == 30 + resultado.hallazgos == 31  # todos, más la evidencia


# ── Un cuadro por cuadro de origen, en orden, con su posición ───────────────────────────


def test_un_cuadro_por_cada_cuadro_de_origen_con_seq_y_posicion(mundo: Mundo) -> None:
    instantaneas: dict[int, list[str]] = {}

    def antes(indice: int) -> None:
        instantaneas[indice] = [p.name for p in mundo.anillo()]

    mundo.encolar()
    assert mundo.trabajador(antes).atender_uno() is not None

    # Al llegar al último cuadro analizado (28) ya se escribieron los 28 anteriores, saltados
    # incluidos: 10 fps de origen caben bajo los 25 de la vista.
    nombres = instantaneas[28]
    assert len(nombres) == 28
    partes = [NOMBRE.match(n) for n in nombres]
    assert all(partes)
    assert [int(m.group(1)) for m in partes if m] == list(range(1, 29))  # seq consecutivos
    assert [int(m.group(2)) for m in partes if m] == [100 * i for i in range(28)]  # pos_ms


# ── Privacidad en TODOS los cuadros, también los saltados ───────────────────────────────


def test_el_poligono_de_privacidad_queda_negro_tambien_en_los_cuadros_saltados(
    mundo: Mundo,
) -> None:
    mundo.privacidad_a_la_izquierda()
    vistos: dict[str, np.ndarray] = {}

    def antes(indice: int) -> None:
        if indice == 28:
            vistos.update({p.name: decodificar(p) for p in mundo.anillo()})

    mundo.encolar()
    assert mundo.trabajador(antes).atender_uno() is not None

    assert len(vistos) == 28
    for nombre, imagen in vistos.items():
        seq = int(nombre[:8])
        tipo = "analizado" if seq % 2 == 1 else "saltado"  # 0,2,4... se analizan; 1,3,5... no
        assert imagen.shape[:2] == (ALTO, ANCHO)
        assert imagen[:, :100].max() < 30, f"{nombre} ({tipo}): el polígono se ve"
        assert imagen[:, 200:].min() > 180, f"{nombre} ({tipo}): el resto desapareció"


def test_los_cuadros_saltados_llevan_la_caja_del_ultimo_analisis(mundo: Mundo) -> None:
    from gepp_core import Caja

    persona = Caja(0.40, 0.20, 0.52, 0.80)  # la del guion
    zona = zona_de_rostro(persona)
    cara = (round((zona.x1 + zona.x2) / 2 * ANCHO), round((zona.y1 + zona.y2) / 2 * ALTO))
    borde = (round(persona.x1 * ANCHO), round((persona.y1 + persona.y2) / 2 * ALTO))
    vistos: dict[str, np.ndarray] = {}

    def antes(indice: int) -> None:
        if indice == 6:
            vistos.update({p.name: decodificar(p) for p in mundo.anillo()})

    mundo.encolar()
    assert mundo.trabajador(antes).atender_uno() is not None
    ordenados = [vistos[n] for n in sorted(vistos)]
    # Cuadros 0 (analizado), 1 (saltado), 2 (analizado), 3 (saltado)... todos con su caja.
    assert len(ordenados) == 6
    assert all(
        int(v[borde[1], borde[0]][2]) - int(v[borde[1], borde[0]][0]) > 150 for v in ordenados
    )
    # Y la cara sin tapar (el punto se quitó el 2026-10-09; el fondo es blanco).
    assert not any(es_negro(v, *cara) for v in ordenados)


# ── El anillo ───────────────────────────────────────────────────────────────────────────


def test_el_anillo_nunca_pasa_de_60_cuadros(mundo: Mundo) -> None:
    largos: list[int] = []
    mundo.encolar(segundos=9)  # 90 cuadros de origen

    def antes(_indice: int) -> None:
        largos.append(len(mundo.anillo()))

    assert mundo.trabajador(antes).atender_uno() is not None
    assert max(largos) == 60  # llegó al límite...
    assert all(n <= 60 for n in largos)  # ...y nunca lo pasó


def test_la_subcarpeta_se_borra_al_terminar_bien(mundo: Mundo) -> None:
    mundo.encolar()
    assert mundo.trabajador().atender_uno() is not None
    assert list(mundo.vivo.iterdir()) == []


def test_la_subcarpeta_se_borra_si_el_intento_falla(mundo: Mundo) -> None:
    vistos: list[int] = []

    def antes(indice: int) -> None:
        vistos.append(len(mundo.anillo()))
        if indice >= 10:
            raise RuntimeError("falló a mitad")

    mundo.encolar()
    assert mundo.trabajador(antes).atender_uno() is None  # volvió a la cola para reintento
    assert max(vistos) > 0  # había cuadros mientras se procesaba
    assert list(mundo.vivo.iterdir()) == []


def test_cada_intento_reinicia_seq_en_1(mundo: Mundo) -> None:
    primeros: list[str] = []
    intento = {"n": 0}

    def antes(indice: int) -> None:
        if indice == 0:
            intento["n"] += 1
        if indice == 6:
            primeros.append(mundo.anillo()[0].name)
            if intento["n"] == 1:
                raise RuntimeError("falló el primer intento")

    mundo.encolar()
    trabajador = mundo.trabajador(antes)
    assert trabajador.atender_uno() is None  # el primer intento falla
    assert list(mundo.vivo.iterdir()) == []
    assert trabajador.reencolar_pedidos() >= 0
    assert trabajador.atender_uno() is not None  # y el reintento termina
    assert intento["n"] == 2
    assert [n[:8] for n in primeros] == ["00000001", "00000001"]  # los dos parten de 1


# ── Fallas y arranque ───────────────────────────────────────────────────────────────────


def test_si_escribir_la_vista_falla_el_analisis_sigue(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def roto(*_: Any, **__: Any) -> bytes:
        raise RuntimeError("sin memoria")

    monkeypatch.setattr(modulo_vivo, "cuadro_en_vivo", roto)
    mundo.encolar()
    resultado = mundo.trabajador().atender_uno()
    assert resultado is not None and resultado.hallazgos == 1
    with transaccion(mundo.bd) as s:
        assert s.scalar(select(func.count()).select_from(Hallazgo)) == 1
        assert s.scalars(select(Video.estado)).one() == "listo"
    assert capsys.readouterr().err.count("no se pudo escribir la vista en vivo") == 1


def test_al_arrancar_el_trabajador_la_carpeta_se_vacia_con_sus_subcarpetas(mundo: Mundo) -> None:
    trabajador = mundo.trabajador()
    (mundo.vivo / "9").mkdir()
    (mundo.vivo / "9" / "00000003_000000200.jpg").write_bytes(b"de una corrida cortada")
    (mundo.vivo / "9" / ".00000004.tmp").write_bytes(b"a medias")
    trabajador.correr(seguir=lambda: False)
    assert list(mundo.vivo.iterdir()) == []


def _restos(vivo: Path) -> None:
    (vivo / "9").mkdir(parents=True)
    (vivo / "9" / "00000003_000000200.jpg").write_bytes(b"de una corrida cortada")


def _trabajador_apagado(mundo: Mundo) -> Trabajador:
    config = Configuracion(
        carpeta_evidencia=mundo.tmp / "evidencia",
        carpeta_vivo=None,  # la vista está apagada...
        carpeta_vivo_residuos=mundo.vivo,  # ...pero se sabe dónde pudo quedar algo
    )
    return Trabajador(
        mundo.bd,
        mundo.cola,
        lambda: None,
        config,
        reloj=mundo.reloj,  # type: ignore[arg-type,return-value]
    )


def test_apagada_al_arrancar_se_vacian_los_restos_de_una_corrida_con_la_vista_prendida(
    mundo: Mundo,
) -> None:
    _restos(mundo.vivo)
    _trabajador_apagado(mundo).correr(seguir=lambda: False)
    assert mundo.vivo.is_dir() and list(mundo.vivo.iterdir()) == []


def test_apagada_y_sin_carpeta_no_falla_ni_la_crea(mundo: Mundo) -> None:
    inexistente = mundo.tmp / "no-existe"
    config = Configuracion(
        carpeta_evidencia=mundo.tmp / "evidencia", carpeta_vivo_residuos=inexistente
    )
    Trabajador(
        mundo.bd,
        mundo.cola,
        lambda: None,
        config,
        reloj=mundo.reloj,  # type: ignore[arg-type,return-value]
    ).correr(seguir=lambda: False)
    assert not inexistente.exists()


def test_apagada_no_sigue_un_enlace_a_otra_carpeta(mundo: Mundo) -> None:
    ajena = mundo.tmp / "ajena"
    ajena.mkdir()
    (ajena / "dato.txt").write_text("no tocar")
    enlace = mundo.tmp / "enlace"
    enlace.symlink_to(ajena)
    config = Configuracion(carpeta_evidencia=mundo.tmp / "evidencia", carpeta_vivo_residuos=enlace)
    Trabajador(
        mundo.bd,
        mundo.cola,
        lambda: None,
        config,
        reloj=mundo.reloj,  # type: ignore[arg-type,return-value]
    ).correr(seguir=lambda: False)
    assert (ajena / "dato.txt").read_text() == "no tocar"


# ── El avance sigue su propio ritmo ─────────────────────────────────────────────────────


def test_el_avance_sigue_a_los_2_segundos_aunque_la_vista_escriba_todos_los_cuadros(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cada cuadro analizado "tarda" 0,25 s de reloj. La vista escribe 30 cuadros (todos); el
    avance, que escribe en la base, publica el primero y el que cumple 2 s: nada entre medio."""
    assert Configuracion(carpeta_evidencia=mundo.tmp).avance_cada_s == 2.0
    escritos: list[int] = []
    avances: list[float] = []
    real_vista = modulo_vivo.cuadro_en_vivo
    real_avance = modulo_avance.videos.publicar_avance

    def cuenta_vista(*a: Any, **k: Any) -> bytes:
        escritos.append(1)
        return real_vista(*a, **k)

    def cuenta_avance(*a: Any, **k: Any) -> None:
        if k["fase"] == "analizando":
            avances.append(mundo.reloj.t)
        return real_avance(*a, **k)

    monkeypatch.setattr(modulo_vivo, "cuadro_en_vivo", cuenta_vista)
    monkeypatch.setattr(modulo_avance.videos, "publicar_avance", cuenta_avance)

    def antes(_indice: int) -> None:
        mundo.reloj.t += 0.25

    mundo.encolar()
    resultado = mundo.trabajador(antes).atender_uno()
    assert resultado is not None and resultado.cuadros == 15
    assert len(escritos) == 30
    assert avances == [0.25, 2.25]


# ── Correcciones de la revisión ─────────────────────────────────────────────────────────


def test_si_la_carpeta_de_la_vista_no_se_puede_crear_el_trabajador_arranca_y_analiza(
    mundo: Mundo, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un fallo de la vista nunca tumba el análisis: la raíz cuelga de un ARCHIVO (mkdir falla
    con OSError) y aun así el trabajador se construye y procesa el video."""
    (mundo.tmp / "archivo").write_text("no es carpeta")
    mundo.vivo = mundo.tmp / "archivo" / "vivo"
    mundo.encolar()
    resultado = mundo.trabajador().atender_uno()  # antes: OSError ya en Trabajador.__init__
    assert resultado is not None and resultado.hallazgos == 1
    assert "no se pudo preparar la vista en vivo" in capsys.readouterr().err


def test_si_cerrar_el_muestreador_falla_igual_se_borran_los_cuadros(
    mundo: Mundo, monkeypatch: pytest.MonkeyPatch
) -> None:
    def roto(_self: Any) -> None:
        raise RuntimeError("no se pudo cerrar el video")

    mundo.encolar()
    monkeypatch.setattr(modulo_trabajador.Muestreador, "cerrar", roto)
    mundo.trabajador().atender_uno()  # el intento falla (va a reintento), pero sin dejar JPEG
    assert list(mundo.vivo.iterdir()) == []
