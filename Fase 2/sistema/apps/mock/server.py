"""API simulada de Guardián EPP para desarrollar la bandeja y el visor.

Usa solamente la biblioteca estándar. Los cambios duran hasta reiniciar el proceso.
"""

from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, urlparse

# Esta es una sesión de demostración, no una credencial real.
TOKEN_DEMO = "Bearer demo"
AVISO_LEGAL = "Indicio automatizado. Requiere validación humana."
ESTADOS = {"por_revisar", "confirmado", "falso_positivo", "duplicado", "pospuesto"}
EPP = {"casco", "chaleco", "lentes", "guantes", "arnes", "calzado"}
ORDENES = {
    "recomendado",
    "ts_inicio_desc",
    "ts_inicio_asc",
    "severidad_desc",
    "duracion_desc",
    "confianza_desc",
}

# Los catálogos se comparten entre filtros, filas y detalle.
OBRAS = [{"id": 1, "nombre": "Edificio Mirador Norte"}]
AREAS = {
    1: {"id": 1, "nombre": "Andamio Fachada Norte"},
    2: {"id": 2, "nombre": "Excavación y Fundaciones"},
    3: {"id": 3, "nombre": "Patio de Maniobras"},
    4: {"id": 4, "nombre": "Losa Nivel 3"},
    5: {"id": 5, "nombre": "Bodega de Materiales"},
}
ZONAS = {
    11: {"id": 11, "nombre": "Plataforma N4"},
    12: {"id": 12, "nombre": "Plataforma N3"},
    21: {"id": 21, "nombre": "Talud sur"},
    22: {"id": 22, "nombre": "Acceso maquinaria"},
    23: {"id": 23, "nombre": "Hormigonado"},
    31: {"id": 31, "nombre": "Zona de grúa"},
    32: {"id": 32, "nombre": "Pasillo peatonal"},
    41: {"id": 41, "nombre": "Borde oriente"},
    42: {"id": 42, "nombre": "Enfierradura"},
    43: {"id": 43, "nombre": "Corte de moldaje"},
    44: {"id": 44, "nombre": "Borde poniente"},
    51: {"id": 51, "nombre": "Corte y esmerilado"},
    52: {"id": 52, "nombre": "Acopio"},
    53: {"id": 53, "nombre": "Mesón de corte"},
}
FUENTES = {
    1: {"id": 1, "nombre": "CAM-04 Fachada Norte"},
    2: {"id": 2, "nombre": "CAM-01 Acceso Obra"},
    3: {"id": 3, "nombre": "CAM-09 Patio"},
    4: {"id": 4, "nombre": "CAM-07 Losa N3"},
}
TURNOS = [
    {"codigo": "A", "etiqueta": "Turno A (07:00-15:00)"},
    {"codigo": "B", "etiqueta": "Turno B (15:00-23:00)"},
]
RESPONSABLES = {
    7: {"id": 7, "nombre": "Prevencionista de turno"},
    8: {"id": 8, "nombre": "Supervisor de obra"},
    9: {"id": 9, "nombre": "Supervisor Losa N3"},
}
SESION = {
    "id": 7,
    "nombre": "Prevencionista de turno",
    "rol": "prevencionista",
    "area_id": None,
    "permisos": [
        "ver_hallazgos",
        "triar_hallazgos",
        "ver_evidencia",
        "ver_reportes",
        "asignar_acciones",
    ],
}

# Cada EPP usa una regla sencilla en el bloque "por qué se disparó".
REGLAS = {
    "arnes": (18, "Arnés obligatorio en altura", 2),
    "casco": (12, "Casco obligatorio en obra", 3),
    "chaleco": (15, "Alta visibilidad en circulación", 1),
    "lentes": (21, "Protección ocular en corte", 2),
    "guantes": (24, "Protección de manos", 1),
    "calzado": (27, "Calzado de seguridad", 1),
}


