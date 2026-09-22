-- Guardián EPP — esquema de la base de datos (PostgreSQL 17).
-- GENERADO por scripts/exportar_esquema.py desde las migraciones de gepp-bd.
-- No se edita a mano: se cambia la migración y se vuelve a exportar.

BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE faena (
    id BIGSERIAL NOT NULL, 
    nombre TEXT NOT NULL, 
    zona_horaria TEXT DEFAULT 'America/Santiago' NOT NULL, 
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_faena PRIMARY KEY (id)
);

CREATE TABLE area (
    id BIGSERIAL NOT NULL, 
    faena_id BIGINT NOT NULL, 
    nombre TEXT NOT NULL, 
    criticidad SMALLINT DEFAULT '1' NOT NULL, 
    CONSTRAINT pk_area PRIMARY KEY (id), 
    CONSTRAINT ck_area_criticidad CHECK (criticidad BETWEEN 1 AND 4), 
    CONSTRAINT fk_area_faena_id_faena FOREIGN KEY(faena_id) REFERENCES faena (id), 
    CONSTRAINT uq_area_faena_id_nombre UNIQUE (faena_id, nombre)
);

CREATE TABLE dotacion (
    id BIGSERIAL NOT NULL, 
    area_id BIGINT NOT NULL, 
    fecha DATE NOT NULL, 
    turno TEXT NOT NULL, 
    n_hombres INTEGER NOT NULL, 
    n_mujeres INTEGER NOT NULL, 
    n_otro INTEGER DEFAULT '0' NOT NULL, 
    CONSTRAINT pk_dotacion PRIMARY KEY (id), 
    CONSTRAINT fk_dotacion_area_id_area FOREIGN KEY(area_id) REFERENCES area (id), 
    CONSTRAINT uq_dotacion_area_id_fecha_turno UNIQUE (area_id, fecha, turno)
);

CREATE TABLE fuente (
    id BIGSERIAL NOT NULL, 
    area_id BIGINT NOT NULL, 
    nombre TEXT NOT NULL, 
    tipo TEXT NOT NULL, 
    uri TEXT NOT NULL, 
    fps_objetivo REAL DEFAULT '5.0' NOT NULL, 
    activa BOOLEAN DEFAULT 'true' NOT NULL, 
    cuadro_referencia TEXT, 
    CONSTRAINT pk_fuente PRIMARY KEY (id), 
    CONSTRAINT ck_fuente_tipo CHECK (tipo IN ('carpeta','rtsp')), 
    CONSTRAINT fk_fuente_area_id_area FOREIGN KEY(area_id) REFERENCES area (id)
);

CREATE TABLE usuario (
    id BIGSERIAL NOT NULL, 
    email TEXT NOT NULL, 
    nombre TEXT NOT NULL, 
    rol TEXT NOT NULL, 
    area_id BIGINT, 
    activo BOOLEAN DEFAULT 'true' NOT NULL, 
    CONSTRAINT pk_usuario PRIMARY KEY (id), 
    CONSTRAINT ck_usuario_rol CHECK (rol IN ('administrador','prevencionista','supervisor','auditor')), 
    CONSTRAINT fk_usuario_area_id_area FOREIGN KEY(area_id) REFERENCES area (id), 
    CONSTRAINT uq_usuario_email UNIQUE (email)
);

CREATE TABLE auditoria (
    id BIGSERIAL NOT NULL, 
    usuario_id BIGINT, 
    rol TEXT NOT NULL, 
    accion TEXT NOT NULL, 
    entidad TEXT NOT NULL, 
    entidad_id BIGINT, 
    motivo TEXT, 
    ip INET, 
    ts TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_auditoria PRIMARY KEY (id), 
    CONSTRAINT fk_auditoria_usuario_id_usuario FOREIGN KEY(usuario_id) REFERENCES usuario (id)
);

CREATE TABLE video (
    id BIGSERIAL NOT NULL, 
    fuente_id BIGINT NOT NULL, 
    ruta TEXT NOT NULL, 
    hash_sha256 VARCHAR(64) NOT NULL, 
    bytes BIGINT NOT NULL, 
    duracion_s REAL, 
    fps_declarado REAL, 
    ancho INTEGER, 
    alto INTEGER, 
    capture_ts_inicio TIMESTAMP WITH TIME ZONE NOT NULL, 
    origen_capture_ts TEXT NOT NULL, 
    estado TEXT DEFAULT 'en_cola' NOT NULL, 
    error_motivo TEXT, 
    cuadros_analizados INTEGER, 
    proceso_ms BIGINT, 
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_video PRIMARY KEY (id), 
    CONSTRAINT ck_video_estado CHECK (estado IN ('en_cola','procesando','listo','error')), 
    CONSTRAINT ck_video_origen_capture_ts CHECK (origen_capture_ts IN ('metadatos','mtime','manual','ocr')), 
    CONSTRAINT fk_video_fuente_id_fuente FOREIGN KEY(fuente_id) REFERENCES fuente (id), 
    CONSTRAINT uq_video_hash_sha256 UNIQUE (hash_sha256)
);

CREATE INDEX ix_video_estado_creado_en ON video (estado, creado_en);

