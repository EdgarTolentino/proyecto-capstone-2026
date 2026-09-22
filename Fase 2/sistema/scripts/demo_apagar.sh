#!/usr/bin/env bash
# Apaga lo que levantó demo_todo.sh (API, web y despachador). La base y Redis quedan: `make down`.
DIR="${TMPDIR:-/tmp}/gepp-demo"
for nombre in api web despachador; do
  archivo="$DIR/$nombre.pid"
  [ -f "$archivo" ] || continue
  pid=$(cat "$archivo")
  # Mata al proceso y a sus hijos (uv y npx lanzan el proceso real como hijo).
  pkill -TERM -P "$pid" 2>/dev/null; kill "$pid" 2>/dev/null && echo "apagado: $nombre"
  rm -f "$archivo"
done
