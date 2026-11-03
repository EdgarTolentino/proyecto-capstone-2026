# Espejo de la cámara (WHEP), el MISMO en las dos puertas. Lo incluye cada `server` de
# nginx.conf.template y espera que el `server` defina $authz_api: el Authorization que usaría /api/
# (el del bundle en la puerta local, el de la persona en la de la tailnet).
#
# ¿La persona tiene `ver_evidencia`? Se le pregunta a la API con ese Authorization: `GET /videos/0/vivo`
# revisa el permiso ANTES de cualquier 404 (routers/videos.py), así que con permiso responde 404 (vista
# apagada o video 0 inexistente) → se convierte en 204; sin permiso 403 y sin token 401, que niegan el
# espejo. Cualquier otra respuesta (API caída: 502) también niega.
# Se acepta: un 404 que NO venga de esa ruta (una API vieja o un upstream equivocado) también autorizaría;
# nginx y la API salen del mismo compose, así que no debería ocurrir. Tampoco se revisa el área del
# supervisor: solo `ver_evidencia` (ver 02-privacidad-y-cumplimiento.md).
location = /_ver_evidencia {
    internal;
    proxy_pass http://api_up/api/v1/videos/0/vivo;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Authorization $authz_api;
    proxy_set_header Tailscale-User-Login "";
    proxy_intercept_errors on;
    error_page 404 = @permitido;
}

location @permitido {
    return 204;
}

# MediaMTX se resuelve en cada petición: sin el override del celular nginx arranca igual y esto
# responde 503. La clave del `lector` la pone nginx; el navegador no la ve.
location /espejo/ {
    # Solo el MISMO origen: MediaMTX trae CORS abierto (webrtcAllowOrigins), y sin esto una página ajena
    # que abra Miguel podría pedir el video con su identidad. Sin preflight (OPTIONS → 403) y sin
    # Access-Control-* en las respuestas, el navegador no le entrega la respuesta a otro origen.
    if ($request_method = OPTIONS) {
        return 403;
    }
    proxy_hide_header Access-Control-Allow-Origin;
    proxy_hide_header Access-Control-Allow-Methods;
    proxy_hide_header Access-Control-Allow-Headers;
    proxy_hide_header Access-Control-Allow-Credentials;
    proxy_hide_header Access-Control-Expose-Headers;
    proxy_hide_header Access-Control-Max-Age;
    auth_request /_ver_evidencia;
    resolver 127.0.0.11 valid=5s ipv6=off;
    set $mediamtx http://mediamtx:8889;
    rewrite ^/espejo/(.*)$ /$1 break;
    proxy_pass $mediamtx;
    proxy_http_version 1.1;
    proxy_set_header Authorization $espejo_credencial;
    proxy_set_header Tailscale-User-Login "";
    # El Location de MediaMTX (/camara/whep/<id>) pasa a /espejo/camara/whep/<id>, RELATIVO: con
    # proxy_redirect nginx lo vuelve absoluto con su esquema y puerto internos (http, 8081), que
    # detrás de `tailscale serve` (https, 8443) no existen. Así el DELETE de cierre llega a /espejo/.
    proxy_redirect off;
    proxy_hide_header Location;
    add_header Location $espejo_location always;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_max_temp_file_size 0;
    proxy_connect_timeout 3s;
    proxy_read_timeout 15s;
    add_header Cache-Control "no-store" always;
    error_page 502 503 504 = @camara_apagada;
}

location @camara_apagada {
    charset utf-8;
    default_type text/plain;
    add_header Cache-Control "no-store" always;
    return 503 "cámara apagada\n";
}
