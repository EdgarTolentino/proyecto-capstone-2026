#!/bin/sh
# De DEMO_IDENTIDADES="correo=token,otro=token2" saca lo que necesitan nginx y la API, con los mismos
# valores en los dos lados. Falla (exit 1) ante cualquier elemento mal formado: el contenedor no arranca.
#   identidades.sh nginx  → configuración: mapa correo→token y credencial del `lector` de MediaMTX
#   identidades.sh api    → "token=correo,..." (formato de GEPP_API_TOKENS)
# Sin DEMO_IDENTIDADES la lista queda vacía y la puerta de la tailnet responde 403 a todo.
# Los caracteres permitidos excluyen comillas, `$`, `;` y espacios: nada de lo que entre puede
# cambiar la sintaxis de nginx. Los mensajes de error no repiten el token.
set -eu
modo=${1:?uso: identidades.sh nginx|api}
fallo() { echo "[identidades] $1" >&2; exit 1; }
case $modo in nginx | api) ;; *) fallo "modo desconocido: $modo" ;; esac

# `grep` valida por línea: un salto de línea o un control en el valor dejaría pasar una línea buena y colar
# el resto en la configuración. Se valida la variable ENTERA: se borra lo permitido y, si sobra algo, falla.
solo_permitidos() {  # $1 nombre, $2 valor, $3 lo permitido (para tr)
  [ "$(printf '%s' "$2" | LC_ALL=C tr -d "$3" | wc -c)" -eq 0 ] || fallo "$1 con caracteres no permitidos"
}
solo_permitidos DEMO_IDENTIDADES "${DEMO_IDENTIDADES:-}" 'A-Za-z0-9@._%+~=,-'
solo_permitidos ESPEJO_CLAVE "${ESPEJO_CLAVE:-}" 'A-Za-z0-9._~-'

bundle=$(printf '%s' "${DEMO_TOKEN:-}" | LC_ALL=C tr -cd 'A-Za-z0-9._~-')
vistos_c=,
vistos_t=,
lineas=
pares_api=
n=0
set -f
IFS=,
for par in ${DEMO_IDENTIDADES:-}; do
  [ -n "$par" ] || continue
  n=$((n + 1))
  case $par in *=*) ;; *) fallo "elemento $n de DEMO_IDENTIDADES sin «=»" ;; esac
  correo=${par%%=*}
  token=${par#*=}
  printf '%s' "$correo" | grep -Eq '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+$' || fallo "elemento $n: correo inválido"
  printf '%s' "$token" | grep -Eq '^[A-Za-z0-9._~-]+$' || fallo "elemento $n: token vacío o con caracteres no permitidos"
  minus=$(printf '%s' "$correo" | tr 'A-Z' 'a-z')
  case $vistos_c in *",$minus,"*) fallo "elemento $n: correo repetido" ;; esac
  case $vistos_t in *",$token,"*) fallo "elemento $n: token repetido" ;; esac
  # Una persona con el token del bundle (DEMO_TOKEN, está en el JS) pisaría al prevencionista en GEPP_API_TOKENS.
  # Se compara con DEMO_TOKEN reducido a caracteres de token: la API hace `.strip()` (config.py).
  [ "$token" != "$bundle" ] || fallo "elemento $n: el token es el del bundle (DEMO_TOKEN)"
  vistos_c=$vistos_c$minus,
  vistos_t=$vistos_t$token,
  lineas="$lineas    \"$minus\" \"$token\";
"
  # La API busca el correo EXACTO en la tabla `usuario` (en minúsculas): nginx y la API usan la misma forma.
  pares_api=${pares_api:+$pares_api,}$token=$minus
done
unset IFS
set +f

if [ "$modo" = api ]; then
  printf '%s\n' "$pares_api"
  exit 0
fi

# Credencial con la que nginx entra a MediaMTX como `lector`: el navegador no la ve.
basica=
if [ -n "${ESPEJO_CLAVE:-}" ]; then
  basica="Basic $(printf 'lector:%s' "$ESPEJO_CLAVE" | base64 | tr -d '\n')"
fi
# La comparación del mapa no distingue mayúsculas (se verifica en tests); por eso el correo va en minúsculas.
printf 'map $http_tailscale_user_login $token_persona {\n    default "";\n%s}\n' "$lineas"
printf 'map $server_port $espejo_credencial {\n    default "%s";\n}\n' "$basica"
