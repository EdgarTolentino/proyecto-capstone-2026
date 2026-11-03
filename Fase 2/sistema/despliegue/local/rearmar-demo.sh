#!/usr/bin/env bash
# Deja la demo local como recién armada, para repetirla sin gastar la alerta del ensayo.
#
#   ./rearmar-demo.sh [--yes] [--forzar] [--simular]
#
# Por qué existe: «reiniciar la base» no basta. Redis recuerda los videos terminados y no los
# vuelve a encolar, y la alerta inmediata se gasta por cámara (30 min) y por turno (6) según lo que
# hay en la tabla `notificacion`. Hay que vaciar todo, en este orden:
#
#   1. detener la captura y el hook de la cámara (perfil `camara`), para que no entre un trozo
#   2. detener trabajador, despachador, API y web (nadie escribe mientras se borra)
#   3. vaciar la carpeta vigilada (incluye `en-curso`) y la evidencia
#   4. recrear la base de PostgreSQL, migrar y sembrar
#   5. vaciar el Redis DEL COMPOSE (nunca uno del anfitrión)
#   6. comprobar que el outbox quedó en cero (la alerta queda sin gastar) y volver a levantar
#
# Solo toca el proyecto `gepp-demo`: sus contenedores y sus volúmenes `gepp-demo_vigilada` y
# `gepp-demo_evidencia`. `DEMO_PROYECTO` lo cambia (para probar el script aparte de la demo).
#
# Códigos de salida: 2 uso o entorno · 3 hay un video procesando (o no se pudo saber) · 4 el outbox
# no quedó en cero · 5 no levantaron todos los servicios · 6 no se pudo LEER el estado (antes de
# borrar nada: no se tocó nada) · 7 falló un paso DESPUÉS de borrar (el mensaje dice cómo terminar).
#
# Trabajador: se vuelve a levantar el que estaba corriendo (nunca los dos, ni el GPU en lugar del
# CPU). `DEMO_TRABAJADOR=trabajador|trabajador-cpu` lo fija; si ninguno corría, `trabajador-cpu` con
# `COMPOSE_PROFILES=cpu` y `trabajador` en otro caso.
#
# Se niega si hay un video procesando (o si no puede saberlo). `--forzar` lo salta; `--yes` salta
# la pregunta; `--simular` solo imprime lo que haría, sin ejecutar docker.
# Lo que se borra se lee antes de correr: usa `--simular` la primera vez.

set -euo pipefail

PROYECTO="${DEMO_PROYECTO:-gepp-demo}"   # otro nombre solo para probar el script aparte de la demo
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGEN_UTIL="${DEMO_IMAGEN_UTIL:-gepp-api:demo}"
# Los servicios de la cámara (override del celular): se detienen y NO se vuelven a levantar solos.
CAMARA_SERVICIOS=(${CAMARA_SERVICIOS:-mediamtx captura})
APAGAR_SERVICIOS=(trabajador trabajador-cpu despachador api web borrador)
TRABAJADORES=(trabajador trabajador-cpu)

SI=0 FORZAR=0 SIMULAR=0
for a in "$@"; do
  case "$a" in
    --yes) SI=1 ;;
    --forzar) FORZAR=1 ;;
    --simular) SIMULAR=1 ;;
    *) echo "opción desconocida: $a" >&2; exit 2 ;;
  esac
done

if [[ $SIMULAR -eq 0 ]]; then
  : "${DEMO_PG_PASSWORD:?define DEMO_PG_PASSWORD (el mismo con que se armó la demo)}"
  : "${DEMO_TOKEN:?define DEMO_TOKEN}"
fi
export DEMO_PG_PASSWORD="${DEMO_PG_PASSWORD:-simulacion}" DEMO_TOKEN="${DEMO_TOKEN:-simulacion}"

# `--profile '*'` solo para detener y listar: así se ve también lo que está fuera del perfil activo.
# Archivos de compose, separados por «:» (las rutas pueden llevar espacios). Por defecto solo el
# local; con el celular como cámara: DEMO_COMPOSE_ARCHIVOS=<local>/compose.yml:<celular>/compose.yml
# (el orden importa: las rutas relativas salen de la carpeta del primero).
IFS=: read -r -a ARCHIVOS <<< "${DEMO_COMPOSE_ARCHIVOS:-$AQUI/compose.yml}"
BANDERAS=()
for a in "${ARCHIVOS[@]}"; do BANDERAS+=(-f "$a"); done
COMPOSE=(docker compose -p "$PROYECTO" "${BANDERAS[@]}")
TODOS=(docker compose -p "$PROYECTO" "${BANDERAS[@]}" --profile '*')
es_camara() { [[ " ${CAMARA_SERVICIOS[*]} " == *" $1 "* ]]; }

paso() { echo "[rearmar] $*"; }
ejecutar() {
  if [[ $SIMULAR -eq 1 ]]; then echo "  + $*"; else "$@"; fi
}

