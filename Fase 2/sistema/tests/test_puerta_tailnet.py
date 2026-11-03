"""La puerta de la tailnet (nginx :8081).

`identidades.sh` se prueba siempre (solo `sh`). La plantilla se prueba con `nginx:alpine` en
Docker real y se salta si no hay Docker o la imagen (no se descarga). Qué cuida cada prueba:
sin `Tailscale-User-Login` de la lista no pasa nada (403) y el token del bundle nunca llega a
la API por esa puerta.
"""

import http.client
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

LOCAL = Path(__file__).resolve().parents[1] / "despliegue" / "local"
SCRIPT = LOCAL / "identidades.sh"
ENTRYPOINT_WEB = yaml.safe_load((LOCAL / "compose.yml").read_text())["services"]["web"][
    "entrypoint"
]
LISTA = "ana@equipo.invalid=tokana01,luis@equipo.invalid=tokluis2"


def _script(modo: str, identidades: str | None, **entorno: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin", **entorno}
    if identidades is not None:
        env["DEMO_IDENTIDADES"] = identidades
    return subprocess.run(
        ["sh", str(SCRIPT), modo], env=env, capture_output=True, text=True, check=False
    )


def test_las_dos_salidas_salen_de_la_misma_lista() -> None:
    nginx = _script("nginx", LISTA)
    api = _script("api", LISTA)
    assert nginx.returncode == 0 and api.returncode == 0
    assert '"ana@equipo.invalid" "tokana01";' in nginx.stdout
    assert '"luis@equipo.invalid" "tokluis2";' in nginx.stdout
    assert api.stdout.strip() == "tokana01=ana@equipo.invalid,tokluis2=luis@equipo.invalid"


def test_el_correo_va_en_minusculas_en_nginx_y_en_la_api() -> None:
    # la API busca el correo EXACTO de la tabla `usuario`; nginx no distingue mayúsculas
    assert _script("api", "ANA@equipo.invalid=t2").stdout.strip() == "t2=ana@equipo.invalid"
    assert '"ana@equipo.invalid" "t2";' in _script("nginx", "ANA@equipo.invalid=t2").stdout


@pytest.mark.parametrize("control", ["\n", "\r", "\t", "\x1b"])
def test_un_caracter_de_control_en_cualquier_parte_hace_fallar_el_arranque(control: str) -> None:
    # `grep` valida por línea: una línea buena no debe dejar pasar el resto (inyección en el mapa)
    lista = f'a@b.invalid=t,c@d.invalid=ok{control}";{control}"" "t'
    for modo in ("nginx", "api"):
        assert _script(modo, lista).returncode == 1, (modo, repr(control))
    assert _script("nginx", "a@b.invalid=t,c@d.invalid=ok").returncode == 0  # sin control: pasa


def test_un_token_de_persona_no_puede_ser_el_del_bundle() -> None:
    for modo in ("nginx", "api"):
        # la API hace `.strip()` del token: con espacios o tabuladores en los extremos es el mismo
        for bundle in ("tok1", "tok1 ", " tok1", "tok1\t", "tok1\n", "\r tok1 \x0b"):
            assert _script(modo, "a@b.invalid=tok1", DEMO_TOKEN=bundle).returncode == 1, repr(
                bundle
            )
        assert _script(modo, "a@b.invalid=tok1", DEMO_TOKEN="tok12").returncode == 0  # otro token
        assert _script(modo, "a@b.invalid=tok1", DEMO_TOKEN="").returncode == 0


@pytest.mark.parametrize("lista", [None, "", ",,"])
def test_lista_vacia_o_sin_definir_no_deja_a_nadie(lista: str | None) -> None:
    nginx = _script("nginx", lista)
    assert nginx.returncode == 0
    assert 'default "";\n}' in nginx.stdout  # el mapa no tiene ninguna persona
    assert _script("api", lista).stdout.strip() == ""


@pytest.mark.parametrize(
    "lista",
    [
        "ana@equipo.invalid",  # sin «=»
        "ana@equipo.invalid=",  # token vacío
        "=tok123",  # correo vacío
        'ana@equipo.invalid=tok"; return 200; #',  # intento de cerrar la cadena
        "ana@equipo.invalid=tok$http_host",  # variable de nginx
        "ana@equipo.invalid=tok 1",  # espacio
        "ana@equipo.invalid=ab=cd",  # «=» en el token: la API lo partiría en otro lugar
        "ana@equipo.invalid=a@b",  # los tokens no llevan @, % ni +
        "ana@equipo.invalid=a+b",
        "ana@equipo.invalid=tok1,ANA@equipo.invalid=tok2",  # correo repetido (sin mayúsculas)
        "ana@equipo.invalid=tok1,luis@equipo.invalid=tok1",  # token repetido
        "sin-arroba=tok1",
    ],
)
def test_una_lista_mal_formada_hace_fallar_el_arranque(lista: str) -> None:
    for modo in ("nginx", "api"):
        r = _script(modo, lista)
        assert r.returncode == 1, (modo, lista)
        secreto = lista.split(",")[-1].split("=", 1)[-1]
        assert not secreto or secreto not in r.stderr  # el mensaje no repite el token


# ───────────── nginx real ─────────────


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


def _hay_docker() -> bool:
    if shutil.which("docker") is None:
        return False
    return _docker("image", "inspect", "nginx:alpine", check=False).returncode == 0


requiere_docker = pytest.mark.skipif(
    not _hay_docker(), reason="sin Docker o sin nginx:alpine local"
)

# «API» falsa: devuelve el Authorization y la identidad que recibe.
ECO = """
server {
    listen 9000;
    location / { return 200 "$http_authorization|$http_tailscale_user_login"; }
}
"""


class Nginx:
    def __init__(self, nombre: str, puertos: dict[int, int]) -> None:
        self.nombre, self.puertos = nombre, puertos

    def pedir(
        self, puerto: int, metodo: str, ruta: str, **cabeceras: str
    ) -> tuple[int, str, dict[str, str]]:
        conn = http.client.HTTPConnection("127.0.0.1", self.puertos[puerto], timeout=10)
        conn.request(metodo, ruta, body=b"x" if metodo == "POST" else None, headers=cabeceras)
        r = conn.getresponse()
        return r.status, r.read().decode(), {k.lower(): v for k, v in r.getheaders()}


def _levantar(tmp: Path, identidades: str, red: str | None) -> Nginx:
    eco = tmp / "eco.conf"
    eco.write_text(ECO)
    nombre = f"puerta-{uuid.uuid4().hex[:8]}"
    comando = [
        "run", "-d", "--name", nombre, "-p", "127.0.0.1::8080", "-p", "127.0.0.1::8081",
        "-e", "API_UPSTREAM=127.0.0.1:9000", "-e", f"DEMO_IDENTIDADES={identidades}",
        "-v", f"{LOCAL / 'nginx.conf.template'}:/etc/nginx/templates/default.conf.template:ro",
        "-v", f"{SCRIPT}:/identidades.sh:ro", "-v", f"{eco}:/etc/nginx/conf.d/eco.conf:ro",
        *(["--network", red] if red else []),
        "--entrypoint", ENTRYPOINT_WEB[0], "nginx:alpine", *ENTRYPOINT_WEB[1:],
    ]  # fmt: skip
    _docker(*comando)
    puertos = {}
    try:
        for interno in (8080, 8081):
            salida = _docker("port", nombre, str(interno)).stdout.split()[0]
            puertos[interno] = int(salida.rsplit(":", 1)[1])
    except subprocess.CalledProcessError:  # nginx no arrancó: no dejar el contenedor
        registro = _docker("logs", nombre, check=False)
        _docker("rm", "-f", nombre, check=False)
        pytest.fail(f"nginx no arrancó:\n{registro.stdout}{registro.stderr}")
    nginx = Nginx(nombre, puertos)
    for _ in range(50):
        try:
            nginx.pedir(8080, "GET", "/")
            break
        except OSError:
            subprocess.run(["sleep", "0.2"], check=False)
    return nginx


@pytest.fixture
def red() -> Iterator[str]:
    nombre = f"red-{uuid.uuid4().hex[:8]}"
    _docker("network", "create", nombre)
    yield nombre
    _docker("network", "rm", nombre, check=False)


@pytest.fixture
def nginx(tmp_path: Path, red: str) -> Iterator[Nginx]:
    n = _levantar(tmp_path, LISTA, red)
    yield n
    _docker("rm", "-f", n.nombre, check=False)


@requiere_docker
def test_la_plantilla_pasa_nginx_t(nginx: Nginx) -> None:
    r = _docker("exec", nginx.nombre, "nginx", "-t", check=False)
    assert r.returncode == 0, r.stderr


@requiere_docker
@pytest.mark.parametrize("ruta", ["/", "/api/v1/yo"])
@pytest.mark.parametrize(
    "cabeceras",
    [
        {},  # sin cabecera de identidad
        {"Tailscale-User-Login": "otro@equipo.invalid"},  # fuera de la lista
        {"Tailscale-User-Login": ""},
        {"Authorization": "Bearer token-del-bundle"},  # el token del bundle NO basta
    ],
)
def test_sin_persona_de_la_lista_todo_es_403(nginx: Nginx, ruta: str, cabeceras: dict) -> None:
    assert nginx.pedir(8081, "GET", ruta, **cabeceras)[0] == 403


@requiere_docker
def test_con_persona_la_api_recibe_su_token_y_no_el_del_navegador(nginx: Nginx) -> None:
    for login, token in (("ana@equipo.invalid", "tokana01"), ("LUIS@equipo.invalid", "tokluis2")):
        estado, cuerpo, _ = nginx.pedir(
            8081, "GET", "/api/v1/yo",
            **{"Tailscale-User-Login": login, "Authorization": "Bearer token-del-bundle"},
        )  # fmt: skip
        assert estado == 200
        assert cuerpo == f"Bearer {token}|"  # su token; la identidad no sigue hacia la API


@requiere_docker
def test_la_puerta_local_sigue_pasando_el_token_del_bundle(nginx: Nginx) -> None:
    estado, cuerpo, _ = nginx.pedir(
        8080, "GET", "/api/v1/yo", Authorization="Bearer token-del-bundle"
    )
    assert (estado, cuerpo) == (200, "Bearer token-del-bundle|")
    assert nginx.pedir(8080, "GET", "/")[0] == 200


@requiere_docker
def test_lista_vacia_la_puerta_de_la_tailnet_dice_403_a_todo(tmp_path: Path, red: str) -> None:
    n = _levantar(tmp_path, "", red)
    try:
        for ruta in ("/", "/api/v1/yo"):
            login = {"Tailscale-User-Login": "ana@equipo.invalid"}
            assert n.pedir(8081, "GET", ruta, **login)[0] == 403
        assert n.pedir(8080, "GET", "/")[0] == 200  # la local no depende de la lista
    finally:
        _docker("rm", "-f", n.nombre, check=False)
