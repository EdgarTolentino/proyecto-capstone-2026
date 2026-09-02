# Modelo de datos

> PostgreSQL. Migraciones versionadas con Alembic. **El video nunca entra a la base**: solo ruta,
> hash y metadatos. Este documento es la evidencia "modelo de datos" que exige la Fase 2.

## Diagrama

```
   faena
     │
     ├──< area >───────< zona >──────────┐   (polígono sobre el cuadro de referencia)
     │       │                           │
     │       ├──< regla >────┐           │
     │       │   (versionada)│           │
     │       └──< dotacion > │           │   (dato administrativo: sin biometría)
     │                       │           │
     └──< fuente >──< video >┼───────────┘
                        │    │
                        ├──< deteccion >          (cruda, por track — permite recalcular)
                        │
                        └──< hallazgo >──┬──< evidencia >        (recorte anonimizado)
                                         ├──< accion_correctiva >
                                         └──< notificacion >     (patrón outbox)

   usuario ──< rol >                 auditoria   (append-only, sin UPDATE ni DELETE)
```

## Tablas

### `faena` · `area` · `zona`

```sql
CREATE TABLE faena (
    id           BIGSERIAL PRIMARY KEY,
    nombre       TEXT NOT NULL,
    zona_horaria TEXT NOT NULL DEFAULT 'America/Santiago',
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE area (
    id        BIGSERIAL PRIMARY KEY,
    faena_id  BIGINT NOT NULL REFERENCES faena(id),
    nombre    TEXT NOT NULL,
    criticidad SMALLINT NOT NULL DEFAULT 1 CHECK (criticidad BETWEEN 1 AND 4),
    UNIQUE (faena_id, nombre)
);

-- Polígono dibujado sobre un cuadro de referencia de la cámara.
-- tipo = 'interes'   -> solo se evalúan reglas dentro de este polígono
-- tipo = 'privacidad'-> se ennegrece ANTES de inferir (baños, casino, tránsito público)
CREATE TABLE zona (
    id             BIGSERIAL PRIMARY KEY,
    area_id        BIGINT NOT NULL REFERENCES area(id),
    fuente_id      BIGINT NOT NULL REFERENCES fuente(id),
    nombre         TEXT NOT NULL,
    tipo           TEXT NOT NULL CHECK (tipo IN ('interes','privacidad')),
    poligono       JSONB NOT NULL,             -- [[x,y],...] normalizado 0..1
    solape_minimo  REAL NOT NULL DEFAULT 0.50, -- fracción de la caja dentro de la zona
    color          TEXT
);
```

> `solape_minimo = 0.50` es el valor de partida usado en arquitecturas de referencia del rubro.
> Se calibra en la S11 con el simulador de reglas.

### `fuente` · `video`

Una sola tabla de fuentes sirve para la carpeta vigilada (v1) y para RTSP (v2). **Solo cambia
`tipo`.** Ese es el pilar 2 de la arquitectura hecho esquema.

```sql
CREATE TABLE fuente (
    id            BIGSERIAL PRIMARY KEY,
    area_id       BIGINT NOT NULL REFERENCES area(id),
    nombre        TEXT NOT NULL,
    tipo          TEXT NOT NULL CHECK (tipo IN ('carpeta','rtsp')),
    uri           TEXT NOT NULL,              -- /datos/videos/camara_01  |  rtsp://...
    fps_objetivo  REAL NOT NULL DEFAULT 5.0,
    activa        BOOLEAN NOT NULL DEFAULT true,
    cuadro_referencia TEXT                    -- ruta a la imagen para dibujar zonas
);

CREATE TABLE video (
    id             BIGSERIAL PRIMARY KEY,
    fuente_id      BIGINT NOT NULL REFERENCES fuente(id),
    ruta           TEXT NOT NULL,
    hash_sha256    CHAR(64) NOT NULL UNIQUE,  -- clave de idempotencia: reprocesar no duplica
    bytes          BIGINT NOT NULL,
    duracion_s     REAL,
    fps_declarado  REAL,
    ancho          INT,
    alto           INT,
    -- El reloj del sistema. Se deriva de los metadatos del contenedor o, en su defecto,
    -- de (mtime - duracion). NUNCA de la hora de procesamiento.
    capture_ts_inicio TIMESTAMPTZ NOT NULL,
    origen_capture_ts TEXT NOT NULL CHECK (origen_capture_ts IN ('metadatos','mtime','manual','ocr')),
    estado         TEXT NOT NULL DEFAULT 'en_cola'
                   CHECK (estado IN ('en_cola','procesando','listo','error')),
    error_motivo   TEXT,
    cuadros_analizados INT,
    proceso_ms     BIGINT,
    creado_en      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON video (estado, creado_en);
```