# ── Guardas ───────────────────────────────────────────────────────────────────────────────
if [[ $SIMULAR -eq 0 ]]; then
  [[ -n "$("${COMPOSE[@]}" ps -q postgres)" ]] || {
    echo "no hay una demo armada en el proyecto $PROYECTO: usa armar-demo.sh" >&2
    exit 2
  }
  if [[ $FORZAR -eq 0 ]]; then
    # Si la cuenta no es un número no se sabe si hay algo procesando: se niega (falla cerrado).
    # Exige que el comando termine bien Y que diga un número: un «0» con error no vale.
    if en_proceso="$("${COMPOSE[@]}" exec -T postgres psql -U gepp -d gepp -Atc \
      "select count(*) from video where estado in ('en_cola','procesando','reintentando')")"; then
      estado_guarda=0
    else
      estado_guarda=1
    fi
    if [[ $estado_guarda -ne 0 ]] || ! [[ "$en_proceso" =~ ^[0-9]+$ ]]; then
      echo "no pude saber si hay un video procesando (respuesta: '${en_proceso}'); --forzar para seguir" >&2
      exit 3
    fi
    if [[ "$en_proceso" -gt 0 ]]; then
      echo "hay $en_proceso video(s) en cola o procesando; espera a que terminen o usa --forzar" >&2
      exit 3
    fi
  fi
  if [[ $SI -eq 0 ]]; then
    echo "Esto BORRA la base, la evidencia, la carpeta vigilada y el Redis del proyecto $PROYECTO."
    read -r -p "Escribe «rearmar» para seguir: " respuesta || respuesta=""
    [[ "$respuesta" == "rearmar" ]] || { echo "cancelado" >&2; exit 1; }
  fi
fi

# ── 0. Leer qué corre y qué se levantará: TODO antes de borrar nada ───────────────────────
no_pude_leer() {
  echo "no pude leer $1; no se tocó nada (salida 6)" >&2
  exit 6
}
if [[ $SIMULAR -eq 1 ]]; then
  corriendo=("${CAMARA_SERVICIOS[@]}")
  ARRANCAR=("<todos los servicios menos ${CAMARA_SERVICIOS[*]} y el trabajador que no corría>")