CREATE TABLE zona (
    id BIGSERIAL NOT NULL, 
    area_id BIGINT NOT NULL, 
    fuente_id BIGINT NOT NULL, 
    nombre TEXT NOT NULL, 
    tipo TEXT NOT NULL, 
    poligono JSONB NOT NULL, 
    solape_minimo REAL DEFAULT '0.5' NOT NULL, 
    color TEXT, 
    CONSTRAINT pk_zona PRIMARY KEY (id), 
    CONSTRAINT ck_zona_tipo CHECK (tipo IN ('interes','privacidad')), 
    CONSTRAINT fk_zona_area_id_area FOREIGN KEY(area_id) REFERENCES area (id), 
    CONSTRAINT fk_zona_fuente_id_fuente FOREIGN KEY(fuente_id) REFERENCES fuente (id)
);

CREATE TABLE deteccion (
    id BIGSERIAL NOT NULL, 
    video_id BIGINT NOT NULL, 
    cuadro_idx INTEGER NOT NULL, 
    capture_ts TIMESTAMP WITH TIME ZONE NOT NULL, 
    track_id INTEGER, 
    clase TEXT NOT NULL, 
    confianza REAL NOT NULL, 
    bbox REAL[] NOT NULL, 
    zona_id BIGINT, 
    modelo_version TEXT NOT NULL, 
    CONSTRAINT pk_deteccion PRIMARY KEY (id), 
    CONSTRAINT ck_deteccion_bbox_cuatro CHECK (array_length(bbox, 1) = 4), 
    CONSTRAINT fk_deteccion_video_id_video FOREIGN KEY(video_id) REFERENCES video (id) ON DELETE CASCADE, 
    CONSTRAINT fk_deteccion_zona_id_zona FOREIGN KEY(zona_id) REFERENCES zona (id)
);

CREATE INDEX ix_deteccion_video_track_cuadro ON deteccion (video_id, track_id, cuadro_idx);

CREATE TABLE regla (
    id BIGSERIAL NOT NULL, 
    area_id BIGINT NOT NULL, 
    zona_id BIGINT, 
    nombre TEXT NOT NULL, 
    version INTEGER DEFAULT '1' NOT NULL, 
    epp_exigido TEXT[] NOT NULL, 
    confirmacion_segundos REAL DEFAULT '2.0' NOT NULL, 
    cierre_segundos REAL DEFAULT '3.0' NOT NULL, 
    confianza_minima REAL DEFAULT '0.45' NOT NULL, 
    severidad SMALLINT NOT NULL, 
    turno TEXT, 
    hora_desde TIME WITHOUT TIME ZONE, 
    hora_hasta TIME WITHOUT TIME ZONE, 
    activa BOOLEAN DEFAULT 'true' NOT NULL, 
    base_licitud TEXT NOT NULL, 
    norma_fundante TEXT, 
    finalidad_declarada TEXT NOT NULL, 
    retencion_dias INTEGER DEFAULT '30' NOT NULL, 
    creada_por BIGINT, 
    creada_en TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_regla PRIMARY KEY (id), 
    CONSTRAINT ck_regla_base_licitud CHECK (base_licitud IN ('obligacion_legal','interes_legitimo','contrato')), 
    CONSTRAINT ck_regla_epp_exigido_no_vacio CHECK (cardinality(epp_exigido) > 0), 
    CONSTRAINT ck_regla_umbrales_positivos CHECK (confirmacion_segundos > 0 AND cierre_segundos > 0), 
    CONSTRAINT ck_regla_severidad CHECK (severidad BETWEEN 1 AND 4), 
    CONSTRAINT fk_regla_area_id_area FOREIGN KEY(area_id) REFERENCES area (id), 
    CONSTRAINT fk_regla_creada_por_usuario FOREIGN KEY(creada_por) REFERENCES usuario (id), 
    CONSTRAINT fk_regla_zona_id_zona FOREIGN KEY(zona_id) REFERENCES zona (id), 
    CONSTRAINT uq_regla_area_id_nombre_version UNIQUE (area_id, nombre, version)
);

