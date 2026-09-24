# Diagrama entidad-relación

Generado por `scripts/exportar_esquema.py` desde `gepp_bd.modelos`. La explicación de cada tabla está en [`docs/arquitectura/01-modelo-de-datos.md`](../../../../docs/arquitectura/01-modelo-de-datos.md).

```mermaid
erDiagram
    faena {
        BIGINT id PK
        TEXT nombre
        TEXT zona_horaria
        DATETIME creado_en
    }
    area {
        BIGINT id PK
        BIGINT faena_id FK
        TEXT nombre
        SMALLINT criticidad
    }
    dotacion {
        BIGINT id PK
        BIGINT area_id FK
        DATE fecha
        TEXT turno
        INTEGER n_hombres
        INTEGER n_mujeres
        INTEGER n_otro
    }
    fuente {
        BIGINT id PK
        BIGINT area_id FK
        TEXT nombre
        TEXT tipo
        TEXT uri
        REAL fps_objetivo
        BOOLEAN activa
        TEXT cuadro_referencia
    }
    usuario {
        BIGINT id PK
        TEXT email UK
        TEXT nombre
        TEXT rol
        BIGINT area_id FK
        BOOLEAN activo
    }
    auditoria {
        BIGINT id PK
        BIGINT usuario_id FK
        TEXT rol
        TEXT accion
        TEXT entidad
        BIGINT entidad_id
        TEXT motivo
        INET ip
        DATETIME ts
    }
    video {
        BIGINT id PK
        BIGINT fuente_id FK
        TEXT ruta
        VARCHAR hash_sha256 UK
        BIGINT bytes
        REAL duracion_s
        REAL fps_declarado
        INTEGER ancho
        INTEGER alto
        DATETIME capture_ts_inicio
        TEXT origen_capture_ts
        TEXT estado
        TEXT error_motivo
        INTEGER cuadros_analizados
        BIGINT proceso_ms
        DATETIME creado_en
    }
    zona {
        BIGINT id PK
        BIGINT area_id FK
        BIGINT fuente_id FK
        TEXT nombre
        TEXT tipo
        JSONB poligono
        REAL solape_minimo
        TEXT color
        ARRAY evaluable
    }
    deteccion {
        BIGINT id PK
        BIGINT video_id FK
        INTEGER cuadro_idx
        DATETIME capture_ts
        INTEGER track_id
        TEXT clase
        REAL confianza
        ARRAY bbox
        BIGINT zona_id FK
        TEXT modelo_version
    }
    regla {
        BIGINT id PK
        BIGINT area_id FK
        BIGINT zona_id FK
        TEXT nombre
        INTEGER version
        ARRAY epp_exigido
        REAL confirmacion_segundos
        REAL cierre_segundos
        REAL confianza_minima
        SMALLINT severidad
        TEXT turno
        TIME hora_desde
        TIME hora_hasta
        BOOLEAN activa
        TEXT base_licitud
        TEXT norma_fundante
        TEXT finalidad_declarada
        INTEGER retencion_dias
        BIGINT creada_por FK
        DATETIME creada_en
    }
    hallazgo {
        BIGINT id PK
        BIGINT video_id FK
        BIGINT fuente_id FK
        BIGINT area_id FK
        BIGINT zona_id FK
        BIGINT regla_id FK
        INTEGER regla_version
        INTEGER track_id
        ARRAY epp_faltante
        SMALLINT severidad
        DATETIME ts_inicio
        DATETIME ts_fin
        REAL duracion_s
        INTEGER cuadros_confirmados
        REAL confianza_media
        TEXT estado
        BIGINT revisado_por FK
        DATETIME revisado_en
        TEXT vlm_titulo
        TEXT vlm_descripcion
        REAL vlm_confianza
        TEXT vlm_modelo
        DATETIME creado_en
    }
    accion_correctiva {
        BIGINT id PK
        BIGINT hallazgo_id FK
        BIGINT responsable_id FK
        TEXT descripcion
        DATE plazo
        TEXT estado
        DATETIME cerrada_en
        TEXT comentario_cierre
    }
    evidencia {
        BIGINT id PK
        BIGINT hallazgo_id FK
        TEXT ruta
        VARCHAR hash_sha256
        INTEGER cuadro_idx
        DATETIME capture_ts
        BOOLEAN anonimizado
        DATE purgar_el
    }
    notificacion {
        BIGINT id PK
        BIGINT hallazgo_id FK
        TEXT tipo
        TEXT canal
        TEXT destinatario
        JSONB cuerpo
        TEXT estado
        INTEGER intentos
        DATETIME enviada_en
        DATETIME acusada_en
        BIGINT acusada_por FK
        DATETIME creada_en
        TEXT id_externo
        TEXT token_acuse
        DATETIME reintentar_despues
        TEXT motivo
    }
    faena ||--o{ area : "faena_id"
    area ||--o{ dotacion : "area_id"
    area ||--o{ fuente : "area_id"
    area |o--o{ usuario : "area_id"
    usuario |o--o{ auditoria : "usuario_id"
    fuente ||--o{ video : "fuente_id"
    area ||--o{ zona : "area_id"
    fuente ||--o{ zona : "fuente_id"
    video ||--o{ deteccion : "video_id"
    zona |o--o{ deteccion : "zona_id"
    area ||--o{ regla : "area_id"
    zona |o--o{ regla : "zona_id"
    usuario |o--o{ regla : "creada_por"
    video |o--o{ hallazgo : "video_id"
    fuente ||--o{ hallazgo : "fuente_id"
    area ||--o{ hallazgo : "area_id"
    zona |o--o{ hallazgo : "zona_id"
    regla ||--o{ hallazgo : "regla_id"
    usuario |o--o{ hallazgo : "revisado_por"
    hallazgo ||--o{ accion_correctiva : "hallazgo_id"
    usuario ||--o{ accion_correctiva : "responsable_id"
    hallazgo ||--o{ evidencia : "hallazgo_id"
    hallazgo |o--o{ notificacion : "hallazgo_id"
    usuario |o--o{ notificacion : "acusada_por"
```
