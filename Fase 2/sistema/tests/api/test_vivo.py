"""Vista en vivo: `GET /videos/{id}/vivo` (el cuadro más nuevo) y `/vivo/cuadros` (los nuevos).

Los dos leen el anillo que deja el trabajador en `<carpeta>/<video_id>/` y comparten guardas:
permiso, área, vista encendida, video `procesando` y cuadro más nuevo vigente (10 s).
"""

from __future__ import annotations

import base64
import os
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from gepp_api.app import crear_app
from gepp_api.config import Configuracion
from gepp_api.servicios import vivo as servicio
from sqlalchemy import Engine, text

from .conftest import Cliente

pytestmark = pytest.mark.integration

JPEG = b"\xff\xd8\xff\xe0 cuadro-vivo-sintetico \xff\xd9"
DEMO = {"Authorization": "Bearer demo"}  # prevencionista
SUPER = {"Authorization": "Bearer super"}  # supervisor del área 1
ADMIN = {"Authorization": "Bearer admin"}
AUDITOR = {"Authorization": "Bearer auditor"}
MIB8 = 8 * 1024 * 1024


@pytest.fixture(autouse=True)
def _tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GEPP_API_TOKENS",
        "demo=prevencionista@obra.invalid,super=supervisor.acceso@obra.invalid,"
        "admin=administrador@obra.invalid,auditor=auditor@obra.invalid",
    )


@pytest.fixture
def vivo(tmp_path: Path) -> Path:
    carpeta = tmp_path / "vivo"
    carpeta.mkdir()
    return carpeta


def _cliente(bd: Engine, vivo: Path, *, encendida: bool = True) -> Iterator[Cliente]:
    config = Configuracion(vista_en_vivo=encendida, carpeta_vivo=vivo)
    with TestClient(crear_app(motor=bd, config=config)) as c:
        yield Cliente(c)


@pytest.fixture
def web(bd: Engine, datos: dict[str, Any], vivo: Path) -> Iterator[Cliente]:
    del datos
    yield from _cliente(bd, vivo)


@pytest.fixture
def apagada(bd: Engine, datos: dict[str, Any], vivo: Path) -> Iterator[Cliente]:
    del datos
    yield from _cliente(bd, vivo, encendida=False)


@pytest.fixture(autouse=True)
def _procesando(bd: Engine, datos: dict[str, Any]) -> None:
    """El video 1 (fuente 1, área 1) pasa a `procesando`."""
    del datos
    with bd.begin() as c:
        c.execute(text("UPDATE video SET estado = 'procesando' WHERE id = 1"))


def _nombre(seq: int, pos_ms: int | None = None) -> str:
    return f"{seq:08d}_{(seq * 40 if pos_ms is None else pos_ms):09d}.jpg"


def _cuadro(
    vivo: Path,
    seq: int = 1,
    *,
    pos_ms: int | None = None,
    edad_s: float = 0.0,
    video_id: int = 1,
    datos: bytes | None = None,
) -> Path:
    """Un cuadro del anillo, como lo deja el trabajador. `edad_s` retrasa su fecha."""
    carpeta = vivo / str(video_id)
    carpeta.mkdir(exist_ok=True)
    ruta = carpeta / _nombre(seq, pos_ms)
    ruta.write_bytes(JPEG if datos is None else datos)
    ahora = time.time()
    os.utime(ruta, (ahora - edad_s, ahora - edad_s))
    return ruta


def _jpeg(seq: int) -> bytes:
    """Un contenido distinto por cuadro, para ver el orden y que nadie se cruce."""
    return JPEG + f"#{seq}".encode()


def _anillo(vivo: Path, desde: int, hasta: int, **kw: Any) -> None:
    for seq in range(desde, hasta + 1):
        _cuadro(vivo, seq, datos=_jpeg(seq), **kw)


