# syntax=docker/dockerfile:1
# Imágenes de la API y de la web (demo local, despliegue/local/).
#
# Se construye desde "Fase 2/sistema" (la ruta tiene un espacio: entre comillas):
#   docker build -f despliegue/imagenes/api.Dockerfile --target api -t gepp-api:proto .
#   docker build -f despliegue/imagenes/api.Dockerfile --target web -t gepp-web:proto \
#       --build-arg VITE_API_TOKEN="$TOKEN_DE_LA_WEB" .
#
# Dos blancos, una sola fuente:
#   api  (el último = el que sale sin --target)  FastAPI + gepp-bd. SIN visión, trabajador, torch
#        ni pesos (ADR-007, ADR-010). No depende de nada local: lo reutiliza la opción B.
#   web  nginx con la web construida. Sirve /, y reenvía /api/ a la API: mismo origen, sin CORS
#        (la API solo admite http://localhost:5173 y esa lista no se configura por entorno).

ARG PYTHON=3.12-slim
ARG NODE=22-alpine
ARG NGINX=1.27-alpine

# ───────────── web: compilar ─────────────
FROM node:${NODE} AS web-build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
# La URL es relativa: el navegador pide /api/v1 al mismo host que le entregó la web.
# VITE_API_TOKEN queda DENTRO del JavaScript público: es la autenticación de demostración
# (gepp_api.config), no un secreto. Por eso el token de la demo es de un solo uso (despliegue/local/README.md).
ARG VITE_API_TOKEN=demo
ENV VITE_API_URL=/api/v1 VITE_API_TOKEN=${VITE_API_TOKEN}
RUN npm run build

# ───────────── web: nginx ─────────────
FROM nginx:${NGINX} AS web
COPY despliegue/local/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=web-build /web/dist /usr/share/nginx/html
# La imagen oficial rellena la plantilla con envsubst al arrancar.
ENV API_UPSTREAM=api:8000
EXPOSE 8080

# ───────────── API ─────────────
FROM python:${PYTHON} AS api
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /app
# Solo el pyproject de cada paquete y el lock: la capa de dependencias no se rehace por tocar código.
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
# --package gepp-api arrastra gepp-bd y gepp-core, nada más (lo comprueba el README).
RUN uv sync --frozen --no-dev --package gepp-api --no-editable
COPY perfiles/ perfiles/
RUN useradd --system --uid 10001 gepp
USER gepp
ENV GEPP_API_HOST=0.0.0.0 GEPP_API_PUERTO=8000
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/docs', timeout=2)"
CMD ["python", "-m", "gepp_api"]
