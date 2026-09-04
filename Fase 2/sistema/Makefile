# Seis verbos. Ni uno más: lo primero que mira alguien nuevo en el repositorio.
# Encapsula la ruta con espacio para que nadie tenga que escribirla.

.PHONY: ayuda setup lint fmt tipos test test-gpu cobertura contrato contrato-lint mock up down limpiar

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
	uv run mypy packages/gepp-core/src packages/gepp-api/src packages/gepp-vision/src packages/gepp-worker/src

test:  ## Ejecuta las pruebas (sin GPU)
	uv run pytest -m "not gpu and not slow"

test-gpu:  ## Ejecuta también las pruebas que necesitan GPU
	uv run pytest --run-gpu

cobertura:  ## Pruebas con informe de cobertura
	uv run pytest --cov --cov-report=term-missing --cov-report=html

contrato:  ## Exporta el OpenAPI y falla si cambió sin actualizar el contrato
	uv run python scripts/exportar_openapi.py
	git diff --exit-code contracts/openapi.json

contrato-lint:  ## Valida el contrato OpenAPI
	npx --yes @redocly/cli@latest lint contracts/openapi.yaml

mock:  ## Levanta el servidor simulado del contrato en el puerto 4010
	@echo "Recuerda la cabecera:  Authorization: Bearer demo"
	npx --yes @stoplight/prism-cli@latest mock contracts/openapi.yaml -p 4010

up:  ## Levanta PostgreSQL y Redis
	docker compose -f docker/compose.yml up -d

down:  ## Detiene los servicios
	docker compose -f docker/compose.yml down

limpiar:  ## Borra cachés
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