# Las dos vistas comparten guardas: cada test de guardas corre contra las dos.
VISTAS = [("obtenerVivoVideo", "/vivo"), ("listarCuadrosVivo", "/vivo/cuadros")]


@pytest.fixture(params=VISTAS, ids=["vivo", "cuadros"])
def vista(request: pytest.FixtureRequest) -> tuple[str, str]:
    return request.param  # type: ignore[no-any-return]


def _pedir(
    api: Cliente,
    vista: tuple[str, str],
    esperado: int = 200,
    headers: dict[str, str] = DEMO,
    video_id: int = 1,
    consulta: str = "",
) -> Any:
    op, ruta = vista
    return api.llamar(
        op, "GET", f"/videos/{video_id}{ruta}{consulta}", esperado=esperado, headers=headers
    )


def _cruda(api: Cliente, vista: tuple[str, str]) -> Any:
    """La respuesta HTTP sin interpretar, con sus cabeceras."""
    r = api.http.get(f"/api/v1/videos/1{vista[1]}", headers=DEMO)
    assert r.status_code == 200, r.text[:200]
    return r


def _cuadros(api: Cliente, desde: int | None = None, headers: dict[str, str] = DEMO) -> Any:
    consulta = "" if desde is None else f"?desde={desde}"
    return _pedir(api, VISTAS[1], 200, headers, consulta=consulta)


def _seqs(cuerpo: Any) -> list[int]:
    return [c["seq"] for c in cuerpo["cuadros"]]


# ── Guardas compartidas ────────────────────────────────────────────────────────────────────


def test_el_mas_nuevo_llega_a_las_dos_vistas(web: Cliente, vivo: Path, vista: Any) -> None:
    _anillo(vivo, 1, 3)
    _pedir(web, vista)  # valida la respuesta contra el contrato
    r = _cruda(web, vista)
    assert r.headers["cache-control"] == "no-store"
    if vista[0] == "obtenerVivoVideo":
        assert r.content == _jpeg(3)
        assert r.headers["content-type"] == "image/jpeg"
        assert r.headers["content-length"] == str(len(_jpeg(3)))
    else:
        assert base64.b64decode(r.json()["cuadros"][-1]["jpeg"]) == _jpeg(3)


@pytest.mark.parametrize(
    "headers", [DEMO, SUPER, AUDITOR], ids=["prevencionista", "supervisor", "auditor"]
)
def test_los_roles_con_ver_evidencia_lo_ven(
    web: Cliente, vivo: Path, vista: Any, headers: dict[str, str]
) -> None:
    _cuadro(vivo)
    _pedir(web, vista, 200, headers)


def test_el_administrador_no_la_ve(web: Cliente, vivo: Path, vista: Any) -> None:
    _cuadro(vivo)
    assert _pedir(web, vista, 403, ADMIN)["codigo"] == "sin_permiso"


def test_sin_sesion_es_401(web: Cliente, vivo: Path, vista: Any) -> None:
    _cuadro(vivo)
    assert web.http.get(f"/api/v1/videos/1{vista[1]}").status_code == 401


def test_el_supervisor_de_otra_area_no_la_ve(
    web: Cliente, bd: Engine, vivo: Path, vista: Any
) -> None:
    with bd.begin() as c:
        c.execute(text("UPDATE video SET fuente_id = 2 WHERE id = 1"))
        area = c.execute(text("SELECT area_id FROM fuente WHERE id = 2")).scalar_one()
    assert area != 1, "la prueba necesita una cámara de otra área"
    _cuadro(vivo)
    assert _pedir(web, vista, 403, SUPER)["codigo"] == "sin_permiso"
    _pedir(web, vista, 200, DEMO)  # los roles sin límite de área sí


def test_con_la_vista_apagada_es_404_aunque_haya_cuadro(
    apagada: Cliente, vivo: Path, vista: Any
) -> None:
    _cuadro(vivo)
    assert _pedir(apagada, vista, 404)["codigo"] == "vivo_no_disponible"


