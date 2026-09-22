"""`python -m gepp_api`: levanta la API en el puerto 8000 (GEPP_API_PUERTO para cambiarlo)."""

from __future__ import annotations

import os

import uvicorn

from gepp_api.app import crear_app


def main() -> None:
    uvicorn.run(
        crear_app(),
        host=os.environ.get("GEPP_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("GEPP_API_PUERTO", "8000")),
    )


if __name__ == "__main__":
    main()
