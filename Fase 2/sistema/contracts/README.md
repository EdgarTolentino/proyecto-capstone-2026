# El contrato

`openapi.yaml` es **la frontera entre el backend y el frontend**, y está congelado.

Mientras esté congelado, `apps/web` se construye contra el servidor simulado: sin detector, sin
GPU, sin base de datos y sin esperar a nadie. Ese es el motivo entero del
[ADR-003](../../../docs/arquitectura/adr/003-fastapi-y-react.md) — con plantillas dentro del
backend, quien hace frontend no puede avanzar hasta que exista el modelo.

## Levantar el servidor simulado

```bash
make mock          # queda escuchando en http://127.0.0.1:4010
```

Responde con datos de ejemplo realistas, ya con nombres de obra. **Hay que mandar la cabecera de
autorización**: sin ella el contrato exige sesión y el simulado responde 401, igual que hará el
backend real.

```bash
curl -H "Authorization: Bearer demo" http://127.0.0.1:4010/hallazgos
```

Desde el frontend, en desarrollo:

```js
const api = "http://127.0.0.1:4010"
const cabeceras = { Authorization: "Bearer demo" }
```

Cuando el backend esté listo, **cambia esa constante y nada más**.

## Validar antes de tocar nada

```bash
make contrato-lint
```

## Qué se puede cambiar y qué no

| Cambio | Rompe al frontend | Cómo se hace |
|---|---|---|
| Añadir un campo opcional | No | Se hace y se avisa |
| Añadir una ruta | No | Se hace y se avisa |
| Renombrar o quitar un campo | **Sí** | Se discute antes, en un PR aparte |
| Cambiar un tipo o hacer obligatorio un campo | **Sí** | Se discute antes |
| Cambiar un `enum` | **Sí** | Se discute antes |

"Congelado" no quiere decir intocable: quiere decir que **lo que rompe al otro se acuerda antes**.

## Reglas del dominio que el contrato hace cumplir por forma

No son comentarios: están en el esquema, así que un backend que las incumpla no valida.

- **No se identifica a nadie.** No existe ningún campo con nombre, RUT, foto ni identificador
  persistente de trabajador. El `track_id` es efímero: único dentro de un video y sin significado
  fuera de él ([ADR-006](../../../docs/arquitectura/adr/006-sin-identificacion.md)).
- **Severidad y confianza son campos separados.** Nunca se combinan en un indicador.
- **Los umbrales van en segundos**, jamás en cuadros
  ([ADR-005](../../../docs/arquitectura/adr/005-fuente-y-reloj.md)).
- **Todo instante es hora de captura**, derivada de la fuente — nunca hora de procesamiento.
- **La evidencia se sirve ya anonimizada:** `anonimizado` es `const: true`.
- **Los reportes suprimen las celdas con n < 5** y devuelven `datos_insuficientes`. La supresión
  es del servidor: el frontend no puede saltársela.
- **El administrador no accede a evidencia.** El frontend se pinta contra `permisos`, no contra
  el rol.
- **Cada hallazgo lleva `aviso_legal`**: "Indicio automatizado. Requiere validación humana."

## Cuando exista el backend

FastAPI genera su propio OpenAPI desde el código. A partir de ese momento `make contrato`
compara el generado contra este archivo y **falla si se desviaron**: el contrato deja de ser una
promesa y pasa a ser una prueba.

## Estado

Congelado el 2026-09-04, versión 0.1.0. Cubre las seis pantallas del diseño: bandeja de triage,
visor de evidencia, cola de ingesta, panel, editor de reglas con simulador, y reportes.