else
  texto="$("${TODOS[@]}" ps --status running --services)" || no_pude_leer "lo que está corriendo"
  mapfile -t corriendo <<< "$texto"
  texto="$("${COMPOSE[@]}" config --services)" || no_pude_leer "la lista de servicios del compose"
  mapfile -t DEFINIDOS <<< "$texto"

  # El trabajador que estaba corriendo (nunca los dos, ni el GPU en lugar del CPU).
  previos=()
  for t in "${TRABAJADORES[@]}"; do
    [[ " ${corriendo[*]} " == *" $t "* ]] && previos+=("$t")
  done
  if [[ -n "${DEMO_TRABAJADOR:-}" ]]; then
    [[ " ${TRABAJADORES[*]} " == *" $DEMO_TRABAJADOR "* ]] || {
      echo "DEMO_TRABAJADOR debe ser uno de: ${TRABAJADORES[*]}" >&2
      exit 2
    }
    elegido="$DEMO_TRABAJADOR"
  elif [[ ${#previos[@]} -gt 1 ]]; then
    echo "corren los dos trabajadores a la vez (${previos[*]}); elige uno con DEMO_TRABAJADOR" >&2
    exit 2
  elif [[ ${#previos[@]} -eq 1 ]]; then
    elegido="${previos[0]}"
  elif [[ ",${COMPOSE_PROFILES:-}," == *",cpu,"* ]]; then
    elegido="trabajador-cpu"
  else
    elegido="trabajador"
  fi

  ARRANCAR=()
  for s in "${DEFINIDOS[@]}"; do
    [[ -n "$s" ]] || continue
    es_camara "$s" && continue
    [[ " ${TRABAJADORES[*]} " == *" $s "* ]] && continue  # el trabajador se agrega abajo
    ARRANCAR+=("$s")
  done
  ARRANCAR+=("$elegido")
  [[ ${#ARRANCAR[@]} -gt 1 ]] || no_pude_leer "ningún servicio que levantar (config --services vacío)"
fi

# Lo que sigue BORRA: si algo falla desde aquí, la demo queda a medias y hay que decir cómo seguir.
fallo_tras_borrar() {
  echo "falló «$1» DESPUÉS de borrar: la demo quedó DETENIDA y a medias (salida 7)." >&2
  echo "Para terminarla, repite:  $0 --forzar --yes   (--forzar: la guarda de videos no puede leer una base sin tablas)" >&2
  echo "o a mano, en este orden:" >&2
  printf '  ' >&2; printf '%q ' "${COMPOSE[@]}" run --rm --no-deps preparar >&2; echo >&2
  printf '  ' >&2; printf '%q ' "${COMPOSE[@]}" exec -T redis redis-cli flushall >&2; echo >&2
  printf '  ' >&2; printf '%q ' "${COMPOSE[@]}" up -d "${ARRANCAR[@]}" >&2; echo >&2
  exit 7
}

# ── 1. Captura y hook ─────────────────────────────────────────────────────────────────────
paso "1/6 detener la captura y el hook de la cámara (si están)"
for s in "${CAMARA_SERVICIOS[@]}"; do
  if [[ " ${corriendo[*]} " == *" $s "* ]]; then ejecutar "${TODOS[@]}" stop "$s"; fi
done

# ── 2. Quien escribe ──────────────────────────────────────────────────────────────────────
paso "2/6 detener trabajador, despachador, API y web"
for s in "${APAGAR_SERVICIOS[@]}"; do
  if [[ $SIMULAR -eq 1 || " ${corriendo[*]} " == *" $s "* ]]; then ejecutar "${TODOS[@]}" stop "$s"; fi
done

# ── 3. Carpeta vigilada (con `en-curso`) y evidencia ──────────────────────────────────────
paso "3/6 vaciar la carpeta vigilada y la evidencia (solo el contenido de los volúmenes)"
ejecutar docker run --rm --user root --entrypoint sh \
  -v "${PROYECTO}_vigilada:/v" -v "${PROYECTO}_evidencia:/e" "$IMAGEN_UTIL" \
  -c 'find /v /e -mindepth 1 -delete' || fallo_tras_borrar "vaciar la vigilada y la evidencia"

# ── 4. PostgreSQL ─────────────────────────────────────────────────────────────────────────
paso "4/6 recrear la base, migrar y sembrar"
ejecutar "${COMPOSE[@]}" exec -T postgres psql -U gepp -d postgres -v ON_ERROR_STOP=1 \
  -c 'DROP DATABASE IF EXISTS gepp WITH (FORCE)' -c 'CREATE DATABASE gepp' ||
  fallo_tras_borrar "recrear la base"
ejecutar "${COMPOSE[@]}" run --rm --no-deps preparar || fallo_tras_borrar "migrar y sembrar (preparar)"

# ── 5. Redis del compose ──────────────────────────────────────────────────────────────────
paso "5/6 vaciar el Redis del compose"
ejecutar "${COMPOSE[@]}" exec -T redis redis-cli flushall || fallo_tras_borrar "vaciar Redis"

# ── 6. Alerta sin gastar y de vuelta ──────────────────────────────────────────────────────
paso "6/6 comprobar el outbox y volver a levantar"
if [[ $SIMULAR -eq 0 ]]; then
  avisos="$("${COMPOSE[@]}" exec -T postgres psql -U gepp -d gepp -Atc \
    'select count(*) from notificacion')" || fallo_tras_borrar "contar el outbox"
  [[ "$avisos" == "0" ]] || { echo "el outbox quedó con '$avisos' filas: la alerta no está sin gastar" >&2; exit 4; }
  paso "outbox en 0: la alerta está sin gastar"
fi
# Sin `--wait`: con el compose real `up -d --wait` sale con 0 (los servicios dependen de los de
# una sola vez con `service_completed_successfully`), pero con un `preparar` suelto sale con 1. Esperar
# a mano es válido en los dos casos: todo lo que no sea `preparar` ni `permisos` debe quedar `running`.
# Se levanta TODO menos la cámara: un trozo del encuadre gastaría la alerta recién rearmada. El
# `borrador` (privacidad del celular) sí queda arriba si el override lo define.
ejecutar "${COMPOSE[@]}" up -d "${ARRANCAR[@]}" || fallo_tras_borrar "levantar los servicios"
if [[ $SIMULAR -eq 0 ]]; then
  excluir="^(preparar|permisos|$(IFS='|'; echo "${CAMARA_SERVICIOS[*]}")) "
  for _ in $(seq 60); do
    texto="$("${COMPOSE[@]}" ps -a --format '{{.Service}} {{.State}}')" ||
      fallo_tras_borrar "listar el estado de los servicios"
    [[ -n "$texto" ]] || fallo_tras_borrar "listar el estado (salió vacío)"
    mal="$(grep -Ev "$excluir" <<< "$texto" | grep -v ' running$' || true)"
    [[ -z "$mal" ]] && break
    sleep 1
  done
  [[ -z "$mal" ]] || { echo "no levantaron: $mal" >&2; exit 5; }
fi
paso "listo. La cámara queda APAGADA: enciéndela cuando la cámara esté encuadrada y Edgar listo:"
printf '  '; printf '%q ' "${COMPOSE[@]}" up -d "${CAMARA_SERVICIOS[0]}"; echo
echo "  (plan B con video: VIDEO=<ruta> y, en lugar de lo anterior, los mismos -f con --profile plan-b up -d captura)"