def crear_hallazgo(
    hallazgo_id: int,
    area_id: int,
    zona_id: int,
    fuente_id: int,
    epp_faltante: list[str],
    severidad: int,
    inicio: str,
    duracion: float,
    estado: str,
    confianza: float,
    asignado_id: int | None,
    reincidente: bool,
    turno: str,
) -> dict[str, Any]:
    """Arma un hallazgo con los nombres exactos del contrato."""

    inicio_dt = datetime.fromisoformat(inicio)
    fin_dt = inicio_dt + timedelta(seconds=duracion)
    evidencia_id = hallazgo_id * 10

    return {
        "id": hallazgo_id,
        "area": copy.deepcopy(AREAS[area_id]),
        "zona": copy.deepcopy(ZONAS[zona_id]),
        "fuente": copy.deepcopy(FUENTES[fuente_id]),
        "epp_faltante": epp_faltante,
        "severidad": severidad,
        "ts_inicio": inicio_dt.isoformat(timespec="seconds"),
        "ts_fin": fin_dt.isoformat(timespec="seconds"),
        "duracion_s": duracion,
        # A 5 fps algunos cuadros se descartan. Por eso usamos 4,75.
        "cuadros_confirmados": int(duracion * 4.75),
        "confianza_media": confianza,
        "estado": estado,
        "miniatura_url": f"/api/v1/evidencias/{evidencia_id}/miniatura",
        "asignado_a": copy.deepcopy(RESPONSABLES.get(asignado_id)),
        "reincidente": reincidente,
        "aviso_legal": AVISO_LEGAL,
        # Estas claves sirven para filtrar, pero no salen en el JSON público.
        "_obra_id": 1,
        "_turno": turno,
        "_evidencia_id": evidencia_id,
    }


# Los 16 casos vienen del diseño aprobado para la issue 11.
FILAS = [
    (
        2418,
        1,
        11,
        1,
        ["arnes"],
        4,
        "2026-09-03T10:14:07-03:00",
        192.0,
        "por_revisar",
        0.91,
        None,
        True,
        "A",
    ),
    (
        2417,
        2,
        21,
        2,
        ["casco"],
        4,
        "2026-09-03T08:22:40-03:00",
        107.0,
        "por_revisar",
        0.88,
        None,
        False,
        "A",
    ),
    (
        2416,
        3,
        31,
        3,
        ["chaleco"],
        3,
        "2026-09-03T07:41:55-03:00",
        48.0,
        "por_revisar",
        0.76,
        None,
        False,
        "A",
    ),
    (
        2415,
        4,
        41,
        4,
        ["casco", "chaleco"],
        3,
        "2026-09-02T14:02:31-03:00",
        65.0,
        "confirmado",
        0.83,
        9,
        True,
        "A",
    ),
    (
        2414,
        5,
        51,
        3,
        ["lentes"],
        2,
        "2026-09-02T09:18:44-03:00",
        150.0,
        "falso_positivo",
        0.64,
        7,
        False,
        "A",
    ),
    (
        2413,
        1,
        12,
        1,
        ["arnes"],
        4,
        "2026-09-02T11:36:02-03:00",
        82.0,
        "por_revisar",
        0.87,
        None,
        True,
        "A",
    ),
    (
        2412,
        4,
        42,
        4,
        ["casco"],
        3,
        "2026-09-03T12:05:18-03:00",
        56.0,
        "por_revisar",
        0.79,
        None,
        False,
        "A",
    ),
    (
        2411,
        5,
        52,
        3,
        ["guantes"],
        1,
        "2026-09-03T13:44:09-03:00",
        70.0,
        "por_revisar",
        0.58,
        None,
        False,
        "A",
    ),
    (
        2410,
        2,
        22,
        2,
        ["chaleco"],
        3,
        "2026-09-02T08:57:33-03:00",
        124.0,
        "confirmado",
        0.81,
        8,
        False,
        "A",
    ),
    (
        2409,
        1,
        11,
        1,
        ["casco", "arnes"],
        4,
        "2026-09-01T16:12:47-03:00",
        278.0,
        "confirmado",
        0.93,
        8,
        True,
        "B",
    ),
    (
        2408,
        4,
        43,
        4,
        ["lentes"],
        2,
        "2026-09-02T15:29:56-03:00",
        38.0,
        "por_revisar",
        0.67,
        None,
        False,
        "B",
    ),
    (
        2407,
        3,
        32,
        3,
        ["calzado"],
        1,
        "2026-09-01T17:02:14-03:00",
        27.0,
        "falso_positivo",
        0.55,
        7,
        False,
        "B",
    ),
    (
        2406,
        3,
        31,
        3,
        ["chaleco"],
        3,
        "2026-09-02T07:12:03-03:00",
        93.0,
        "por_revisar",
        0.74,
        None,
        True,
        "A",
    ),
    (
        2405,
        2,
        23,
        2,
        ["guantes"],
        2,
        "2026-09-01T10:48:21-03:00",
        118.0,
        "por_revisar",
        0.62,
        None,
        False,
        "A",
    ),
    (
        2404,
        4,
        44,
        4,
        ["arnes"],
        4,
        "2026-09-02T09:03:39-03:00",
        167.0,
        "por_revisar",
        0.90,
        None,
        False,
        "A",
    ),
    (
        2403,
        5,
        53,
        3,
        ["lentes"],
        1,
        "2026-09-01T11:51:07-03:00",
        44.0,
        "duplicado",
        0.53,
        7,
        False,
        "A",
    ),
]
HALLAZGOS = [crear_hallazgo(*fila) for fila in FILAS]

