# Seis verbos. Ni uno más: lo primero que mira alguien nuevo en el repositorio.
# Encapsula la ruta con espacio para que nadie tenga que escribirla.

# El .env (nunca versionado) se carga si existe: así el token de Telegram no se escribe en la
# terminal ni queda en el historial.
ifneq (,$(wildcard .env))
include .env
export
endif

# La base de docker/compose.yml. Si exportas GEPP_BD_URL (o la pones en .env y la cargas), manda esa.
export GEPP_BD_URL ?= postgresql+psycopg://gepp:gepp_dev@localhost:5432/gepp

.PHONY: ayuda setup lint fmt tipos test test-gpu cobertura contrato contrato-lint mock up down migrar semilla demo demo-todo demo-apagar demo-api api despachador telegram-chat-id limpiar

ayuda:  ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Instala el entorno (máquinas SIN GPU y CI)
	uv sync --all-packages

setup-gpu:  ## Instala el entorno en la máquina CON GPU
	uv sync --all-packages --extra cu126

lint:  ## Revisa estilo y errores
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## Corrige estilo y formatea
	uv run ruff check --fix .
	uv run ruff format .

tipos:  ## Verifica tipos
	uv run mypy packages/gepp-core/src packages/gepp-bd/src packages/gepp-api/src packages/gepp-vision/src packages/gepp-worker/src

test:  ## Ejecuta las pruebas (sin GPU)
	uv run pytest -m "not gpu and not slow"

test-gpu:  ## Ejecuta también las pruebas que necesitan GPU
	uv run pytest --run-gpu

cobertura:  ## Pruebas con informe de cobertura
	uv run pytest --cov --cov-report=term-missing --cov-report=html

contrato:  ## Falla si la API sirve operaciones distintas de contracts/openapi.yaml
	uv run python scripts/exportar_openapi.py

contrato-lint:  ## Valida el contrato OpenAPI
	npx --yes @redocly/cli@latest lint contracts/openapi.yaml

mock:  ## Levanta el servidor simulado del contrato en el puerto 4010
	@echo "Recuerda la cabecera:  Authorization: Bearer demo"
	npx --yes @stoplight/prism-cli@latest mock contracts/openapi.yaml -p 4010

up:  ## Levanta PostgreSQL y Redis
	docker compose -f docker/compose.yml up -d

down:  ## Detiene los servicios
	docker compose -f docker/compose.yml down

migrar:  ## Aplica las migraciones a la base de GEPP_BD_URL (ver .env.example)
	uv run python -m gepp_bd.migrar subir

semilla:  ## Carga el perfil de construcción (ADR-011); PERFIL=perfiles/otro.yaml para cambiarlo
	uv run python -m gepp_bd.semilla $(or $(PERFIL),perfiles/construccion.yaml)

demo:  ## Demo de punta a punta con detector simulado: make demo VIDEO=ruta.mp4 [GUION=...] [FUENTE=2]
	@test -n "$(VIDEO)" || { echo "uso: make demo VIDEO=ruta/al/video.mp4 [GUION=demo/guion_cam03.json]"; exit 2; }
	uv run python scripts/demo.py "$(VIDEO)" $(if $(GUION),--guion "$(GUION)") $(if $(FUENTE),--fuente $(FUENTE))

demo-todo:  ## TODO de una vez (base, demo, API, web): make demo-todo VIDEO=ruta.mp4 [FUENTE=1]
	@test -n "$(VIDEO)" || { echo "uso: make demo-todo VIDEO=ruta/al/video.mp4 [FUENTE=1]"; exit 2; }
	./scripts/demo_todo.sh "$(VIDEO)" $(or $(FUENTE),2)

demo-apagar:  ## Apaga la API, la web y el despachador de demo-todo
	./scripts/demo_apagar.sh

demo-api:  ## API sobre la base de la última `make demo`, para verla en la web
	GEPP_BD_URL=$(GEPP_BD_URL)_demo uv run python -m gepp_api

api:  ## Levanta la API real en :8000. La web: VITE_API_URL=http://localhost:8000/api/v1 npm run dev
	uv run python -m gepp_api

despachador:  ## Envía los avisos del outbox por Telegram (GEPP_TELEGRAM_TOKEN en .env)
	uv run python -m gepp_api.notificaciones

telegram-chat-id:  ## Muestra el chat_id de quien le escribió al bot (GEPP_AVISO_DESTINATARIO)
	uv run python scripts/telegram_chat_id.py

limpiar:  ## Borra cachés
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