def test_apagada_por_defecto_en_el_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEPP_VISTA_EN_VIVO", raising=False)
    monkeypatch.delenv("GEPP_CARPETA_VIVO", raising=False)
    assert Configuracion().vista_en_vivo is False
    assert Configuracion().carpeta_vivo == Path("/dev/shm/gepp-vivo")
    monkeypatch.setenv("GEPP_VISTA_EN_VIVO", "1")
    monkeypatch.setenv("GEPP_CARPETA_VIVO", "/tmp/otra")
    assert Configuracion().vista_en_vivo is True
    assert Configuracion().carpeta_vivo == Path("/tmp/otra")
    monkeypatch.setenv("GEPP_VISTA_EN_VIVO", "0")
    assert Configuracion().vista_en_vivo is False


@pytest.mark.parametrize("estado", ["en_cola", "reintentando", "listo", "error"])
def test_si_el_video_no_esta_procesando_es_404(
    web: Cliente, bd: Engine, vivo: Path, vista: Any, estado: str
) -> None:
    with bd.begin() as c:
        c.execute(text("UPDATE video SET estado = :e WHERE id = 1"), {"e": estado})
    _cuadro(vivo)
    assert _pedir(web, vista, 404)["codigo"] == "vivo_no_disponible"


def test_un_video_que_no_existe_es_404(web: Cliente, vista: Any) -> None:
    assert _pedir(web, vista, 404, video_id=999)["codigo"] == "video_no_encontrado"


def test_sin_subcarpeta_o_vacia_es_404(web: Cliente, vivo: Path, vista: Any) -> None:
    assert _pedir(web, vista, 404)["codigo"] == "vivo_no_disponible"
    (vivo / "1").mkdir()
    assert _pedir(web, vista, 404)["codigo"] == "vivo_no_disponible"


@pytest.mark.parametrize(
    ("edad_s", "esperado"),
    [(0.0, 200), (9.0, 200), (11.0, 404), (3600.0, 404), (-9.0, 200), (-11.0, 404)],
)
def test_vigencia_de_diez_segundos_en_los_dos_lados_del_umbral(
    web: Cliente, vivo: Path, vista: Any, edad_s: float, esperado: int
) -> None:
    _cuadro(vivo, edad_s=edad_s)
    _pedir(web, vista, esperado)


def test_la_vigencia_es_la_del_mas_nuevo_y_no_la_de_los_demas(
    web: Cliente, vivo: Path, vista: Any
) -> None:
    _anillo(vivo, 1, 3, edad_s=100.0)  # viejos
    _pedir(web, vista, 404)  # sin ninguno vigente
    _cuadro(vivo, 4, datos=_jpeg(4))  # llega uno nuevo
    _pedir(web, vista, 200)  # los viejos ya no matan la vista


def test_el_archivo_suelto_de_antes_ya_no_se_sirve(web: Cliente, vivo: Path, vista: Any) -> None:
    (vivo / "1.jpg").write_bytes(JPEG)
    assert _pedir(web, vista, 404)["codigo"] == "vivo_no_disponible"


def test_el_id_del_video_decide_la_carpeta_y_no_se_puede_salir_de_ella(
    web: Cliente, vivo: Path, vista: Any
) -> None:
    _cuadro(vivo.parent, 1, video_id=1)  # un anillo FUERA de la carpeta configurada
    r = web.http.get(f"/api/v1/videos/..%2F1{vista[1]}", headers=DEMO)
    assert r.status_code in (404, 422)


def test_la_respuesta_nunca_trae_rutas(web: Cliente, vivo: Path, vista: Any) -> None:
    assert str(vivo) not in _pedir(web, vista, 404)["mensaje"]
    _cuadro(vivo)
    cuerpo = _cruda(web, vista).content
    assert str(vivo).encode() not in cuerpo


# ── Lectura segura del anillo ──────────────────────────────────────────────────────────────


