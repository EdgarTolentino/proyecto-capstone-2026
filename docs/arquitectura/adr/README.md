# Registro de Decisiones de Arquitectura (ADR)

Una decisión técnica de fondo no se discute en el chat del grupo: se escribe aquí y se aprueba en
un Pull Request. El formato es corto a propósito — un ADR que nadie lee no sirve de nada.

| # | Decisión | Estado |
|---|---|---|
| [001](001-dos-etapas.md) | Arquitectura de dos etapas: el detector decide, el VLM describe | Aceptada |
| [002](002-detector-y-licencias.md) | RF-DETR en lugar de Ultralytics YOLO | Aceptada |
| [003](003-fastapi-y-react.md) | FastAPI + React en lugar de Django + HTMX | Aceptada |
| [004](004-el-evento-es-la-unidad.md) | El evento es la unidad; se persisten las detecciones crudas | Aceptada |
| [005](005-fuente-y-reloj.md) | Puerto `FrameSource` y reloj de captura | Aceptada |
| [006](006-sin-identificacion.md) | El sistema no identifica personas ni infiere atributos | Aceptada |
| [007](007-monorepo-uv.md) | Monorepo con espacio de trabajo `uv` y cuatro paquetes | Aceptada |
| [008](008-alertas-dos-velocidades.md) | Alertas a dos velocidades | Aceptada |
