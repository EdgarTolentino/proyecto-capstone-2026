"""Pedir desde la web que se procese un video: lista de la carpeta de entrada, pedidos y errores."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from gepp_api.app import crear_app
from gepp_api.config import Configuracion
from gepp_bd.repositorios import pedidos
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from .conftest import Cliente

pytestmark = pytest.mark.integration

ADMIN = {"Authorization": "Bearer admin"}
DEMO = {"Authorization": "Bearer demo"}  # prevencionista: no tiene `editar_reglas`
OPERACIONES = [
    ("listarEntradaVideos", "GET", "/videos/entrada"),
    ("listarPedidos", "GET", "/videos/pedidos"),
    ("pedirIngesta", "POST", "/videos"),
]


@pytest.fixture(autouse=True)
def _tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GEPP_API_TOKENS", "demo=prevencionista@obra.invalid,admin=administrador@obra.invalid"
    )
    monkeypatch.delenv("GEPP_CARPETA_ENTRADA", raising=False)


@pytest.fixture
def entrada(tmp_path: Path) -> Path:
    carpeta = tmp_path / "entrada"
    carpeta.mkdir()
    return carpeta


def _cliente(bd: Engine, carpeta: Path | None) -> Iterator[Cliente]:
    with TestClient(crear_app(motor=bd, config=Configuracion(carpeta_entrada=carpeta))) as c:
        yield Cliente(c)


@pytest.fixture
def web(bd: Engine, datos: dict[str, Any], entrada: Path) -> Iterator[Cliente]:
    del datos
    yield from _cliente(bd, entrada)


@pytest.fixture
def sin_carpeta(bd: Engine, datos: dict[str, Any]) -> Iterator[Cliente]:
    del datos
    yield from _cliente(bd, None)


def _video(carpeta: Path, nombre: str, contenido: bytes = b"x", mtime: float | None = None) -> Path:
    ruta = carpeta / nombre
    ruta.write_bytes(contenido)
    if mtime is not None:
        os.utime(ruta, (mtime, mtime))
    return ruta


def _pedir(
    web: Cliente, archivo: Any, fuente_id: Any = 1, *, esperado: int = 202, **kw: Any
) -> Any:
    return web.llamar(
        "pedirIngesta",
        "POST",
        "/videos",
        esperado=esperado,
        json={"archivo": archivo, "fuente_id": fuente_id},
        headers=ADMIN,
        **kw,
    )


def _sin_rutas(valor: Any, *prohibidos: str) -> None:
    """Ningún texto del JSON es una ruta del servidor ni contiene las carpetas del test."""
    if isinstance(valor, dict):
        for v in valor.values():
            _sin_rutas(v, *prohibidos)
    elif isinstance(valor, list):
        for v in valor:
            _sin_rutas(v, *prohibidos)
    elif isinstance(valor, str):
        assert not valor.startswith("/"), valor
        assert all(p not in valor for p in prohibidos), valor


# ── Permisos ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("operacion", "metodo", "ruta"), OPERACIONES)
def test_sin_sesion_es_401(web: Cliente, operacion: str, metodo: str, ruta: str) -> None:
    web.llamar(operacion, metodo, ruta, esperado=401, headers={}, json={})


@pytest.mark.parametrize(("operacion", "metodo", "ruta"), OPERACIONES)
def test_el_prevencionista_no_puede_lanzar_ni_ver_la_entrada(
    web: Cliente, operacion: str, metodo: str, ruta: str
) -> None:
    cuerpo = {"archivo": "a.mp4", "fuente_id": 1}
    r = web.llamar(operacion, metodo, ruta, esperado=403, headers=DEMO, json=cuerpo)
    assert r["codigo"] == "sin_permiso"


def test_el_permiso_se_exige_antes_que_la_configuracion(sin_carpeta: Cliente) -> None:
    """Sin carpeta Y sin permiso: 403, no 409 (no se cuenta cómo está el servidor)."""
    sin_carpeta.llamar("listarEntradaVideos", "GET", "/videos/entrada", esperado=403, headers=DEMO)


# ── GET /videos/entrada ────────────────────────────────────────────────────────────────────


def test_la_entrada_lista_solo_videos_utilizables_del_mas_nuevo_al_mas_viejo(
    web: Cliente, entrada: Path, tmp_path: Path
) -> None:
    _video(entrada, "viejo.mp4", b"1234", mtime=1_700_000_000)
    _video(entrada, "nuevo.MP4", b"12345", mtime=1_700_100_000)
    _video(entrada, ".oculto.mp4")
    _video(entrada, "notas.txt")
    _video(entrada, "vacio.mp4", b"")
    afuera = _video(tmp_path, "secreto.mp4")
    os.symlink(afuera, entrada / "enlace.mp4")
    (entrada / "carpeta.mp4").mkdir()
    r = web.llamar("listarEntradaVideos", "GET", "/videos/entrada", headers=ADMIN)
    assert [i["archivo"] for i in r["items"]] == ["nuevo.MP4", "viejo.mp4"]
    assert [i["bytes"] for i in r["items"]] == [5, 4]
    assert all(i["modificado"].endswith(("-03:00", "-04:00")) for i in r["items"])
    assert set(r["items"][0]) == {"archivo", "bytes", "modificado", "posible_duplicado"}
    _sin_rutas(r, str(tmp_path))


def test_una_carpeta_vacia_da_una_lista_vacia(web: Cliente) -> None:
    r = web.llamar("listarEntradaVideos", "GET", "/videos/entrada", headers=ADMIN)
    assert r == {"items": []}


def test_posible_duplicado_compara_nombre_y_tamano_y_solo_informa(
    web: Cliente, entrada: Path
) -> None:
    # `datos` sembró /datos/aaaaaa.mp4 con 10 bytes.
    _video(entrada, "aaaaaa.mp4", b"x" * 10)  # mismo nombre y tamaño -> posible duplicado
    _video(entrada, "bbbbbb.mp4", b"x" * 10)  # mismo tamaño, otro nombre
    _video(entrada, "cccccc.mp4", b"x" * 11)  # otro tamaño
    r = web.llamar("listarEntradaVideos", "GET", "/videos/entrada", headers=ADMIN)
    marcas = {i["archivo"]: i["posible_duplicado"] for i in r["items"]}
    assert marcas == {"aaaaaa.mp4": True, "bbbbbb.mp4": False, "cccccc.mp4": False}
    # Informa, no decide: un posible duplicado se puede pedir igual.
    _pedir(web, "aaaaaa.mp4")


def test_sin_carpeta_configurada_la_entrada_es_409(sin_carpeta: Cliente) -> None:
    r = sin_carpeta.llamar(
        "listarEntradaVideos", "GET", "/videos/entrada", esperado=409, headers=ADMIN
    )
    assert r["codigo"] == "entrada_no_configurada"


def test_una_carpeta_que_desaparecio_es_409_y_no_500(web: Cliente, entrada: Path) -> None:
    entrada.rmdir()
    r = web.llamar("listarEntradaVideos", "GET", "/videos/entrada", esperado=409, headers=ADMIN)
    assert r["codigo"] == "entrada_no_configurada"


# ── POST /videos ───────────────────────────────────────────────────────────────────────────


def test_pedir_un_video_responde_202_con_el_pedido_y_deja_auditoria(
    web: Cliente, entrada: Path, bd: Engine, tmp_path: Path
) -> None:
    _video(entrada, "cam1.mp4")
    r = _pedir(web, "cam1.mp4", 2)
    assert r["estado"] == "pendiente" and r["archivo"] == "cam1.mp4"
    assert r["fuente"]["id"] == 2 and r["fuente"]["nombre"]
    assert r["motivo"] is None and r["video_id"] is None
    assert r["creado_en"].endswith(("-03:00", "-04:00"))
    _sin_rutas(r, str(tmp_path))
    with bd.connect() as c:
        fila = c.execute(
            text("SELECT archivo, fuente_id, estado, usuario_id FROM pedido_ingesta")
        ).one()
        auditoria = c.execute(
            text(
                "SELECT accion, entidad, entidad_id, rol FROM auditoria"
                " WHERE accion = 'video:ingesta'"
            )
        ).one()
    assert (fila.archivo, fila.fuente_id, fila.estado) == ("cam1.mp4", 2, "pendiente")
    assert fila.usuario_id is not None
    assert (auditoria.entidad, auditoria.entidad_id, auditoria.rol) == (
        "pedido_ingesta",
        r["id"],
        "administrador",
    )


LARGO_MAXIMO = "a" * 251 + ".mp4"  # 255 bytes


@pytest.mark.parametrize(
    "archivo",
    [
        "",
        "../x.mp4",
        "a/b.mp4",
        "/etc/passwd",
        "a\\b.mp4",
        "a\x00.mp4",
        ".oculto.mp4",
        "..",
        "notas.txt",
        "sin_extension",
        "a" + LARGO_MAXIMO,  # 256 bytes: 422, no 500
        "á" * 126 + ".mp4",  # 256 bytes en 130 caracteres
    ],
)
def test_un_nombre_mal_formado_es_422(web: Cliente, archivo: str) -> None:
    r = _pedir(web, archivo, esperado=422)
    assert r["codigo"] == "peticion_invalida"
    _sin_rutas(r)


def test_un_surrogate_suelto_en_el_json_es_422_y_no_500(web: Cliente) -> None:
    """`\\ud800` es JSON válido pero no se puede escribir en UTF-8: no debe tumbar la API."""
    r = web.http.post(
        "/api/v1/videos",
        content='{"archivo": "\\ud800.mp4", "fuente_id": 1}',
        headers={**ADMIN, "Content-Type": "application/json"},
    )
    assert r.status_code == 422 and r.json()["codigo"] == "peticion_invalida"


def test_un_nombre_de_255_bytes_es_valido(web: Cliente, entrada: Path) -> None:
    _video(entrada, LARGO_MAXIMO)
    assert _pedir(web, LARGO_MAXIMO)["archivo"] == LARGO_MAXIMO


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"archivo": "a.mp4"},
        {"fuente_id": 1},
        {"archivo": "a.mp4", "fuente_id": 1, "ruta": "/etc/passwd"},
        {"archivo": 5, "fuente_id": 1},
        {"archivo": None, "fuente_id": 1},
        {"archivo": "a.mp4", "fuente_id": "uno"},
        {"archivo": "a.mp4", "fuente_id": None},
    ],
)
def test_un_cuerpo_que_no_cumple_el_contrato_es_422(web: Cliente, cuerpo: dict[str, Any]) -> None:
    r = web.llamar("pedirIngesta", "POST", "/videos", esperado=422, json=cuerpo, headers=ADMIN)
    assert r["codigo"] == "peticion_invalida"


def test_un_archivo_que_no_existe_es_404(web: Cliente) -> None:
    r = _pedir(web, "fantasma.mp4", esperado=404)
    assert r["codigo"] == "archivo_no_encontrado"


def test_enlaces_directorios_y_archivos_vacios_son_404(
    web: Cliente, entrada: Path, tmp_path: Path
) -> None:
    afuera = _video(tmp_path, "secreto.mp4")
    os.symlink(afuera, entrada / "enlace.mp4")
    (entrada / "carpeta.mp4").mkdir()
    _video(entrada, "vacio.mp4", b"")
    for nombre in ("enlace.mp4", "carpeta.mp4", "vacio.mp4"):
        assert _pedir(web, nombre, esperado=404)["codigo"] == "archivo_no_encontrado"


@pytest.mark.parametrize("fuente_id", [0, -1, 999])
def test_una_fuente_que_no_existe_es_404(web: Cliente, entrada: Path, fuente_id: int) -> None:
    _video(entrada, "a.mp4")
    r = _pedir(web, "a.mp4", fuente_id, esperado=404)
    assert r["codigo"] == "fuente_no_encontrada"


def test_una_fuente_desactivada_es_409(web: Cliente, entrada: Path, bd: Engine) -> None:
    _video(entrada, "a.mp4")
    with bd.begin() as c:
        c.execute(text("UPDATE fuente SET activa = false WHERE id = 2"))
    assert _pedir(web, "a.mp4", 2, esperado=409)["codigo"] == "fuente_inactiva"
    assert _pedir(web, "a.mp4", 1)["estado"] == "pendiente"  # la otra cámara sigue sirviendo


def test_sin_carpeta_configurada_pedir_es_409(sin_carpeta: Cliente) -> None:
    r = sin_carpeta.llamar(
        "pedirIngesta",
        "POST",
        "/videos",
        esperado=409,
        json={"archivo": "a.mp4", "fuente_id": 1},
        headers=ADMIN,
    )
    assert r["codigo"] == "entrada_no_configurada"


def test_el_mismo_archivo_dos_veces_es_409_hasta_que_el_pedido_se_cierra(
    web: Cliente, entrada: Path, bd: Engine
) -> None:
    _video(entrada, "a.mp4")
    primero = _pedir(web, "a.mp4")
    assert _pedir(web, "a.mp4", 2, esperado=409)["codigo"] == "pedido_existente"
    # El trabajador lo toma y lo rechaza: se puede volver a pedir.
    with Session(bd) as s, s.begin():
        tomado = pedidos.tomar_siguiente(s)
        assert tomado is not None and tomado.id == primero["id"]
        assert pedidos.rechazar(s, tomado.id, "mismo contenido ya registrado")
    assert _pedir(web, "a.mp4")["id"] != primero["id"]


def test_dos_pedidos_simultaneos_del_mismo_archivo_crean_uno_y_un_409(
    web: Cliente, entrada: Path, bd: Engine
) -> None:
    _video(entrada, "a.mp4")
    estados: list[int] = []
    barrera = threading.Barrier(2)

    def pedir() -> None:
        barrera.wait()
        r = web.http.post(
            "/api/v1/videos", json={"archivo": "a.mp4", "fuente_id": 1}, headers=ADMIN
        )
        estados.append(r.status_code)

    hilos = [threading.Thread(target=pedir) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    assert sorted(estados) == [202, 409]
    with bd.connect() as c:
        assert c.execute(text("SELECT count(*) FROM pedido_ingesta")).scalar_one() == 1


# ── GET /videos/pedidos ────────────────────────────────────────────────────────────────────


def test_los_pedidos_van_del_mas_nuevo_al_mas_viejo_con_la_camara_y_el_motivo(
    web: Cliente, entrada: Path, bd: Engine, tmp_path: Path
) -> None:
    _video(entrada, "a.mp4")
    _video(entrada, "b.mp4")
    a = _pedir(web, "a.mp4", 1)
    b = _pedir(web, "b.mp4", 2)
    with Session(bd) as s, s.begin():
        tomado = pedidos.tomar_siguiente(s)
        assert tomado is not None and tomado.id == a["id"]
        assert pedidos.rechazar(s, tomado.id, "el archivo cambió mientras se leía")
    r = web.llamar("listarPedidos", "GET", "/videos/pedidos", headers=ADMIN)
    assert [p["id"] for p in r["items"]] == [b["id"], a["id"]]
    nuevo, viejo = r["items"]
    assert (nuevo["estado"], nuevo["motivo"], nuevo["fuente"]["id"]) == ("pendiente", None, 2)
    assert (viejo["estado"], viejo["fuente"]["id"]) == ("rechazado", 1)
    assert viejo["motivo"] == "el archivo cambió mientras se leía"
    _sin_rutas(r, str(tmp_path))


def test_el_motivo_de_un_pedido_se_muestra_sin_rutas(
    web: Cliente, entrada: Path, bd: Engine, tmp_path: Path
) -> None:
    # Un motivo escrito por otra vía (o antes del saneo del trabajador) no sale con rutas.
    _video(entrada, "a.mp4")
    a = _pedir(web, "a.mp4", 1)
    with Session(bd) as s, s.begin():
        tomado = pedidos.tomar_siguiente(s)
        assert tomado is not None and tomado.id == a["id"]
        motivo = f"no se pudo leer: {entrada / 'a.mp4'} (copia en /srv/respaldo/a.mp4)"
        assert pedidos.rechazar(s, tomado.id, motivo)
    r = web.llamar("listarPedidos", "GET", "/videos/pedidos", headers=ADMIN)
    assert r["items"][0]["motivo"] == "no se pudo leer: a.mp4 (copia en a.mp4)"
    _sin_rutas(r, str(tmp_path))


def test_los_pedidos_se_listan_sin_carpeta_de_entrada(sin_carpeta: Cliente) -> None:
    """Solo lee la base: no depende de la carpeta."""
    assert sin_carpeta.llamar("listarPedidos", "GET", "/videos/pedidos", headers=ADMIN) == {
        "items": []
    }


@pytest.mark.parametrize(("creados", "listados"), [(0, 0), (49, 49), (50, 50), (51, 50), (55, 50)])
def test_se_listan_a_lo_mas_50_pedidos(
    web: Cliente, bd: Engine, creados: int, listados: int
) -> None:
    """El tope de 50, justo en el umbral y a cada lado."""
    with Session(bd) as s, s.begin():
        for i in range(creados):
            pedidos.crear(s, archivo=f"v{i}.mp4", fuente_id=1)
    r = web.llamar("listarPedidos", "GET", "/videos/pedidos", headers=ADMIN)
    assert len(r["items"]) == listados
    if creados:
        assert r["items"][0]["archivo"] == f"v{creados - 1}.mp4"