### `deteccion` — la tabla cruda

La decisión de guardarla es lo que permite recalcular reglas sin volver a usar la GPU.

```sql
CREATE TABLE deteccion (
    id           BIGSERIAL PRIMARY KEY,
    video_id     BIGINT NOT NULL REFERENCES video(id) ON DELETE CASCADE,
    cuadro_idx   INT NOT NULL,
    capture_ts   TIMESTAMPTZ NOT NULL,
    track_id     INT NOT NULL,      -- EFÍMERO: único dentro del video, jamás entre videos
    clase        TEXT NOT NULL,     -- persona | casco | chaleco | lentes | guantes | arnes
    confianza    REAL NOT NULL,
    bbox         REAL[4] NOT NULL,  -- x1,y1,x2,y2 normalizado 0..1
    zona_id      BIGINT REFERENCES zona(id),
    modelo_version TEXT NOT NULL
);
CREATE INDEX ON deteccion (video_id, track_id, cuadro_idx);
```

> **`track_id` es efímero por diseño.** No se cruza entre videos, cámaras ni días. Es lo que
> mantiene al sistema fuera del régimen de datos sensibles: sin persistencia de identidad no hay
> tratamiento biométrico.

### `regla` — versionada, con gobernanza

```sql
CREATE TABLE regla (
    id                     BIGSERIAL PRIMARY KEY,
    area_id                BIGINT NOT NULL REFERENCES area(id),
    zona_id                BIGINT REFERENCES zona(id),
    nombre                 TEXT NOT NULL,
    version                INT NOT NULL DEFAULT 1,
    epp_exigido            TEXT[] NOT NULL,          -- {'casco','chaleco'}
    -- TODOS los umbrales en SEGUNDOS. Los cuadros se derivan en ejecución.
    confirmacion_segundos  REAL NOT NULL DEFAULT 2.0,
    cierre_segundos        REAL NOT NULL DEFAULT 3.0,
    confianza_minima       REAL NOT NULL DEFAULT 0.45,
    severidad              SMALLINT NOT NULL CHECK (severidad BETWEEN 1 AND 4),
    turno                  TEXT,                      -- NULL = todos
    hora_desde             TIME,
    hora_hasta             TIME,
    activa                 BOOLEAN NOT NULL DEFAULT true,
    -- Gobernanza: la trazabilidad jurídica se audita con un SELECT, no con un PDF
    base_licitud           TEXT NOT NULL
                           CHECK (base_licitud IN ('obligacion_legal','interes_legitimo','contrato')),
    norma_fundante         TEXT,                      -- 'DS 132 art. 32'
    finalidad_declarada    TEXT NOT NULL,
    retencion_dias         INT NOT NULL DEFAULT 30,
    creada_por             BIGINT REFERENCES usuario(id),
    creada_en              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (area_id, nombre, version)
);
```

Cambiar una regla **crea una versión nueva**; la anterior se marca inactiva. El hallazgo guarda
`regla_id` **y** `regla_version`: sin eso, en la S16 nadie puede explicar por qué un hallazgo de
la S8 se disparó con un umbral que ya no existe.

