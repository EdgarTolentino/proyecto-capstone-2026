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
quien() { ss -ltnp 2>/dev/null | grep ":$1 " | grep -oP 'users:\(\("\K[^"]+' | head -1; }
# Lanza un comando en su PROPIO grupo de procesos y guarda el id del grupo. Lo escribe el
# proceso ya dentro del grupo nuevo: `setsid` a veces hace fork y su PID no sirve para esto.
en_grupo() {
  local pidfile="$1" log="$2"; shift 2
  setsid bash -c 'echo $$ >"$0"; exec "$@"' "$pidfile" "$@" >"$log" 2>&1 < /dev/null &
}
esperar() { for _ in $(seq 60); do curl -s -o /dev/null "$1" && return 0; sleep 1; done; echo "no respondió $1" >&2; return 1; }

"$(dirname "$0")/demo_apagar.sh" >/dev/null 2>&1 || true

echo "1/4  PostgreSQL y Redis"
docker compose -f docker/compose.yml up -d --wait postgres redis >/dev/null

echo "2/4  Demo sobre $(basename "$VIDEO") (cámara $FUENTE)"
uv run python scripts/demo.py "$VIDEO" --fuente "$FUENTE" | sed -n '/== Hallazgos/,/== Evidencia/p' | head -4

echo "3/4  API en :8000"
puerto_libre 8000 || { echo "el puerto 8000 está ocupado: $(quien 8000)" >&2; exit 1; }
en_grupo "$DIR/api.pid" "$DIR/api.log" env GEPP_BD_URL="$BASE_DEMO" uv run python -m gepp_api
esperar http://localhost:8000/docs

echo "4/4  Web en :5173"
puerto_libre 5173 || { echo "el puerto 5173 está ocupado: $(quien 5173)" >&2; exit 1; }
[ -d apps/web/node_modules ] || (cd apps/web && npm ci --silent)
(cd apps/web && en_grupo "$DIR/web.pid" "$DIR/web.log" env VITE_API_URL=http://localhost:8000/api/v1 npx vite --port 5173 --strictPort)
esperar http://localhost:5173

if [ -n "${GEPP_TELEGRAM_TOKEN:-}" ]; then
  en_grupo "$DIR/despachador.pid" "$DIR/despachador.log" env GEPP_BD_URL="$BASE_DEMO" uv run python -m gepp_api.notificaciones
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