# El bloqueo evita que dos peticiones cambien la lista al mismo tiempo.
HALLAZGOS_LOCK = Lock()


def ruta_api(path: str) -> str:
    """Quita el prefijo opcional `/api/v1`."""

    ruta = path.rstrip("/") or "/"
    if ruta == "/api/v1":
        return "/"
    if ruta.startswith("/api/v1/"):
        return ruta[len("/api/v1") :]
    return ruta


def valores_url(parametros: dict[str, list[str]], nombre: str) -> list[str]:
    """Lee valores repetidos o separados por coma."""

    valores: list[str] = []
    for grupo in parametros.get(nombre, []):
        valores.extend(valor.strip() for valor in grupo.split(",") if valor.strip())
    return valores


def entero_url(
    parametros: dict[str, list[str]], nombre: str, minimo: int | None = None
) -> int | None:
    """Lee un número entero de la URL."""

    texto = parametros.get(nombre, [None])[0]
    if texto is None:
        return None
    try:
        valor = int(texto)
    except ValueError as error:
        raise ValueError(f"'{nombre}' debe ser un número entero") from error
    if minimo is not None and valor < minimo:
        raise ValueError(f"'{nombre}' debe ser mayor o igual a {minimo}")
    return valor


def fecha_url(parametros: dict[str, list[str]], nombre: str) -> datetime | None:
    """Lee una fecha ISO 8601 con zona horaria."""

    texto = parametros.get(nombre, [None])[0]
    if texto is None:
        return None
    try:
        fecha = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"'{nombre}' debe ser una fecha ISO 8601") from error
    if fecha.tzinfo is None:
        raise ValueError(f"'{nombre}' debe incluir la zona horaria")
    return fecha


def publico(hallazgo: dict[str, Any]) -> dict[str, Any]:
    """Quita las claves internas antes de responder."""

    datos = {clave: valor for clave, valor in hallazgo.items() if not clave.startswith("_")}
    return copy.deepcopy(datos)


def buscar(hallazgo_id: int) -> dict[str, Any] | None:
    """Busca un hallazgo por su identificador."""

    return next((item for item in HALLAZGOS if item["id"] == hallazgo_id), None)


