# Alertas por Telegram — puesta en marcha

> PT-13 (#36). Diez minutos la primera vez. El token del bot es un **secreto**: vive en
> `Fase 2/sistema/.env`, que git ignora, y nunca se pega en un chat, un issue ni un PR.

## 1. Crear el bot (una vez)

1. En Telegram, abrir **@BotFather** y enviar `/newbot`.
2. Nombre visible: por ejemplo `Guardián EPP (demo)`. Usuario: uno libre que termine en `bot`.
3. BotFather responde con el **token** (`123456789:AA…`). Copiarlo al `.env`:

```bash
cd "Fase 2/sistema"
cp -n .env.example .env        # si todavía no existe
# editar .env y completar:
GEPP_TELEGRAM_TOKEN=123456789:AA...
```

## 2. Averiguar a quién le llegan los avisos

Desde el teléfono, abrir el bot recién creado y enviarle cualquier mensaje (por ejemplo `hola`).
Luego:

```bash
make telegram-chat-id
# GEPP_AVISO_DESTINATARIO=987654321   (private)
```

Copiar esa línea al `.env`. Para un grupo del equipo: agregar el bot al grupo, escribir en el
grupo y repetir; el `chat_id` del grupo es negativo.

## 3. Probar el ciclo completo

```bash
make up
make demo VIDEO=~/videos/generativa.mp4 FUENTE=2   # cámara 2: regla crítica, avisa ya
GEPP_BD_URL=postgresql+psycopg://gepp:gepp_dev@localhost:5432/gepp_demo make despachador
```

En segundos llega al teléfono:

> **Frente de obra gruesa · turno A**
> 1 persona sin casco ni chaleco entre 15:38 y 15:38.
> Indicio automatizado. Requiere validación humana.
> [ ✅ Acuso recibo ]

Al tocar **Acuso recibo** el botón desaparece, la terminal del despachador muestra
`acusados=1` y en la base la notificación pasa a `acusada` con su `acusada_en`:

```bash
docker exec guardian-epp-postgres-1 psql -U gepp -d gepp_demo \
  -c "select estado, enviada_en, acusada_en from notificacion"
```

Con `FUENTE=1` (regla de severidad alta, 3,4 s) **no llega nada al teléfono**: es un incumplimiento
corriente y baja al resumen del turno. Eso es ADR-008 funcionando, no un error.

## Qué hace el despachador, en una tabla

| Situación | Qué pasa |
|---|---|
| Hallazgo crítico, o más de 120 s | Aviso inmediato |
| Hallazgo corriente | Al resumen, que sale al empezar el turno siguiente |
| Varias personas en la misma área y EPP | **Un** mensaje: "3 personas sin casco" |
| Ya hubo un aviso hace menos de 10 min | Espera y se agrupa con lo que llegue |
| La misma cámara avisó hace menos de 30 min | Al resumen |
| Ya salieron 6 avisos en el turno | Al resumen, y queda registrado en `auditoria` |
| Telegram caído o limitando | Reintenta con espera; a los 5 intentos queda `fallida` |
| Token inválido, bot bloqueado, chat inexistente | `fallida` de inmediato, con el motivo |

`/metrics` expone `gepp_avisos_inmediatos_turno` contra `gepp_presupuesto_avisos_turno` (6) y
`gepp_alertas_accionables_ratio`: hallazgos avisados que terminaron en acción correctiva.

## Privacidad

Los avisos van **al área y al turno, nunca a una persona**: dicen cuántas personas y qué EPP,
no quiénes. No llevan imagen. El `chat_id` y el token no entran al repositorio.