### `hallazgo` — la unidad del sistema

```sql
CREATE TABLE hallazgo (
    id                 BIGSERIAL PRIMARY KEY,
    video_id           BIGINT REFERENCES video(id) ON DELETE SET NULL,
    fuente_id          BIGINT NOT NULL REFERENCES fuente(id),
    area_id            BIGINT NOT NULL REFERENCES area(id),
    zona_id            BIGINT REFERENCES zona(id),
    regla_id           BIGINT NOT NULL REFERENCES regla(id),
    regla_version      INT NOT NULL,
    track_id           INT NOT NULL,
    epp_faltante       TEXT[] NOT NULL,
    severidad          SMALLINT NOT NULL CHECK (severidad BETWEEN 1 AND 4),
    -- Reloj de captura, no de procesamiento
    ts_inicio          TIMESTAMPTZ NOT NULL,
    ts_fin             TIMESTAMPTZ,               -- NULL mientras el evento está vivo (v2)
    duracion_s         REAL GENERATED ALWAYS AS (EXTRACT(EPOCH FROM (ts_fin - ts_inicio))) STORED,
    cuadros_confirmados INT NOT NULL,
    confianza_media    REAL NOT NULL,
    -- Triage. severidad y confianza son ejes INDEPENDIENTES: no se mezclan.
    estado             TEXT NOT NULL DEFAULT 'por_revisar'
                       CHECK (estado IN ('por_revisar','confirmado','falso_positivo','duplicado','pospuesto')),
    revisado_por       BIGINT REFERENCES usuario(id),
    revisado_en        TIMESTAMPTZ,
    -- Etapa 2: el VLM describe, no decide
    vlm_titulo         TEXT,
    vlm_descripcion    TEXT,
    vlm_confianza      REAL,
    vlm_modelo         TEXT,
    creado_en          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON hallazgo (estado, severidad, ts_inicio DESC);
CREATE INDEX ON hallazgo (area_id, ts_inicio DESC);
```

### `evidencia` · `accion_correctiva` · `notificacion`

```sql
CREATE TABLE evidencia (
    id           BIGSERIAL PRIMARY KEY,
    hallazgo_id  BIGINT NOT NULL REFERENCES hallazgo(id) ON DELETE CASCADE,
    ruta         TEXT NOT NULL,
    hash_sha256  CHAR(64) NOT NULL,
    cuadro_idx   INT NOT NULL,
    capture_ts   TIMESTAMPTZ NOT NULL,
    -- El recorte se escribe YA anonimizado. No existe versión con rostro visible en disco.
    anonimizado  BOOLEAN NOT NULL DEFAULT true,
    purgar_el    DATE NOT NULL              -- fecha calculada según regla.retencion_dias
);
CREATE INDEX ON evidencia (purgar_el);

CREATE TABLE accion_correctiva (
    id            BIGSERIAL PRIMARY KEY,
    hallazgo_id   BIGINT NOT NULL REFERENCES hallazgo(id),
    responsable_id BIGINT NOT NULL REFERENCES usuario(id),
    descripcion   TEXT NOT NULL,
    plazo         DATE NOT NULL,
    estado        TEXT NOT NULL DEFAULT 'abierta'
                  CHECK (estado IN ('abierta','en_curso','cerrada','vencida')),
    cerrada_en    TIMESTAMPTZ,
    comentario_cierre TEXT
);

-- Patrón outbox: la notificación se escribe en la misma transacción que el hallazgo
-- y un despachador aparte la envía con reintentos. Si el canal cae, nada se pierde.
CREATE TABLE notificacion (
    id            BIGSERIAL PRIMARY KEY,
    hallazgo_id   BIGINT REFERENCES hallazgo(id),
    tipo          TEXT NOT NULL CHECK (tipo IN ('inmediata','resumen_turno','escalamiento')),
    canal         TEXT NOT NULL CHECK (canal IN ('correo','telegram','whatsapp','webhook')),
    destinatario  TEXT NOT NULL,
    cuerpo        JSONB NOT NULL,
    estado        TEXT NOT NULL DEFAULT 'pendiente'
                  CHECK (estado IN ('pendiente','enviada','fallida','acusada')),
    intentos      INT NOT NULL DEFAULT 0,
    enviada_en    TIMESTAMPTZ,
    acusada_en    TIMESTAMPTZ,               -- cierra el ciclo: alguien la recibió
    acusada_por   BIGINT REFERENCES usuario(id),
    creada_en     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON notificacion (estado, creada_en);
```