def filtrar(
    hallazgos: list[dict[str, Any]],
    parametros: dict[str, list[str]],
    incluir_estado: bool,
) -> list[dict[str, Any]]:
    """Aplica los filtros definidos en OpenAPI."""

    resultado = hallazgos
    estado = parametros.get("estado", [None])[0]

    if incluir_estado and estado:
        if estado in {"descartado", "descartados"}:
            resultado = [
                item for item in resultado if item["estado"] in {"falso_positivo", "duplicado"}
            ]
        elif estado == "reincidente":
            resultado = [item for item in resultado if item["reincidente"]]
        elif estado in ESTADOS:
            resultado = [item for item in resultado if item["estado"] == estado]
        else:
            raise ValueError("'estado' no es válido")

    severidades_texto = valores_url(parametros, "severidad")
    if severidades_texto:
        try:
            severidades = {int(valor) for valor in severidades_texto}
        except ValueError as error:
            raise ValueError("'severidad' debe usar números del 1 al 4") from error
        if not severidades <= {1, 2, 3, 4}:
            raise ValueError("'severidad' debe usar números del 1 al 4")
        resultado = [item for item in resultado if item["severidad"] in severidades]

    epp = set(valores_url(parametros, "epp"))
    if epp:
        if not epp <= EPP:
            raise ValueError("'epp' contiene un valor no válido")
        resultado = [item for item in resultado if epp.intersection(item["epp_faltante"])]

    for parametro, campo in (("area_id", "area"), ("zona_id", "zona"), ("fuente_id", "fuente")):
        valor = entero_url(parametros, parametro)
        if valor is not None:
            resultado = [item for item in resultado if item[campo]["id"] == valor]

    obra_id = entero_url(parametros, "obra_id")
    if obra_id is not None:
        resultado = [item for item in resultado if item["_obra_id"] == obra_id]

    turno = parametros.get("turno", [None])[0]
    if turno:
        resultado = [item for item in resultado if item["_turno"] == turno]

    reincidente = parametros.get("reincidente", [None])[0]
    if reincidente is not None:
        if reincidente.lower() not in {"true", "false", "1", "0"}:
            raise ValueError("'reincidente' debe ser true o false")
        esperado = reincidente.lower() in {"true", "1"}
        resultado = [item for item in resultado if item["reincidente"] is esperado]

    desde = fecha_url(parametros, "desde")
    hasta = fecha_url(parametros, "hasta")
    if desde is not None:
        resultado = [
            item for item in resultado if datetime.fromisoformat(item["ts_inicio"]) >= desde
        ]
    if hasta is not None:
        resultado = [
            item for item in resultado if datetime.fromisoformat(item["ts_inicio"]) <= hasta
        ]

    # Este filtro extra sostiene la búsqueda rápida del atajo `/`.
    texto = parametros.get("q", parametros.get("buscar", [None]))[0]
    if texto:
        texto = texto.casefold()
        resultado = [
            item
            for item in resultado
            if texto
            in " ".join(
                [
                    str(item["id"]),
                    item["area"]["nombre"],
                    item["zona"]["nombre"],
                    item["fuente"]["nombre"],
                    *item["epp_faltante"],
                ]
            ).casefold()
        ]
    return resultado


def contadores(hallazgos: list[dict[str, Any]]) -> dict[str, int]:
    """Cuenta las pestañas de la bandeja."""

    return {
        "por_revisar": sum(item["estado"] == "por_revisar" for item in hallazgos),
        "confirmado": sum(item["estado"] == "confirmado" for item in hallazgos),
        "descartado": sum(item["estado"] in {"falso_positivo", "duplicado"} for item in hallazgos),
        "reincidente": sum(bool(item["reincidente"]) for item in hallazgos),
        "todos": len(hallazgos),
    }


def ordenar(hallazgos: list[dict[str, Any]], orden: str) -> list[dict[str, Any]]:
    """Ordena la bandeja según la opción elegida."""

    if orden == "ts_inicio_asc":
        return sorted(hallazgos, key=lambda item: item["ts_inicio"])
    if orden == "ts_inicio_desc":
        return sorted(hallazgos, key=lambda item: item["ts_inicio"], reverse=True)
    if orden == "severidad_desc":
        return sorted(
            hallazgos,
            key=lambda item: (item["severidad"], item["ts_inicio"]),
            reverse=True,
        )
    if orden == "duracion_desc":
        return sorted(hallazgos, key=lambda item: item["duracion_s"], reverse=True)
    if orden == "confianza_desc":
        return sorted(hallazgos, key=lambda item: item["confianza_media"], reverse=True)

    # Recomendado prioriza severidad, reincidencia y recencia.
    return sorted(
        hallazgos,
        key=lambda item: (item["severidad"], item["reincidente"], item["ts_inicio"]),
        reverse=True,
    )


