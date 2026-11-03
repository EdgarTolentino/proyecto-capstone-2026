"""`rearmar-demo.sh` con un `docker` falso: el orden, las guardas y a qué proyecto toca.

Nada de docker real: el falso anota cada llamada y contesta lo que la prueba le pide.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "despliegue" / "local" / "rearmar-demo.sh"

DOCKER_FALSO = """#!/bin/bash
echo "$*" >> "$STUB_LOG"
if [ -n "$STUB_FALLA" ] && [[ "$*" == *"$STUB_FALLA"* ]]; then
  printf '%s' "$STUB_FALLA_SALIDA"; exit 1
fi
case "$*" in
  *"ps -q postgres"*) echo abc123 ;;
  *"--status paused --services"*) printf '%s\\n' $STUB_CORRIENDO ;;
  *"count(*) from video"*) printf '%s' "$STUB_VIDEOS" ;;
  *"count(*) from notificacion"*) printf '%s' "$STUB_AVISOS" ;;
  *"config --services"*) printf '%s\\n' $STUB_SERVICIOS ;;
  *"ps -a --format"*)
    for s in $STUB_SERVICIOS; do
      case "$s" in
        preparar|permisos|mediamtx|captura) echo "$s exited" ;;
        *)
          if [[ " $STUB_DETENIDOS " == *" $s "* ]]; then
            echo "$s exited"
          else
            echo "$s running"
          fi ;;
      esac
    done ;;
