# ADR-010 — El cómputo se parte: nube para lo público, local para la faena

**Estado:** aceptada · **Fecha:** 2026-09-02

## Contexto

Dos decisiones previas se contradicen y nadie lo había notado:

1. *"Sin GPU el proyecto igual se termina: las plataformas gratuitas dan 30 h semanales."*
2. Toda la defensa de privacidad —y el argumento de venta al cliente minero— se apoya en que
   **el video de faena no sale de la infraestructura controlada**.

Las dos no pueden ser verdad a la vez con el mismo material.

## Decisión

Se parte el cómputo por **origen del dato**, no por conveniencia:

| Etapa | Dónde | Con qué datos |
|---|---|---|
| Preentrenamiento del detector | **Nube gratuita** (Kaggle/Colab) | Solo datasets **públicos** |
| *Fine-tuning* final | **Local**, máquina con GPU | Dataset propio de faena |
| Inferencia y evaluación | **Local** | Video de faena |
| Etiquetado | **Local** (CVAT autoalojado) | Video de faena |

Con esa partición, la nube cubre la mayor parte del cómputo **legalmente**, y ni un cuadro de
faena sale de la infraestructura controlada.

## Consecuencias

- La máquina con GPU sigue siendo un **punto único de fallo**. Mitigación: respaldo semanal de
  checkpoints y del dataset etiquetado en disco externo.
- **Nunca entrenar y servir al mismo tiempo** en esa máquina: se reservan ventanas.
- Un motor de TensorRT queda atado a la GPU, el driver y la versión con que se compiló. Con una
  sola máquina con GPU, eso la convertiría en cuello de botella de despliegue: **TensorRT solo al
  final, y solo si hace falta**.
- El repositorio es público: ni una imagen de faena entra en él. Lo fuerzan el `.gitignore` y un
  gancho de pre-commit que rechaza binarios grandes.