def detalle(hallazgo: dict[str, Any]) -> dict[str, Any]:
    """Agrega la información que necesita el visor lateral."""

    respuesta = publico(hallazgo)
    inicio = datetime.fromisoformat(hallazgo["ts_inicio"])
    evidencia_base = int(hallazgo["_evidencia_id"])
    epp_principal = hallazgo["epp_faltante"][0]
    regla_id, regla_nombre, regla_version = REGLAS[epp_principal]
    evidencias = []

    # Cada URL devuelve un dibujo sintético sin personas reales.
    for indice in range(1, 4):
        evidencia_id = evidencia_base + indice
        evidencias.append(
            {
                "id": evidencia_id,
                "cuadro_idx": indice * 5,
                "capture_ts": (inicio + timedelta(seconds=indice)).isoformat(timespec="seconds"),
                "anonimizado": True,
                "url": f"/api/v1/evidencias/{evidencia_id}",
                "purgar_el": (inicio.date() + timedelta(days=30)).isoformat(),
            }
        )

    respuesta.update(
        {
            "recorte_video_url": None,
            "evidencias": evidencias,
            "linea_tiempo": {
                "primera_deteccion": hallazgo["ts_inicio"],
                "umbral_alcanzado": (inicio + timedelta(seconds=2)).isoformat(timespec="seconds"),
                "fin": hallazgo["ts_fin"],
            },
            "descripcion_automatica": {
                "titulo": f"Falta de {epp_principal} en {hallazgo['zona']['nombre']}",
                "descripcion": (
                    "La evidencia simulada muestra un incumplimiento continuo de EPP. "
                    "La decisión final corresponde a una persona autorizada."
                ),
                "confianza": round(max(0.0, hallazgo["confianza_media"] - 0.12), 2),
                "modelo": "qwen3-vl-4b-q4-demo",
            },
            "por_que_se_disparo": {
                "regla_id": regla_id,
                "regla_nombre": regla_nombre,
                "regla_version": regla_version,
                "zona": hallazgo["zona"]["nombre"],
                "epp_exigido": copy.deepcopy(hallazgo["epp_faltante"]),
                "umbral_configurado": "2,0 segundos de incumplimiento continuo",
                "valores_observados": (
                    f"{hallazgo['cuadros_confirmados']} cuadros confirmados "
                    f"en {hallazgo['duracion_s']:.1f} s"
                ),
                "confianza_minima": 0.45,
                "base_licitud": "obligacion_legal",
                "norma_fundante": "DS 594 art. 53",
            },
            "tecnicos": {
                "video_archivo": (
                    f"CAM-{hallazgo['fuente']['id']:02d}_{inicio.strftime('%Y-%m-%d_%H-%M')}.mp4"
                ),
                "video_hash": f"demo{hallazgo['id']:08x}…anonimizado",
                "segundo_en_video": float((hallazgo["id"] * 17) % 1800),
                "fps_muestreo": 5.0,
                "modelo_version": "rfdetr-b-epp-v3-demo",
                "track_id": hallazgo["id"] % 97,
            },
            "acciones": [],
        }
    )
    return respuesta


def validar_decision(datos: Any) -> dict[str, Any]:
    """Comprueba el cuerpo de una decisión de triage."""

    if not isinstance(datos, dict):
        raise ValueError("La decisión debe ser un objeto JSON")
    if datos.get("estado") not in ESTADOS - {"por_revisar"}:
        raise ValueError("La decisión debe usar un estado de triage válido")
    return datos


def aplicar_decision(hallazgo: dict[str, Any], decision: dict[str, Any]) -> None:
    """Actualiza un hallazgo y lo asigna al usuario actual."""

    hallazgo["estado"] = decision["estado"]
    if hallazgo["asignado_a"] is None:
        hallazgo["asignado_a"] = copy.deepcopy(RESPONSABLES[7])


