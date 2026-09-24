#!/usr/bin/env bash
# Apaga lo que levantó demo_todo.sh (API, web y despachador). La base y Redis quedan: `make down`.
#
# Cada servidor corre en su propio grupo de procesos (setsid): se apaga el GRUPO entero, así no
# sobreviven los nietos (npx -> sh -> node vite; uv -> python).
DIR="${TMPDIR:-/tmp}/gepp-demo"
for nombre in api web despachador; do
  archivo="$DIR/$nombre.pid"
  [ -f "$archivo" ] || continue
  pid=$(cat "$archivo")
  if kill -TERM -- "-$pid" 2>/dev/null; then
    echo "apagado: $nombre"
  else
    echo "no estaba corriendo: $nombre"
  fi
  rm -f "$archivo"
done
sleep 1  # que terminen de cerrarse antes de buscar restos
# Restos de corridas anteriores a este script (sin grupo propio): solo los de ESTE proyecto.
for patron in "node_modules/\\.bin/vite --port 5173" "\\.venv/bin/python3 -m gepp_api"; do
  pids=$(pgrep -f "$patron" || true)
  [ -n "$pids" ] && kill $pids 2>/dev/null && echo "apagado resto: $patron"
done
exit 0
