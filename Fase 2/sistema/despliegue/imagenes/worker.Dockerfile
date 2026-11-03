# gepp-worker:proto — vigilante + trabajador (ADR-009) en una imagen. PROTOTIPO, opción B (GCP).
#
# Contexto de build: «Fase 2/sistema» (desde el repo: docker build -f <este archivo> .).
#   CPU (onnxruntime):   docker build --build-arg VARIANTE=cpu -t gepp-worker:proto -f despliegue/imagenes/worker.Dockerfile .
#   GPU (torch + CUDA):  docker build --build-arg VARIANTE=gpu -t gepp-worker:proto-gpu -f despliegue/imagenes/worker.Dockerfile .
#
# Por qué dos variantes. El motor `onnx` del trabajador fija CPUExecutionProvider en el código
# (gepp_vision/detectores/onnx.py) y __main__ no deja elegirlo: con onnxruntime-gpu NO se usaría
# la GPU. La GPU del repo es el motor `rfdetr` (.pth, PyTorch): extra `gpu` de gepp-vision, que
# arrastra torch y las bibliotecas CUDA como ruedas (el driver lo pone el host: --gpus all).
#
# Nunca en la imagen: pesos, video, datasets, credenciales. Todo se monta o llega por entorno.
FROM python:3.12-slim-bookworm AS base
ARG VARIANTE=cpu
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

# ffprobe: el trabajador lee los metadatos del contenedor con él (fuente_archivo.leer_metadatos).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app

# Solo lo que el trabajador necesita (no entra apps/web, datos/ ni scripts/).
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY perfiles ./perfiles

# --no-dev: sin pytest ni herramientas. --package: solo el trabajador y lo que arrastra.
RUN if [ "$VARIANTE" = "gpu" ]; then \
      uv sync --frozen --no-dev --package gepp-worker --package gepp-vision --extra gpu ; \
    else \
      uv sync --frozen --no-dev --package gepp-worker ; \
    fi

RUN useradd --system --uid 10001 --create-home gepp \
 && mkdir -p /datos/evidencia /datos/vigilada && chown -R gepp /datos
USER gepp
ENV GEPP_CARPETA_EVIDENCIA=/datos/evidencia GEPP_CARPETA_VIGILADA=/datos/vigilada

ENTRYPOINT ["python", "-m", "gepp_worker"]
