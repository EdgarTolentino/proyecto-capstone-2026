#!/usr/bin/env bash
# Arma la demo local desde cero y la deja lista: construye, levanta y la deja como recién armada.
#
#   export DEMO_PG_PASSWORD=... DEMO_TOKEN=...      # obligatorias (ver compose.yml)
#   export GEPP_TELEGRAM_TOKEN=... GEPP_AVISO_DESTINATARIO=...   # opcionales
#   ./armar-demo.sh
#
# Se corre DESPUÉS de encuadrar la cámara, para que un trozo del encuadre no gaste la alerta. Para
# repetir la demo no se vuelve a armar: `rearmar-demo.sh`.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${DEMO_PG_PASSWORD:?define DEMO_PG_PASSWORD}"
: "${DEMO_TOKEN:?define DEMO_TOKEN}"
[[ -n "${GEPP_TELEGRAM_TOKEN:-}" ]] || echo "[armar] sin GEPP_TELEGRAM_TOKEN: el despachador queda en espera y no llegará ninguna alerta" >&2

# Archivos de compose, separados por «:» (las rutas pueden llevar espacios). Por defecto solo el
# local; con el celular como cámara: DEMO_COMPOSE_ARCHIVOS=<local>/compose.yml:<celular>/compose.yml
# (el orden importa: las rutas relativas salen de la carpeta del primero).
TRABAJADORES=(trabajador trabajador-cpu)
IFS=: read -r -a ARCHIVOS <<< "${DEMO_COMPOSE_ARCHIVOS:-$AQUI/compose.yml}"
BANDERAS=()
for a in "${ARCHIVOS[@]}"; do BANDERAS+=(-f "$a"); done
PROYECTO="${DEMO_PROYECTO:-gepp-demo}"
CAMARA_SERVICIOS=(${CAMARA_SERVICIOS:-mediamtx captura})
COMPOSE=(docker compose -p "$PROYECTO" "${BANDERAS[@]}")
# Se construye y levanta todo menos la cámara (se enciende después de encuadrar, ver rearmar-demo.sh).
if ! texto="$("${COMPOSE[@]}" config --services)"; then
  echo "no pude leer la lista de servicios del compose; no se tocó nada" >&2
  exit 6
fi
mapfile -t DEFINIDOS <<< "$texto"
# Un solo trabajador (misma regla que rearmar): DEMO_TRABAJADOR, o el CPU si el perfil `cpu` está activo.
if [[ -n "${DEMO_TRABAJADOR:-}" ]]; then
  [[ " ${TRABAJADORES[*]} " == *" $DEMO_TRABAJADOR "* ]] || {
    echo "DEMO_TRABAJADOR debe ser uno de: ${TRABAJADORES[*]}" >&2
    exit 2
  }
  elegido="$DEMO_TRABAJADOR"
elif [[ ",${COMPOSE_PROFILES:-}," == *",cpu,"* ]]; then
  elegido="trabajador-cpu"
else
  elegido="trabajador"
fi
ARRANCAR=()
for s in "${DEFINIDOS[@]}"; do
  [[ -n "$s" ]] || continue
  [[ " ${CAMARA_SERVICIOS[*]} " == *" $s "* ]] && continue
  [[ " ${TRABAJADORES[*]} " == *" $s "* ]] && continue
  ARRANCAR+=("$s")
done
ARRANCAR+=("$elegido")
[[ ${#ARRANCAR[@]} -gt 1 ]] || { echo "ningún servicio que levantar (config --services vacío)" >&2; exit 6; }
export DEMO_TRABAJADOR="$elegido"  # rearmar-demo.sh levanta el mismo
"${COMPOSE[@]}" up -d --build "${ARRANCAR[@]}"
# El arranque pudo procesar algo (un video en la vigilada, un trozo): se deja en cero igual.
exec "$AQUI/rearmar-demo.sh" --yes