def test_un_enlace_simbolico_no_se_sigue(web: Cliente, vivo: Path, vista: Any) -> None:
    secreto = vivo.parent / "secreto.jpg"
    secreto.write_bytes(b"no-debe-salir")
    carpeta = vivo / "1"
    carpeta.mkdir()
    (carpeta / _nombre(1)).symlink_to(secreto)
    assert _pedir(web, vista, 404)["codigo"] == "vivo_no_disponible"


def test_un_enlace_en_el_anillo_se_ignora_pero_los_demas_cuadros_salen(
    web: Cliente, vivo: Path
) -> None:
    secreto = vivo.parent / "secreto.jpg"
    secreto.write_bytes(b"no-debe-salir")
    _anillo(vivo, 1, 3)
    (vivo / "1" / _nombre(2)).unlink()
    (vivo / "1" / _nombre(2)).symlink_to(secreto)
    cuerpo = _cuadros(web)
    assert _seqs(cuerpo) == [1, 3]
    assert b"no-debe-salir" not in b"".join(base64.b64decode(c["jpeg"]) for c in cuerpo["cuadros"])


def test_un_cuadro_cambiado_por_un_enlace_tras_el_listado_no_se_sigue(
    web: Cliente, vivo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La carrera: el nombre era un archivo al listar y ya es un enlace al abrirlo."""
    secreto = vivo.parent / "secreto.jpg"
    secreto.write_bytes(b"no-debe-salir")
    _anillo(vivo, 1, 3)
    listar = servicio._nombres

    def listar_y_cambiar(dfd: int) -> Any:
        nombres = listar(dfd)
        ruta = vivo / "1" / _nombre(2)
        ruta.unlink()
        ruta.symlink_to(secreto)
        return nombres

    monkeypatch.setattr(servicio, "_nombres", listar_y_cambiar)
    cuerpo = _cuadros(web)
    assert _seqs(cuerpo) == [1, 3]


def test_una_subcarpeta_enlazada_no_se_sigue(web: Cliente, vivo: Path, vista: Any) -> None:
    real = vivo.parent / "otro-anillo"
    _cuadro(vivo.parent, 1, video_id=1)
    (vivo.parent / "1").rename(real)
    (vivo / "1").symlink_to(real)
    assert _pedir(web, vista, 404)["codigo"] == "vivo_no_disponible"


def test_una_tuberia_o_una_carpeta_con_nombre_valido_no_cuelgan_ni_se_sirven(
    web: Cliente, vivo: Path
) -> None:
    carpeta = vivo / "1"
    carpeta.mkdir()
    os.mkfifo(carpeta / _nombre(2))
    (carpeta / _nombre(3)).mkdir()
    _cuadro(vivo, 1, datos=_jpeg(1))
    assert _seqs(_cuadros(web)) == [1]


@pytest.mark.parametrize(
    "ajeno",
    [
        ".00000005_000000200.jpg",  # temporal oculto del trabajador
        "00000005_000000200.jpg.tmp",
        "00000005_000000200.JPG",
        "00000005_000000200.jpeg",
        "5_200.jpg",
        "0000005_000000200.jpg",  # 7 dígitos
        "000000005_000000200.jpg",  # 9 dígitos
        "00000005_00000200.jpg",
        "00000005_0000000200.jpg",
        "0000000a_000000200.jpg",
        "\uff10\uff10\uff10\uff10\uff10\uff10\uff10\uff15_000000200.jpg",  # ancho completo
        "\u0660\u0660\u0660\u0660\u0660\u0660\u0660\u0665_000000200.jpg",  # arábigo-índicas
        "00000005_000000200.jpg\n",
        " 00000005_000000200.jpg",
        "x00000005_000000200.jpg",
        "00000005-000000200.jpg",
        "LEEME.txt",
    ],
)
def test_los_nombres_ajenos_y_los_temporales_se_ignoran(
    web: Cliente, vivo: Path, ajeno: str
) -> None:
    _anillo(vivo, 1, 2)
    (vivo / "1" / ajeno).write_bytes(b"ajeno")
    cuerpo = _cuadros(web)
    assert _seqs(cuerpo) == [1, 2] and cuerpo["ultimo_seq"] == 2


def test_solo_nombres_ajenos_es_404(web: Cliente, vivo: Path, vista: Any) -> None:
    carpeta = vivo / "1"
    carpeta.mkdir()
    (carpeta / ".00000001_000000040.jpg").write_bytes(JPEG)
    assert _pedir(web, vista, 404)["codigo"] == "vivo_no_disponible"


def test_un_archivo_vacio_o_enorme_se_salta(web: Cliente, vivo: Path) -> None:
    _cuadro(vivo, 1, datos=_jpeg(1))
    _cuadro(vivo, 2, datos=b"")
    _cuadro(vivo, 3, datos=b"x" * (MIB8 + 1))
    _cuadro(vivo, 4, datos=b"x" * MIB8)
    cuerpo = _cuadros(web)
    assert _seqs(cuerpo) == [1, 4] and cuerpo["ultimo_seq"] == 4
    assert len(base64.b64decode(cuerpo["cuadros"][-1]["jpeg"])) == MIB8


def test_si_un_cuadro_se_poda_entre_el_listado_y_la_lectura_se_salta(
    web: Cliente, vivo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _anillo(vivo, 1, 4)
    listar = servicio._nombres

    def listar_y_podar(dfd: int) -> Any:
        nombres = listar(dfd)
        (vivo / "1" / _nombre(2)).unlink()  # el trabajador lo borró justo después
        return nombres

    monkeypatch.setattr(servicio, "_nombres", listar_y_podar)
    cuerpo = _cuadros(web)
    assert _seqs(cuerpo) == [1, 3, 4] and cuerpo["ultimo_seq"] == 4


def test_si_el_mas_nuevo_desaparece_antes_de_leerlo_vale_el_anterior(
    web: Cliente, vivo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _anillo(vivo, 1, 3)
    listar = servicio._nombres

    def listar_y_podar(dfd: int) -> Any:
        nombres = listar(dfd)
        (vivo / "1" / _nombre(3)).unlink()
        return nombres

    monkeypatch.setattr(servicio, "_nombres", listar_y_podar)
    cuerpo = _cuadros(web)
    assert _seqs(cuerpo) == [1, 2] and cuerpo["ultimo_seq"] == 2


def test_el_contenido_sale_del_descriptor_abierto_aunque_el_archivo_se_borre(
    web: Cliente, vivo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ruta = _cuadro(vivo, 1)
    real = os.open

    def abrir_y_borrar(path: str, *args: Any, **kw: Any) -> int:
        fd = real(path, *args, **kw)
        if str(path).endswith(".jpg"):
            ruta.unlink()  # ya abierto: el descriptor sigue valiendo
        return fd

    monkeypatch.setattr(os, "open", abrir_y_borrar)
    assert _cuadros(web)["cuadros"][0]["seq"] == 1
    monkeypatch.undo()
    _pedir(web, VISTAS[1], 404)


# ── /vivo/cuadros: qué cuadros salen ───────────────────────────────────────────────────────


def test_desde_0_el_intermedio_y_el_ultimo(web: Cliente, vivo: Path) -> None:
    _anillo(vivo, 1, 5)
    por_defecto = _cuadros(web)
    assert _seqs(por_defecto) == [1, 2, 3, 4, 5] and por_defecto["ultimo_seq"] == 5
    assert _cuadros(web, 0) == por_defecto  # el valor por defecto es 0
    medio = _cuadros(web, 3)
    assert _seqs(medio) == [4, 5] and medio["ultimo_seq"] == 5
    ultimo = _cuadros(web, 5)
    assert ultimo == {"cuadros": [], "ultimo_seq": 5}  # 200 y vacío, no 404


def test_un_desde_posterior_al_ultimo_da_vacio_y_dice_cual_es_el_ultimo(
    web: Cliente, vivo: Path
) -> None:
    """`seq` vuelve a 1 en cada intento: el cliente se entera por `ultimo_seq < desde`."""
    _anillo(vivo, 1, 2)
    assert _cuadros(web, 900) == {"cuadros": [], "ultimo_seq": 2}


def test_los_cuadros_salen_de_viejo_a_nuevo_con_su_contenido_y_su_posicion(
    web: Cliente, vivo: Path
) -> None:
    _cuadro(vivo, 2, pos_ms=1500, datos=_jpeg(2))
    _cuadro(vivo, 1, pos_ms=0, datos=_jpeg(1))
    _cuadro(vivo, 10, pos_ms=123456, datos=_jpeg(10))
    cuerpo = _cuadros(web)
    assert [(c["seq"], c["posicion_s"]) for c in cuerpo["cuadros"]] == [
        (1, 0),
        (2, 1.5),
        (10, 123.456),
    ]
    assert [base64.b64decode(c["jpeg"]) for c in cuerpo["cuadros"]] == [
        _jpeg(1),
        _jpeg(2),
        _jpeg(10),
    ]


def test_con_mas_de_treinta_nuevos_salen_los_treinta_mas_nuevos(web: Cliente, vivo: Path) -> None:
    _anillo(vivo, 1, 45)
    assert _seqs(_cuadros(web)) == list(range(16, 46))
    assert _seqs(_cuadros(web, 10)) == list(range(16, 46))  # 35 nuevos: los 30 más nuevos
    assert _seqs(_cuadros(web, 15)) == list(range(16, 46))  # justo 30
    assert _seqs(_cuadros(web, 16)) == list(range(17, 46))  # 29
    assert _seqs(_cuadros(web, 40)) == [41, 42, 43, 44, 45]


def test_exactamente_treinta_y_treinta_y_uno(web: Cliente, vivo: Path) -> None:
    _anillo(vivo, 1, 30)
    assert _seqs(_cuadros(web)) == list(range(1, 31))
    _cuadro(vivo, 31, datos=_jpeg(31))
    assert _seqs(_cuadros(web)) == list(range(2, 32))


def test_el_desde_es_un_entero_no_negativo(web: Cliente, vivo: Path) -> None:
    _anillo(vivo, 1, 2)
    for malo in ("-1", "abc", "1.5", ""):
        assert _pedir(web, VISTAS[1], 422, consulta=f"?desde={malo}")["codigo"] == (
            "peticion_invalida"
        )


@pytest.mark.parametrize(
    ("edad_viejo_s", "esperado"),
    [(100.0, [2]), (11.0, [2]), (9.0, [1, 2]), (0.0, [1, 2]), (-100.0, [2])],
)
def test_cada_cuadro_se_filtra_por_su_propia_edad(
    web: Cliente, vivo: Path, edad_viejo_s: float, esperado: list[int]
) -> None:
    """La vigencia no es solo la del más nuevo: un cuadro viejo del anillo no se sirve (H2)."""
    _cuadro(vivo, 1, datos=_jpeg(1), edad_s=edad_viejo_s)
    _cuadro(vivo, 2, datos=_jpeg(2))
    cuerpo = _cuadros(web)
    assert _seqs(cuerpo) == esperado
    assert cuerpo["ultimo_seq"] == 2  # el seq devuelto sigue siendo el del más nuevo


# ── Correcciones de la revisión ────────────────────────────────────────────────────────────


def test_una_raiz_enlazada_no_se_sigue(
    bd: Engine, datos: dict[str, Any], tmp_path: Path, vista: Any
) -> None:
    """`O_NOFOLLOW` en la subcarpeta no basta: con la raíz enlazada se serviría otro directorio."""
    del datos
    real = tmp_path / "real"
    real.mkdir()
    _cuadro(real, 1, datos=_jpeg(1))
    enlace = tmp_path / "enlace"
    enlace.symlink_to(real, target_is_directory=True)
    for cliente in _cliente(bd, enlace):
        assert _pedir(cliente, vista, 404)["codigo"] == "vivo_no_disponible"
    # Control: la misma carpeta, sin enlace, sí se sirve.
    for cliente in _cliente(bd, real):
        _pedir(cliente, vista, 200)


def test_una_tuberia_con_nombre_valido_y_con_datos_vigentes_no_se_sirve(
    web: Cliente, vivo: Path
) -> None:
    carpeta = vivo / "1"
    carpeta.mkdir()
    ruta = carpeta / _nombre(2)
    os.mkfifo(ruta)
    escritor = os.open(
        ruta, os.O_RDWR | os.O_NONBLOCK
    )  # mantiene la tubería con bytes y fecha de ahora
    try:
        assert os.write(escritor, JPEG) == len(JPEG)
        _cuadro(vivo, 1, datos=_jpeg(1))
        cuerpo = _cuadros(web)
        assert _seqs(cuerpo) == [1]
        assert cuerpo["ultimo_seq"] == 1
        assert JPEG not in [base64.b64decode(c["jpeg"]) for c in cuerpo["cuadros"]]
    finally:
        os.close(escritor)


def test_un_anillo_con_solo_el_seq_cero_no_se_sirve(web: Cliente, vivo: Path, vista: Any) -> None:
    """El contrato exige `ultimo_seq >= 1`: el seq 0 es un nombre inválido."""
    _cuadro(vivo, 0, pos_ms=0, datos=_jpeg(0))
    assert _pedir(web, vista, 404)["codigo"] == "vivo_no_disponible"


def test_el_seq_cero_se_ignora_y_los_demas_cuadros_salen(web: Cliente, vivo: Path) -> None:
    _cuadro(vivo, 0, pos_ms=0, datos=_jpeg(0))
    _cuadro(vivo, 1, datos=_jpeg(1))
    cuerpo = _cuadros(web)
    assert _seqs(cuerpo) == [1]
    assert cuerpo["ultimo_seq"] == 1


AHORA = 2_000_000_000.0  # entero: con edades diádicas, las fechas del archivo son exactas


@pytest.fixture
def reloj(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fija `time.time` solo dentro del servicio: la vigencia deja de depender del reloj real."""
    monkeypatch.setattr(servicio, "time", SimpleNamespace(time=lambda: AHORA))


def _cuadro_fechado(vivo: Path, seq: int, edad_s: float) -> None:
    ruta = _cuadro(vivo, seq, datos=_jpeg(seq))
    os.utime(ruta, (AHORA - edad_s, AHORA - edad_s))


@pytest.mark.usefixtures("reloj")
@pytest.mark.parametrize(
    ("edad_s", "esperado"),
    [(9.75, 200), (10.0, 200), (10.25, 404), (-9.75, 200), (-10.0, 200), (-10.25, 404)],
)
def test_vigencia_exacta_del_cuadro_mas_nuevo(
    web: Cliente, vivo: Path, vista: Any, edad_s: float, esperado: int
) -> None:
    _cuadro_fechado(vivo, 1, edad_s)
    _pedir(web, vista, esperado)


@pytest.mark.usefixtures("reloj")
@pytest.mark.parametrize(
    ("edad_s", "esperado"),
    [(9.75, [1, 2]), (10.0, [1, 2]), (10.25, [2]), (-9.75, [1, 2]), (-10.0, [1, 2]), (-10.25, [2])],
)
def test_vigencia_exacta_de_cada_cuadro_del_anillo(
    web: Cliente, vivo: Path, edad_s: float, esperado: list[int]
) -> None:
    _cuadro_fechado(vivo, 1, edad_s)
    _cuadro_fechado(vivo, 2, 0.0)
    assert _seqs(_cuadros(web)) == esperado