CREATE TABLE hallazgo (
    id BIGSERIAL NOT NULL, 
    video_id BIGINT, 
    fuente_id BIGINT NOT NULL, 
    area_id BIGINT NOT NULL, 
    zona_id BIGINT, 
    regla_id BIGINT NOT NULL, 
    regla_version INTEGER NOT NULL, 
    track_id INTEGER NOT NULL, 
    epp_faltante TEXT[] NOT NULL, 
    severidad SMALLINT NOT NULL, 
    ts_inicio TIMESTAMP WITH TIME ZONE NOT NULL, 
    ts_fin TIMESTAMP WITH TIME ZONE, 
    duracion_s REAL GENERATED ALWAYS AS (EXTRACT(EPOCH FROM (ts_fin - ts_inicio))) STORED, 
    cuadros_confirmados INTEGER NOT NULL, 
    confianza_media REAL NOT NULL, 
    estado TEXT DEFAULT 'por_revisar' NOT NULL, 
    revisado_por BIGINT, 
    revisado_en TIMESTAMP WITH TIME ZONE, 
    vlm_titulo TEXT, 
    vlm_descripcion TEXT, 
    vlm_confianza REAL, 
    vlm_modelo TEXT, 
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_hallazgo PRIMARY KEY (id), 
    CONSTRAINT ck_hallazgo_estado CHECK (estado IN ('por_revisar','confirmado','falso_positivo','duplicado','pospuesto')), 
    CONSTRAINT ck_hallazgo_severidad CHECK (severidad BETWEEN 1 AND 4), 
    CONSTRAINT fk_hallazgo_area_id_area FOREIGN KEY(area_id) REFERENCES area (id), 
    CONSTRAINT fk_hallazgo_fuente_id_fuente FOREIGN KEY(fuente_id) REFERENCES fuente (id), 
    CONSTRAINT fk_hallazgo_regla_id_regla FOREIGN KEY(regla_id) REFERENCES regla (id), 
    CONSTRAINT fk_hallazgo_revisado_por_usuario FOREIGN KEY(revisado_por) REFERENCES usuario (id), 
    CONSTRAINT fk_hallazgo_video_id_video FOREIGN KEY(video_id) REFERENCES video (id) ON DELETE SET NULL, 
    CONSTRAINT fk_hallazgo_zona_id_zona FOREIGN KEY(zona_id) REFERENCES zona (id)
);

CREATE INDEX ix_hallazgo_area_ts ON hallazgo (area_id, ts_inicio DESC);

CREATE INDEX ix_hallazgo_estado_severidad_ts ON hallazgo (estado, severidad, ts_inicio DESC);

CREATE TABLE accion_correctiva (
    id BIGSERIAL NOT NULL, 
    hallazgo_id BIGINT NOT NULL, 
    responsable_id BIGINT NOT NULL, 
    descripcion TEXT NOT NULL, 
    plazo DATE NOT NULL, 
    estado TEXT DEFAULT 'abierta' NOT NULL, 
    cerrada_en TIMESTAMP WITH TIME ZONE, 
    comentario_cierre TEXT, 
    CONSTRAINT pk_accion_correctiva PRIMARY KEY (id), 
    CONSTRAINT ck_accion_correctiva_estado CHECK (estado IN ('abierta','en_curso','cerrada','vencida')), 
    CONSTRAINT fk_accion_correctiva_hallazgo_id_hallazgo FOREIGN KEY(hallazgo_id) REFERENCES hallazgo (id), 
    CONSTRAINT fk_accion_correctiva_responsable_id_usuario FOREIGN KEY(responsable_id) REFERENCES usuario (id)
);

CREATE TABLE evidencia (
    id BIGSERIAL NOT NULL, 
    hallazgo_id BIGINT NOT NULL, 
    ruta TEXT NOT NULL, 
    hash_sha256 VARCHAR(64) NOT NULL, 
    cuadro_idx INTEGER NOT NULL, 
    capture_ts TIMESTAMP WITH TIME ZONE NOT NULL, 
    anonimizado BOOLEAN DEFAULT 'true' NOT NULL, 
    purgar_el DATE NOT NULL, 
    CONSTRAINT pk_evidencia PRIMARY KEY (id), 
    CONSTRAINT fk_evidencia_hallazgo_id_hallazgo FOREIGN KEY(hallazgo_id) REFERENCES hallazgo (id) ON DELETE CASCADE
);

CREATE INDEX ix_evidencia_purgar_el ON evidencia (purgar_el);

CREATE TABLE notificacion (
    id BIGSERIAL NOT NULL, 
    hallazgo_id BIGINT, 
    tipo TEXT NOT NULL, 
    canal TEXT NOT NULL, 
    destinatario TEXT NOT NULL, 
    cuerpo JSONB NOT NULL, 
    estado TEXT DEFAULT 'pendiente' NOT NULL, 
    intentos INTEGER DEFAULT '0' NOT NULL, 
    enviada_en TIMESTAMP WITH TIME ZONE, 
    acusada_en TIMESTAMP WITH TIME ZONE, 
    acusada_por BIGINT, 
    creada_en TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_notificacion PRIMARY KEY (id), 
    CONSTRAINT ck_notificacion_canal CHECK (canal IN ('correo','telegram','whatsapp','webhook')), 
    CONSTRAINT ck_notificacion_estado CHECK (estado IN ('pendiente','enviada','fallida','acusada')), 
    CONSTRAINT ck_notificacion_tipo CHECK (tipo IN ('inmediata','resumen_turno','escalamiento')), 
    CONSTRAINT fk_notificacion_acusada_por_usuario FOREIGN KEY(acusada_por) REFERENCES usuario (id), 
    CONSTRAINT fk_notificacion_hallazgo_id_hallazgo FOREIGN KEY(hallazgo_id) REFERENCES hallazgo (id)
);

CREATE INDEX ix_notificacion_estado_creada_en ON notificacion (estado, creada_en);

CREATE RULE auditoria_no_update AS ON UPDATE TO auditoria DO INSTEAD NOTHING;

CREATE RULE auditoria_no_delete AS ON DELETE TO auditoria DO INSTEAD NOTHING;

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