### `dotacion` — la respuesta a "desagregar por género" sin biometría

```sql
-- Dato ADMINISTRATIVO aportado por el cliente. No se infiere nada desde la imagen.
-- El reporte cruza hallazgos agregados por (area, turno, fecha) contra esta tabla.
CREATE TABLE dotacion (
    id         BIGSERIAL PRIMARY KEY,
    area_id    BIGINT NOT NULL REFERENCES area(id),
    fecha      DATE NOT NULL,
    turno      TEXT NOT NULL,
    n_hombres  INT NOT NULL,
    n_mujeres  INT NOT NULL,
    n_otro     INT NOT NULL DEFAULT 0,
    UNIQUE (area_id, fecha, turno)
);
```

> **Regla de presentación, obligatoria en la interfaz:** ninguna celda del reporte con
> **n < 5** se renderiza; muestra "datos insuficientes". Con una dotación femenina en torno al
> 15 %, una celda pequeña reidentifica a la trabajadora.

### `usuario` · `auditoria`

```sql
CREATE TABLE usuario (
    id        BIGSERIAL PRIMARY KEY,
    email     TEXT NOT NULL UNIQUE,
    nombre    TEXT NOT NULL,
    rol       TEXT NOT NULL CHECK (rol IN ('administrador','prevencionista','supervisor','auditor')),
    area_id   BIGINT REFERENCES area(id),   -- el supervisor solo ve su área
    activo    BOOLEAN NOT NULL DEFAULT true
);

-- Append-only: sin esto, en una controversia el sistema no puede acreditar nada.
CREATE TABLE auditoria (
    id          BIGSERIAL PRIMARY KEY,
    usuario_id  BIGINT REFERENCES usuario(id),
    rol         TEXT NOT NULL,
    accion      TEXT NOT NULL,
    entidad     TEXT NOT NULL,
    entidad_id  BIGINT,
    motivo      TEXT,
    ip          INET,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE RULE auditoria_no_update AS ON UPDATE TO auditoria DO INSTEAD NOTHING;
CREATE RULE auditoria_no_delete AS ON DELETE TO auditoria DO INSTEAD NOTHING;
```

## Roles y qué ve cada uno

| Rol | Hallazgos | Evidencia | Reglas | Auditoría |
|---|---|---|---|---|
| **Administrador** | Todos | ❌ sin acceso | Crear y editar | Leer |
| **Prevencionista** | Todos | Anonimizada | Leer | — |
| **Supervisor de área** | Solo su área | Anonimizada | Leer | — |
| **Auditor** | Todos, solo lectura | Anonimizada | Leer | Leer |

Que el administrador **no** vea la evidencia no es un descuido: es lo que separa "quien configura"
de "quien observa", y es la traducción a esquema de la exigencia de que el control sea general e
impersonal. Ningún rol tiene descarga masiva de recortes.

## Retención en tres anillos

| Anillo | Qué | Plazo | Ancla |
|---|---|---|---|
| 1 | Recortes de evidencia | 30 días (configurable por regla) | Recomendación del Consejo para la Transparencia (Oficio 2309/2017) |
| 2 | Hallazgos, detecciones y metadatos | 12 meses | Ciclo anual de gestión preventiva |
| 3 | Agregados estadísticos anonimizados | Indefinido | Ya no son datos personales |

El purgado es una tarea programada con su propio registro, no una buena intención.
