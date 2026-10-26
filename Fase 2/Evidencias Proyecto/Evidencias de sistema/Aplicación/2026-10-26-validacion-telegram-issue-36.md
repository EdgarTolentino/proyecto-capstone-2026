# Validación operativa de alertas por Telegram — issue #36

Validación manual del ciclo real de alertas de Guardián EPP con un teléfono. Se sigue
[`docs/operacion/alertas-telegram.md`](../../../../../docs/operacion/alertas-telegram.md) y la
instrucción registrada en la issue #36. El detector es simulado y no requiere GPU.

## Alcance

Esta evidencia debe comprobar:

1. Un aviso crítico llega al teléfono.
2. El acuse vuelve a la base de datos.
3. Un incumplimiento corriente no genera un aviso inmediato.
4. Una caída temporal del canal no pierde la notificación.
5. El aviso identifica área, turno, cantidad de personas y EPP, sin nombres ni imágenes.

La medición del presupuesto de seis avisos por turno queda fuera de esta ejecución: según la
asignación de la issue #36, Edgar la realiza en la máquina con GPU.

## Seguridad de la evidencia

- El token del bot y el `chat_id` viven solo en `Fase 2/sistema/.env`.
- El video de prueba no se incorpora al repositorio.
- La captura final debe ocultar el nombre del bot y cualquier dato personal antes de publicarse.
- Si una prueba falla, se registra el resultado antes de modificar código.

## Paso 1 — preparación del repositorio

| Comprobación | Resultado |
|---|---|
| Fecha | 2026-10-26 |
| Commit base | `886f820` |
| Rama de trabajo | `docs/issue-36-validacion-telegram` |
| Árbol antes de iniciar | Limpio |
| Entorno Python local | Disponible en `.venv` |
| Docker, uv y Git | Instalados |
| `Fase 2/sistema/.env` | No existía al comenzar |
| Servicios de Docker | Aún no levantados en este paso |

## Avance de las pruebas

| # | Prueba | Estado | Evidencia |
|---|---|---|---|
| 1 | El aviso llega | Pendiente | — |
| 2 | El acuse vuelve a la base | Pendiente | — |
| 3 | Lo corriente no avisa de inmediato | Pendiente | — |
| 4 | Una caída temporal no pierde el aviso | Pendiente | — |
| 5 | El aviso no identifica personas | Pendiente | — |