class MockHandler(BaseHTTPRequestHandler):
    """Responde las peticiones del frontend."""

    server_version = "GuardianEPPMock/2.0"

    def log_message(self, message_format: str, *args: object) -> None:
        """Muestra cada petición en la terminal."""

        print("[mock] " + message_format % args)

    def cors(self) -> None:
        """Permite llamadas desde el servidor local de Vite."""

        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "600")

    def responder_json(self, datos: Any, estado: HTTPStatus = HTTPStatus.OK) -> None:
        """Envía una respuesta JSON con CORS."""

        cuerpo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.cors()
        self.end_headers()
        self.wfile.write(cuerpo)

    def responder_error(self, estado: HTTPStatus, codigo: str, mensaje: str) -> None:
        """Usa la forma de error indicada por OpenAPI."""

        self.responder_json(
            {"codigo": codigo, "mensaje": mensaje, "detalle": None},
            estado,
        )

    def autorizado(self) -> bool:
        """Comprueba el token local de demostración."""

        if self.headers.get("Authorization") == TOKEN_DEMO:
            return True
        cuerpo = json.dumps(
            {
                "codigo": "no_autenticado",
                "mensaje": "Usa la cabecera Authorization: Bearer demo",
                "detalle": None,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("WWW-Authenticate", "Bearer")
        self.send_header("Cache-Control", "no-store")
        self.cors()
        self.end_headers()
        self.wfile.write(cuerpo)
        return False

    def leer_json(self) -> Any:
        """Lee un cuerpo JSON pequeño."""

        try:
            largo = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Content-Length no es válido") from error
        if largo > 1_000_000:
            raise ValueError("El cuerpo JSON es demasiado grande")
        try:
            return json.loads(self.rfile.read(largo) or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("El cuerpo no contiene JSON válido") from error

    def responder_svg(self, evidencia_id: int) -> None:
        """Entrega una imagen sintética sin datos personales."""

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"
viewBox="0 0 640 360" role="img" aria-label="Evidencia simulada {evidencia_id}">
<rect width="640" height="360" fill="#14171A"/>
<rect x="72" y="54" width="496" height="252" rx="8" fill="#1A1E23" stroke="#3A3F46"/>
<path d="M320 105l52 90h-104z" fill="#E69F00"/>
<circle cx="320" cy="170" r="18" fill="#14171A"/>
<rect x="304" y="188" width="32" height="54" rx="8" fill="#14171A"/>
<text x="320" y="276" text-anchor="middle" fill="#E6E8EB" font-family="sans-serif"
font-size="18">Evidencia simulada · {evidencia_id}</text>
<text x="320" y="299" text-anchor="middle" fill="#A6ADB5" font-family="sans-serif"
font-size="12">Sin imagen real ni datos personales</text>
</svg>"""
        cuerpo = svg.encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.cors()
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_OPTIONS(self) -> None:
        """Responde la comprobación CORS del navegador."""

        # El preflight no lleva token. La petición real sí lo exige.
        self.send_response(HTTPStatus.NO_CONTENT)
        self.cors()
        self.end_headers()

    def do_GET(self) -> None:
        """Atiende las consultas de la bandeja y del visor."""

        peticion = urlparse(self.path)
        ruta = ruta_api(peticion.path)

        # Health es público para poder comprobar si el proceso está listo.
        if ruta == "/health":
            self.responder_json({"status": "ok", "service": "guardian-epp-mock"})
            return
        if not self.autorizado():
            return

        if ruta == "/hallazgos":
            self.listar_hallazgos(parse_qs(peticion.query))
            return

        coincidencia = re.fullmatch(r"/hallazgos/(\d+)", ruta)
        if coincidencia:
            hallazgo_id = int(coincidencia.group(1))
            with HALLAZGOS_LOCK:
                hallazgo = buscar(hallazgo_id)
                respuesta = detalle(hallazgo) if hallazgo else None
            if respuesta is None:
                self.responder_error(
                    HTTPStatus.NOT_FOUND,
                    "hallazgo_no_encontrado",
                    "No existe el hallazgo",
                )
                return
            self.responder_json(respuesta)
            return

        if ruta == "/catalogos":
            self.responder_json(
                {
                    "obras": copy.deepcopy(OBRAS),
                    "areas": copy.deepcopy(list(AREAS.values())),
                    "zonas": copy.deepcopy(list(ZONAS.values())),
                    "fuentes": copy.deepcopy(list(FUENTES.values())),
                    "turnos": copy.deepcopy(TURNOS),
                    "epp": sorted(EPP),
                }
            )
            return

        if ruta == "/estado":
            with HALLAZGOS_LOCK:
                pendientes = sum(item["estado"] == "por_revisar" for item in HALLAZGOS)
            self.responder_json(
                {
                    "ingesta": {"activa": True, "en_proceso": 1, "en_cola": 2},
                    "cobertura": {
                        "fuentes_activas": 3,
                        "fuentes_totales": 4,
                        "sin_cobertura": [
                            {
                                "fuente": copy.deepcopy(FUENTES[3]),
                                "motivo": "requiere_recalibracion",
                                "desde": "2026-09-03T06:40:00-03:00",
                            }
                        ],
                    },
                    "pendientes_por_revisar": pendientes,
                }
            )
            return

        if ruta == "/yo":
            self.responder_json(copy.deepcopy(SESION))
            return

        evidencia = re.fullmatch(r"/evidencias/(\d+)(?:/miniatura)?", ruta)
        if evidencia:
            self.responder_svg(int(evidencia.group(1)))
            return

        self.responder_error(HTTPStatus.NOT_FOUND, "ruta_no_encontrada", "La ruta no existe")

    def listar_hallazgos(self, parametros: dict[str, list[str]]) -> None:
        """Filtra, ordena y pagina los hallazgos."""

        try:
            limite = entero_url(parametros, "limite", 1) or 50
            if limite > 200:
                raise ValueError("'limite' no puede ser mayor que 200")
            cursor = entero_url(parametros, "cursor", 0) or 0
            orden = parametros.get("orden", ["recomendado"])[0]
            if orden not in ORDENES:
                raise ValueError("'orden' no es válido")
            with HALLAZGOS_LOCK:
                copia = copy.deepcopy(HALLAZGOS)
            para_contadores = filtrar(copia, parametros, incluir_estado=False)
            filtrados = filtrar(copia, parametros, incluir_estado=True)
        except ValueError as error:
            self.responder_error(HTTPStatus.BAD_REQUEST, "parametro_invalido", str(error))
            return

        ordenados = ordenar(filtrados, orden)
        pagina = ordenados[cursor : cursor + limite]
        siguiente = cursor + limite if cursor + limite < len(ordenados) else None
        self.responder_json(
            {
                "items": [publico(item) for item in pagina],
                "contadores": contadores(para_contadores),
                "siguiente_cursor": str(siguiente) if siguiente is not None else None,
            }
        )

    def do_POST(self) -> None:
        """Atiende el triage individual y en lote."""

        ruta = ruta_api(urlparse(self.path).path)
        if not self.autorizado():
            return
        if ruta == "/hallazgos/triage-lote":
            self.triar_lote()
            return

        coincidencia = re.fullmatch(r"/hallazgos/(\d+)/triage", ruta)
        if coincidencia:
            self.triar_uno(int(coincidencia.group(1)))
            return
        self.responder_error(HTTPStatus.NOT_FOUND, "ruta_no_encontrada", "La ruta no existe")

    def triar_uno(self, hallazgo_id: int) -> None:
        """Guarda una decisión sobre un hallazgo."""

        try:
            decision = validar_decision(self.leer_json())
        except ValueError as error:
            self.responder_error(HTTPStatus.BAD_REQUEST, "decision_invalida", str(error))
            return

        with HALLAZGOS_LOCK:
            hallazgo = buscar(hallazgo_id)
            if hallazgo:
                aplicar_decision(hallazgo, decision)
                respuesta = publico(hallazgo)
            else:
                respuesta = None
        if respuesta is None:
            self.responder_error(
                HTTPStatus.NOT_FOUND,
                "hallazgo_no_encontrado",
                "No existe el hallazgo",
            )
            return
        self.responder_json(respuesta)

    def triar_lote(self) -> None:
        """Aplica una decisión a varios hallazgos."""

        try:
            datos = self.leer_json()
            if not isinstance(datos, dict):
                raise ValueError("El cuerpo debe ser un objeto JSON")
            ids = datos.get("ids")
            if (
                not isinstance(ids, list)
                or not ids
                or len(ids) > 200
                or any(not isinstance(item, int) or isinstance(item, bool) for item in ids)
            ):
                raise ValueError("'ids' debe contener entre 1 y 200 números enteros")
            decision = validar_decision(datos.get("decision"))
        except ValueError as error:
            self.responder_error(HTTPStatus.BAD_REQUEST, "decision_invalida", str(error))
            return

        aplicados = 0
        omitidos = []
        with HALLAZGOS_LOCK:
            for hallazgo_id in ids:
                hallazgo = buscar(hallazgo_id)
                if hallazgo is None:
                    omitidos.append({"id": hallazgo_id, "motivo": "hallazgo no encontrado"})
                    continue
                aplicar_decision(hallazgo, decision)
                aplicados += 1
        self.responder_json({"aplicados": aplicados, "omitidos": omitidos})

    def do_PATCH(self) -> None:
        """Explica que el contrato usa POST para el triage."""

        if not self.autorizado():
            return
        self.responder_error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "metodo_no_permitido",
            "Usa POST /hallazgos/{id}/triage",
        )


def main() -> None:
    """Inicia el servidor hasta que se presiona Ctrl+C."""

    host = os.environ.get("MOCK_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("MOCK_PORT", "4010"))
    except ValueError as error:
        raise SystemExit("MOCK_PORT debe ser un número entero") from error

    print(f"Mock de Guardián EPP listo en http://{host}:{port}")
    print("Autorización: Bearer demo (GET /health no la necesita)")
    print("API: /api/v1/hallazgos o /hallazgos")
    try:
        ThreadingHTTPServer((host, port), MockHandler).serve_forever()
    except KeyboardInterrupt:
        print("\nMock detenido.")


if __name__ == "__main__":
    main()
