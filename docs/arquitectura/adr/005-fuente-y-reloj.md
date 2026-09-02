# ADR-005 — Puerto `FrameSource` y reloj de captura

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

La v1 procesa archivos; la v2 procesará RTSP en vivo. La diferencia real entre ambas cabe en tres
decisiones, no en dos arquitecturas: de dónde sale el timestamp, qué se hace cuando el consumidor
no da abasto, y quién reinicia la fuente cuando deja de entregar cuadros.

## Decisión

1. **Puerto `FrameSource`** con cinco métodos (`open`, `grab`, `retrieve`, `release`,
   `properties`). v1 implementa `FileFrameSource`; v2 añade `RtspFrameSource` sin tocar nada más.
2. **`Frame` inmutable con `capture_ts` en UTC absoluto.** En archivo se deriva:
   `capture_ts = inicio_video + cuadro_idx / fps_declarado`, con `inicio_video` desde los
   metadatos del contenedor o, en su defecto, `mtime − duración`.
3. **Regla dura:** ningún módulo aguas abajo del ingestor puede llamar a `datetime.now()` para
   fechar un evento. Hay un test que lo verifica.
4. **Política de *backpressure* inyectable** (`WAIT`/`DROP_OLDEST`), elegida en un único punto
   según `SourceProperties.is_file`. Cola acotada, descarte por ocupación de cola —un hecho— y
   nunca por estimación de ritmo de la fuente —una conjetura.

## Por qué el reloj es lo más importante

`datetime.now()` en el punto donde se crea el evento funciona **impecable** en la v1, porque el
video se procesa el mismo día. Y es **irreparable** en la v2: los videos de la semana pasada
quedarían fechados hoy, y toda la analítica por hora, turno y tendencia —el valor de producto del
proyecto— se convierte en basura. Cuesta cero evitarlo hoy.

## El atajo que adelanta la v2

Con **MediaMTX** (MIT) se publica un `.mp4` como cámara RTSP:

```bash
ffmpeg -re -stream_loop -1 -i faena_01.mp4 -c copy -f rtsp rtsp://127.0.0.1:8554/camara_01
```

La ruta RTSP se prueba en la **S6**, con los videos del dataset, sin cámaras ni permisos.

## Consecuencias

El sistema **rechaza** rutas de carpeta vigilada bajo `/mnt/` y lo registra: `inotify` sobre el
sistema de archivos de Windows retorna éxito y jamás entrega un evento — falla en silencio, que
es la peor forma de fallar.