esac
"""


def correr(
    tmp_path: Path,
    *args: str,
    script: Path = SCRIPT,
    videos: str = "0",
    avisos: str = "0",
    entrada: str = "",
    **extra: str,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    falso = tmp_path / "bin"
    falso.mkdir(exist_ok=True)
    (falso / "docker").write_text(DOCKER_FALSO)
    (falso / "docker").chmod(0o755)
    registro = tmp_path / "docker.log"
    registro.write_text("")
    entorno = {
        "PATH": f"{falso}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "STUB_LOG": str(registro),
        "STUB_VIDEOS": videos,
        "STUB_AVISOS": avisos,
        "STUB_CORRIENDO": "trabajador despachador api",
        "STUB_SERVICIOS": "postgres redis preparar permisos trabajador api web despachador",
        "DEMO_PG_PASSWORD": "x",
        "DEMO_TOKEN": "y",
    } | extra
    entorno = {k: v for k, v in entorno.items() if v != "<sin>"}
    r = subprocess.run(
        ["bash", str(script), *args], input=entrada, capture_output=True, text=True, env=entorno
    )
    return r, registro.read_text().splitlines()


def primera(lineas: list[str], texto: str) -> int:
    return next(i for i, linea in enumerate(lineas) if texto in linea)


def test_el_orden_es_camara_escritores_carpetas_base_redis_y_de_vuelta(tmp_path: Path) -> None:
    servicios = "postgres redis preparar permisos trabajador api web despachador mediamtx"
    r, log = correr(tmp_path, "--yes", STUB_SERVICIOS=servicios)
    assert r.returncode == 0, r.stderr
    orden = [
        primera(log, "stop mediamtx"),
        primera(log, "stop trabajador"),
        primera(log, "stop api"),
        primera(log, "find /v /e -mindepth 1 -delete"),
        primera(log, "DROP DATABASE"),
        primera(log, "run --rm --no-deps preparar"),
        primera(log, "redis-cli flushall"),
        primera(log, "count(*) from notificacion"),
        primera(log, " up -d"),
    ]
    assert orden == sorted(orden) and len(set(orden)) == len(orden)


@pytest.mark.parametrize(
    ("videos", "procede"),
    [("0", True), ("1", False), ("", False), ("no-es-numero", False)],
    ids=["0_procede", "1_se_niega", "vacia_se_niega", "invalida_se_niega"],
)
def test_no_rearma_con_un_video_procesando_ni_si_no_puede_saberlo(
    tmp_path: Path, videos: str, procede: bool
) -> None:
    r, log = correr(tmp_path, "--yes", videos=videos)
    destructivo = any("DROP DATABASE" in x or "-delete" in x or "flushall" in x for x in log)
    assert (r.returncode == 0, destructivo) == (procede, procede), r.stderr
    if not procede:
        assert r.returncode == 3 and not any(" stop " in x for x in log)


def test_forzar_salta_la_guarda_del_video(tmp_path: Path) -> None:
    r, log = correr(tmp_path, "--yes", "--forzar", videos="2")
    assert r.returncode == 0 and any("DROP DATABASE" in x for x in log)


def test_solo_toca_el_proyecto_de_la_demo_y_nunca_el_redis_del_anfitrion(tmp_path: Path) -> None:
    _, log = correr(tmp_path, "--yes")
    for linea in log:
        assert linea.startswith("compose -p gepp-demo -f ") or (
            linea.startswith("run --rm --user root --entrypoint sh -v gepp-demo_vigilada:/v")
            and "-v gepp-demo_evidencia:/e" in linea
        ), linea
    assert not any("6379" in x or "REDIS_URL" in x for x in log)


@pytest.mark.parametrize(
    ("respuesta", "procede"), [("rearmar\n", True), ("no\n", False), ("", False)]
)
def test_sin_yes_pide_confirmacion(tmp_path: Path, respuesta: str, procede: bool) -> None:
    r, log = correr(tmp_path, entrada=respuesta)
    assert (r.returncode == 0) == procede
    assert any("DROP DATABASE" in x for x in log) == procede


def test_si_el_outbox_no_queda_en_cero_falla(tmp_path: Path) -> None:
    r, _ = correr(tmp_path, "--yes", avisos="1")
    assert r.returncode == 4 and "sin gastar" in r.stderr


def test_simular_no_llama_a_docker(tmp_path: Path) -> None:
    r, log = correr(tmp_path, "--simular", DEMO_PG_PASSWORD="<sin>", DEMO_TOKEN="<sin>")
    assert r.returncode == 0 and log == [] and "DROP DATABASE" in r.stdout


def test_sin_contrasena_o_con_opcion_desconocida_no_hace_nada(tmp_path: Path) -> None:
    r, log = correr(tmp_path, "--yes", DEMO_PG_PASSWORD="<sin>")
    assert r.returncode != 0 and log == []
    r, log = correr(tmp_path, "--borrar-todo")
    assert r.returncode == 2 and log == []


CON_CELULAR = {
    "DEMO_COMPOSE_ARCHIVOS": (
        "/ruta con espacio/local/compose.yml:/ruta con espacio/celular/compose.yml"
    ),
    "STUB_SERVICIOS": (
        "postgres redis preparar permisos trabajador api web despachador mediamtx borrador"
    ),
    "STUB_CORRIENDO": "mediamtx borrador trabajador despachador api",
}


def test_con_el_celular_cada_comando_lleva_los_dos_archivos_y_la_camara_queda_apagada(
    tmp_path: Path,
) -> None:
    r, log = correr(tmp_path, "--yes", **CON_CELULAR)
    assert r.returncode == 0, r.stderr
    dos = "-f /ruta con espacio/local/compose.yml -f /ruta con espacio/celular/compose.yml"
    for linea in (x for x in log if x.startswith("compose ")):
        assert dos in linea, linea  # en este orden: las rutas relativas salen del primero
    final = [x for x in log if " up -d " in x][-1].split()
    assert "borrador" in final and "trabajador" in final  # el borrador de privacidad SÍ vuelve
    assert "mediamtx" not in final and "captura" not in final  # un trozo gastaría la alerta
    assert primera(log, "stop mediamtx") < primera(log, "stop trabajador")
    assert primera(log, "stop borrador") < primera(log, "DROP DATABASE")
    assert "up -d mediamtx" in r.stdout  # el comando exacto para encender la cámara


def test_sin_el_celular_un_solo_archivo_y_nada_se_corta_por_servicios_que_no_existen(
    tmp_path: Path,
) -> None:
    r, log = correr(tmp_path, "--yes", STUB_CORRIENDO="trabajador api")
    assert r.returncode == 0, r.stderr  # mediamtx / borrador no existen y no se pide pararlos
    for linea in (x for x in log if x.startswith("compose ")):
        assert linea.count(" -f ") == 1, linea
    assert not any("mediamtx" in x or "borrador" in x for x in log)
    final = [x for x in log if " up -d " in x][-1].split()
    assert "api" in final and "web" in final


def test_armar_usa_los_mismos_archivos_construye_sin_la_camara_y_termina_rearmando(
    tmp_path: Path,
) -> None:
    r, log = correr(tmp_path, script=SCRIPT.with_name("armar-demo.sh"), **CON_CELULAR)
    assert r.returncode == 0, r.stderr
    construir = next(x for x in log if " up -d --build " in x)
    assert "-f /ruta con espacio/celular/compose.yml" in construir
    assert "borrador" in construir.split() and "mediamtx" not in construir.split()
    assert any("DROP DATABASE" in x for x in log)  # y quedó rearmado, con la alerta sin gastar


def _destructivo(log: list[str]) -> bool:
    return any(
        "DROP DATABASE" in x or "-delete" in x or "flushall" in x or " stop " in x for x in log
    )


@pytest.mark.parametrize(
    ("falla", "parcial"),
    [
        ("--status paused --services", "mediamtx api"),
        ("config --services", "postgres redis api web"),  # falla pero ya imprimió algo
    ],
    ids=["listar_corriendo", "servicios"],
)
def test_si_falla_el_listado_se_aborta_antes_de_borrar_nada(
    tmp_path: Path, falla: str, parcial: str
) -> None:
    r, log = correr(tmp_path, "--yes", STUB_FALLA=falla, STUB_FALLA_SALIDA=parcial)
    assert r.returncode == 6 and "no se tocó nada" in r.stderr
    assert not _destructivo(log)


def test_sin_servicios_que_levantar_se_aborta_antes_de_borrar(tmp_path: Path) -> None:
    r, log = correr(tmp_path, "--yes", STUB_SERVICIOS="")
    assert r.returncode == 6 and not _destructivo(log)


@pytest.mark.parametrize(
    "salida", ["0", "9", ""], ids=["cero_con_error", "nueve_con_error", "vacia"]
)
def test_la_guarda_de_videos_exige_salida_cero_y_numero(tmp_path: Path, salida: str) -> None:
    r, log = correr(tmp_path, "--yes", STUB_FALLA="count(*) from video", STUB_FALLA_SALIDA=salida)
    assert r.returncode == 3 and not _destructivo(log)


def test_si_falla_preparar_dice_exactamente_como_terminar_y_repetir_no_tropieza(
    tmp_path: Path,
) -> None:
    r, log = correr(tmp_path, "--yes", STUB_FALLA="run --rm --no-deps preparar")
    assert r.returncode == 7 and "DESPUÉS de borrar" in r.stderr
    for pista in ("--forzar --yes", "preparar", "redis-cli flushall", "up -d"):
        assert pista in r.stderr, pista
    assert not any("flushall" in x for x in log)  # se detuvo ahí
    # Repetir: la base quedó sin tablas, la guarda de videos falla; --forzar la salta y termina.
    r2, log2 = correr(tmp_path, "--yes", "--forzar", STUB_FALLA="count(*) from video")
    assert r2.returncode == 0, r2.stderr
    assert not any("count(*) from video" in x for x in log2)


@pytest.mark.parametrize(
    ("falla", "salida"),
    [("ps -a --format", "boom"), ("ps -a --format", "")],
    ids=["error", "vacio"],
)
def test_un_fallo_al_esperar_los_servicios_no_se_anuncia_como_exito(
    tmp_path: Path, falla: str, salida: str
) -> None:
    r, _ = correr(tmp_path, "--yes", STUB_FALLA=falla, STUB_FALLA_SALIDA=salida)
    assert r.returncode == 7 and "listar el estado" in r.stderr
    assert "listo" not in r.stdout


TRABAJADORES = "postgres redis preparar permisos trabajador trabajador-cpu api web despachador"


@pytest.mark.parametrize(
    ("corriendo", "perfiles", "esperado"),
    [
        ("trabajador-cpu api", "", "trabajador-cpu"),  # sin perfil, el CPU NO se cambia por el GPU
        ("trabajador api", "cpu", "trabajador"),  # con perfil cpu, el GPU NO se suma al CPU
        ("api", "cpu", "trabajador-cpu"),  # ninguno corría: manda el perfil
        ("api", "", "trabajador"),
    ],
    ids=["cpu_sin_perfil", "gpu_con_perfil", "ninguno_con_perfil", "ninguno_sin_perfil"],
)
def test_se_levanta_el_trabajador_que_corria_y_nunca_los_dos(
    tmp_path: Path, corriendo: str, perfiles: str, esperado: str
) -> None:
    extra = {"COMPOSE_PROFILES": perfiles} if perfiles else {}
    r, log = correr(
        tmp_path, "--yes", STUB_SERVICIOS=TRABAJADORES, STUB_CORRIENDO=corriendo, **extra
    )
    assert r.returncode == 0, r.stderr
    final = [x for x in log if " up -d " in x][-1].split()
    elegidos = {"trabajador", "trabajador-cpu"} & set(final)
    assert elegidos == {esperado}


def test_dos_trabajadores_a_la_vez_se_aborta_y_la_variable_lo_resuelve(tmp_path: Path) -> None:
    dos = {"STUB_SERVICIOS": TRABAJADORES, "STUB_CORRIENDO": "trabajador trabajador-cpu api"}
    r, log = correr(tmp_path, "--yes", **dos)
    assert r.returncode == 2 and not _destructivo(log)
    r, log = correr(tmp_path, "--yes", DEMO_TRABAJADOR="trabajador-cpu", **dos)
    final = [x for x in log if " up -d " in x][-1].split()
    assert r.returncode == 0 and "trabajador-cpu" in final and "trabajador" not in final
    r, log = correr(tmp_path, "--yes", DEMO_TRABAJADOR="otro", **dos)
    assert r.returncode == 2 and not _destructivo(log)


def test_se_detiene_siempre_a_quien_escribe_aunque_no_figure_corriendo(tmp_path: Path) -> None:
    """Un contenedor en `restarting` no sale en `ps --status running` y volvería a arrancar."""
    r, log = correr(
        tmp_path, "--yes", STUB_CORRIENDO="api"
    )  # trabajador y despachador: no listados
    assert r.returncode == 0, r.stderr
    for servicio in ("trabajador", "despachador", "api", "web"):
        assert any(x.endswith(f" stop {servicio}") for x in log), servicio
    assert primera(log, "stop trabajador") < primera(log, "DROP DATABASE")
    assert not any(x.endswith(" stop borrador") or x.endswith(" stop mediamtx") for x in log)


def test_el_comando_de_recuperacion_lleva_el_trabajador_el_perfil_y_los_archivos(
    tmp_path: Path,
) -> None:
    r, _ = correr(
        tmp_path,
        "--yes",
        STUB_FALLA="run --rm --no-deps preparar",
        STUB_SERVICIOS=TRABAJADORES,
        STUB_CORRIENDO="trabajador-cpu api",
        DEMO_COMPOSE_ARCHIVOS="/a/compose.yml:/b/compose.yml",
    )
    assert r.returncode == 7
    orden = next(x for x in r.stderr.splitlines() if "--forzar --yes" in x)
    for pieza in (
        "DEMO_TRABAJADOR=trabajador-cpu",
        "COMPOSE_PROFILES=cpu",
        "DEMO_COMPOSE_ARCHIVOS=",
    ):
        assert pieza in orden, pieza
    assert "up -d" in r.stderr and "trabajador-cpu" in r.stderr.split("up -d")[-1]


def test_la_recuperacion_de_la_gpu_no_pide_el_perfil_cpu(tmp_path: Path) -> None:
    r, _ = correr(
        tmp_path, "--yes", STUB_FALLA="run --rm --no-deps preparar", STUB_CORRIENDO="trabajador api"
    )
    orden = next(x for x in r.stderr.splitlines() if "--forzar --yes" in x)
    assert "DEMO_TRABAJADOR=trabajador" in orden and "COMPOSE_PROFILES" not in orden


def test_la_espera_solo_mira_lo_que_se_levanto(tmp_path: Path) -> None:
    """Con el CPU elegido, el trabajador GPU detenido a propósito no cuenta como caído."""
    r, _ = correr(
        tmp_path,
        "--yes",
        STUB_SERVICIOS=TRABAJADORES,
        STUB_CORRIENDO="trabajador-cpu api",
        STUB_DETENIDOS="trabajador",
    )
    assert r.returncode == 0, r.stderr
    r, _ = correr(  # y un servicio que SÍ se levantó y no corre, sigue siendo un fallo
        tmp_path,
        "--yes",
        STUB_SERVICIOS=TRABAJADORES,
        STUB_CORRIENDO="trabajador-cpu api",
        STUB_DETENIDOS="trabajador api",
        DEMO_ESPERA_S="1",
    )
    assert r.returncode == 5 and "api exited" in r.stderr


ARMAR = SCRIPT.with_name("armar-demo.sh")


@pytest.mark.parametrize(
    ("perfiles", "esperado"), [("", "trabajador"), ("cpu", "trabajador-cpu")], ids=["gpu", "cpu"]
)
def test_armar_levanta_un_solo_trabajador(tmp_path: Path, perfiles: str, esperado: str) -> None:
    extra = {"COMPOSE_PROFILES": perfiles} if perfiles else {}
    r, log = correr(tmp_path, script=ARMAR, STUB_SERVICIOS=TRABAJADORES, **extra)
    assert r.returncode == 0, r.stderr
    construir = next(x for x in log if " up -d --build " in x).split()
    assert {"trabajador", "trabajador-cpu"} & set(construir) == {esperado}


def test_armar_aborta_si_no_puede_listar_y_rechaza_un_trabajador_invalido(tmp_path: Path) -> None:
    r, log = correr(tmp_path, script=ARMAR, STUB_FALLA="config --services", STUB_FALLA_SALIDA="a b")
    assert r.returncode == 6 and not any(" up -d " in x for x in log)
    r, log = correr(tmp_path, script=ARMAR, DEMO_TRABAJADOR="otro")
    assert r.returncode == 2 and not any(" up -d " in x for x in log)


def test_si_corre_un_servicio_que_no_esta_en_los_archivos_se_aborta_antes_de_borrar(
    tmp_path: Path,
) -> None:
    """Revisión de Codex: la cámara del override corriendo y DEMO_COMPOSE_ARCHIVOS sin definir.
    No se la podría detener; borrar y anunciar «cámara apagada» mientras graba sería mentir."""
    r, log = correr(tmp_path, "--yes", STUB_CORRIENDO="mediamtx trabajador despachador api")
    assert r.returncode == 6
    assert "mediamtx" in r.stderr and "DEMO_COMPOSE_ARCHIVOS" in r.stderr
    assert not _destructivo(log)
