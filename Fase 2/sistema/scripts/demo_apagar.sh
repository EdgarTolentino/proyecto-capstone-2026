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
# Solo lo que levantó demo_todo.sh. Antes había un barrido con `pgrep -f "python3 -m gepp_api"` que
# también mataba la API que uno levanta a mano con `make demo-api` (y demo_todo.sh llama a este
# script al arrancar, en silencio): la API "se cerraba sola" a mitad del recorrido.
exit 0
