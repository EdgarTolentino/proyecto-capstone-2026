# ADR-009 — Pipeline propio, con las ideas de Frigate copiadas sin pudor

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

Frigate NVR resuelve buena parte de lo que este proyecto necesita, es MIT y está muy vivo:
separación estricta entre captura, detección, seguimiento y eventos; detección a 5 fps por
defecto; agrupación de detecciones en "segmentos de revisión" con inicio y fin; y —desde sus
versiones recientes— un modelo de lenguaje visual selectivo sobre el evento **ya cerrado**, con
salida estructurada. Es, casi punto por punto, la arquitectura de dos etapas de este proyecto,
ya validada en producción.

El argumento inicial para no usarlo era que asume RTSP y no hace ingesta por carpeta vigilada.
**Ese argumento se cae**: con MediaMTX un `.mp4` se publica como cámara RTSP en una línea.

## Decisión

**Pipeline propio.** Y copiar de Frigate, deliberadamente, cuatro cosas:

1. El **ciclo de vida del objeto seguido** (inicio, duración, fin, puntuación acumulada).
2. El concepto de **segmento de revisión**: agrupar todo lo solapado en un único período
   revisable, y separar lo que **alerta** de lo que solo se **registra**.
3. La **cadencia de 5 fps** y el tope de cuadros para la etapa del modelo de lenguaje visual.
4. La separación en procesos, para que un detector lento no detenga la captura.

Y de la biblioteca de servicios de DeepStream, la **taxonomía de disparadores** para el motor de
reglas: ocurrencia, ausencia, persistencia, cruce de línea, conteo, intersección.

## Por qué no envolver Frigate

- Frigate es un **NVR**: trae su propia base de datos, su propio modelo de eventos y su propia
  interfaz. Nuestro valor evaluable está justo ahí —motor de reglas configurable en PostgreSQL,
  gestión de hallazgos con responsable y cierre, analítica, cumplimiento— y todo eso habría que
  construirlo **contra** el framework en vez de sobre él.
- La rúbrica de la asignatura evalúa **el sistema envuelto**: base de datos, interfaz, pruebas,
  documentación. Frigate no aporta eso; aporta precisamente la parte que ya está resuelta en el
  diseño.
- El núcleo del pipeline propio, escrito contra los puertos del ADR-005, cabe en unos pocos
  cientos de líneas. Adaptar un NVR completo a un modelo de datos ajeno cuesta más.

## Consecuencia

Se adopta **MediaMTX** desde la S6 para probar la ruta RTSP con los mismos videos del dataset. Y
se cita a Frigate en el informe como referencia de diseño: reconocer de dónde viene una buena idea
es más sólido que fingir que se inventó.
