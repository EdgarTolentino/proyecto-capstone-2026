# Diseño aprobado

`bandeja-y-visor.dc.html` es el diseño exportado de Claude Design el **2026-09-04**, tal cual.
Es la referencia congelada: cuando en la S13 alguien pregunte "¿esta pantalla era así?", la
respuesta está aquí y no en una conversación perdida.

Ábrelo en el navegador para verlo. `support.js` es el runtime del exportador; no se toca.

## Esto NO es el código de la aplicación

Es un **maquetado**: datos fijos, estilos en línea, sin estado, sin componentes, sin tipos.
Copiarlo a React y "hacerlo funcionar" produce un componente gigante que nadie va a poder tocar
en la S13 sin romper algo.

**Lo que sí se hereda de aquí son los valores**, y ya están extraídos en
[`../tokens.css`](../tokens.css): colores, tipografías, tamaños, alturas y radios exactos. Se
construye contra las variables — ni copiando el maquetado, ni sacando colores de una captura.

## Las capturas que se entregan al docente

Están en `Fase 2/Evidencias Proyecto/Evidencias de documentacion/`, junto con lo que se verificó
sobre ellas: prueba de daltonismo, coherencia con el contrato y reglas de privacidad.

## Historial

Las tres iteraciones —qué se corrigió en cada una y por qué— están en
[`../PROMPT-DISENO.md`](../PROMPT-DISENO.md).
