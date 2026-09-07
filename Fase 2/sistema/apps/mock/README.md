# Mock de la API

Este servidor permite desarrollar la bandeja y el visor sin esperar al backend real. Usa solo
Python, guarda los cambios en memoria y recupera los datos originales cuando se reinicia.

## Cómo iniciarlo

Desde `Fase 2/sistema`:

```powershell
make mock
```

El comando ejecuta `uv run python apps/mock/server.py` dentro del entorno del proyecto.

Escucha en `http://127.0.0.1:4010`. Para una prueba en otro puerto:

```powershell
$env:MOCK_PORT = "4011"
uv run python apps/mock/server.py
```

`GET /health` es público. Todas las demás rutas requieren esta cabecera:

```text
Authorization: Bearer demo
```

La API acepta las dos formas de ruta. Por ejemplo, `/hallazgos` y `/api/v1/hallazgos` entregan
la misma respuesta. Esto permite usar el contrato directamente o un proxy de Vite.

## Rutas disponibles

| Método | Ruta | Uso |
| --- | --- | --- |
| GET | `/health` | Comprueba que el proceso está listo |
| GET | `/hallazgos` | Lista, filtra, ordena y pagina 16 hallazgos |
| GET | `/hallazgos/{id}` | Entrega el detalle completo para el visor |
| POST | `/hallazgos/{id}/triage` | Confirma, descarta, duplica o pospone uno |
| POST | `/hallazgos/triage-lote` | Aplica una decisión a varios hallazgos |
| GET | `/catalogos` | Entrega obras, áreas, zonas, cámaras, turnos y EPP |
| GET | `/estado` | Entrega ingesta, cobertura y pendientes |
| GET | `/yo` | Entrega la sesión y sus permisos |
| GET | `/evidencias/{id}` | Entrega una imagen sintética sin datos personales |

Todas estas rutas, salvo `health`, también funcionan con el prefijo `/api/v1`.

## Filtros de la bandeja

La lista admite `estado`, `severidad`, `area_id`, `zona_id`, `fuente_id`, `obra_id`, `epp`,
`desde`, `hasta`, `turno`, `reincidente`, `orden`, `limite` y `cursor`. `severidad` y `epp`
aceptan varios valores separados por coma. También existe `q` para la búsqueda de texto.

Ejemplo:

```powershell
$headers = @{ Authorization = "Bearer demo" }
Invoke-RestMethod `
  -Headers $headers `
  -Uri "http://127.0.0.1:4010/api/v1/hallazgos?estado=por_revisar&severidad=4,3"
```

Los contadores respetan los filtros activos, pero ignoran `estado`, como indica OpenAPI.

## Ejemplos de triage

Decisión individual:

```powershell
$headers = @{ Authorization = "Bearer demo" }
$body = '{"estado":"confirmado"}'
Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Uri "http://127.0.0.1:4010/api/v1/hallazgos/2418/triage" -Body $body
```

Decisión en lote:

```powershell
$headers = @{ Authorization = "Bearer demo" }
$body = '{"ids":[2417,2416],"decision":{"estado":"falso_positivo","motivo":"Prueba local"}}'
Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Uri "http://127.0.0.1:4010/api/v1/hallazgos/triage-lote" -Body $body
```

Las evidencias son dibujos de prueba. No contienen fotografías, rostros ni información de una
persona trabajadora.
