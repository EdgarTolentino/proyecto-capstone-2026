#!/usr/bin/env bash
# Levanta TODO para mostrar el sistema: base y cola, demo sobre un video, API y web.
#
#   make demo-todo VIDEO=ruta.mp4 [FUENTE=2]     ·     make demo-apagar
#
# La API y la web quedan corriendo en segundo plano; sus registros y PID van a
# $TMPDIR/gepp-demo. Si el .env tiene el bot de Telegram, también arranca el despachador.
set -euo pipefail

VIDEO="${1:?uso: demo_todo.sh VIDEO [FUENTE]}"
FUENTE="${2:-2}"
DIR="${TMPDIR:-/tmp}/gepp-demo"
BASE_DEMO="${GEPP_BD_URL:-postgresql+psycopg://gepp:gepp_dev@localhost:5432/gepp}_demo"
mkdir -p "$DIR"

puerto_libre() { ! (ss -ltn 2>/dev/null | grep -q ":$1 "); }
esperar() { for _ in $(seq 60); do curl -s -o /dev/null "$1" && return 0; sleep 1; done; echo "no respondió $1" >&2; return 1; }

"$(dirname "$0")/demo_apagar.sh" >/dev/null 2>&1 || true

echo "1/4  PostgreSQL y Redis"
docker compose -f docker/compose.yml up -d --wait postgres redis >/dev/null

echo "2/4  Demo sobre $(basename "$VIDEO") (cámara $FUENTE)"
uv run python scripts/demo.py "$VIDEO" --fuente "$FUENTE" | sed -n '/== Hallazgos/,/== Evidencia/p' | head -4

echo "3/4  API en :8000"
puerto_libre 8000 || { echo "el puerto 8000 está ocupado" >&2; exit 1; }
GEPP_BD_URL="$BASE_DEMO" nohup uv run python -m gepp_api >"$DIR/api.log" 2>&1 &
echo $! >"$DIR/api.pid"
esperar http://localhost:8000/docs

echo "4/4  Web en :5173"
puerto_libre 5173 || { echo "el puerto 5173 está ocupado" >&2; exit 1; }
[ -d apps/web/node_modules ] || (cd apps/web && npm ci --silent)
# `exec`: la subshell SE CONVIERTE en vite, con la salida ya redirigida. Sin eso la subshell
# queda viva sosteniendo la terminal y el PID guardado no es el del servidor.
(cd apps/web && VITE_API_URL=http://localhost:8000/api/v1 exec nohup npx vite --port 5173 --strictPort >"$DIR/web.log" 2>&1) &
echo $! >"$DIR/web.pid"
esperar http://localhost:5173

if [ -n "${GEPP_TELEGRAM_TOKEN:-}" ]; then
  GEPP_BD_URL="$BASE_DEMO" nohup uv run python -m gepp_api.notificaciones >"$DIR/despachador.log" 2>&1 &
  echo $! >"$DIR/despachador.pid"
  echo "     + despachador de Telegram (registro: $DIR/despachador.log)"
fi

cat <<FIN

Listo:
  Web        http://localhost:5173
  API        http://localhost:8000/docs
  Métricas   http://localhost:8000/metrics
Para apagar: make demo-apagar
FIN
command -v cmd.exe >/dev/null && cmd.exe /c start http://localhost:5173 2>/dev/null || true
