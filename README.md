<div align="center">

# 🦺 Guardián EPP

**Detección automática de uso de Elementos de Protección Personal sobre video de obra de construcción**

*Portafolio de Título APT122 · Ingeniería en Informática · Duoc UC · Semestre 2-2026*

[![CI](https://github.com/EdgarTolentino/proyecto-capstone-2026/actions/workflows/ci.yml/badge.svg)](https://github.com/EdgarTolentino/proyecto-capstone-2026/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![uv](https://img.shields.io/badge/gestionado%20con-uv-261230)](https://github.com/astral-sh/uv)
[![Licencias](https://img.shields.io/badge/modelos-Apache--2.0-green)](docs/arquitectura/adr/002-detector-y-licencias.md)

</div>

---

## El problema

En una obra de construcción el uso de EPP es obligatorio y su incumplimiento causa lesiones. Hoy
se fiscaliza **mirando**: un prevencionista recorre el área y anota en una planilla.

Ese método falla por cuatro sitios a la vez, y ninguno se arregla contratando más gente:

- **Es muestral** — se cubre una fracción del área durante una fracción del turno.
- **Es reactivo** — el CCTV que ya existe solo se revisa *después* del accidente.
- **No deja dato** — nadie puede responder "¿qué EPP se incumple más y dónde?".
- **No es trazable** — no queda registro de que alguien haya actuado.

Mientras tanto, **la obra ya tiene cámaras grabando**. La infraestructura de observación
continua existe. Lo que falta es alguien que mire.

## Qué hace Guardián EPP

```
   HOY                                  CON GUARDIÁN EPP
   ───                                  ────────────────
   Cámara → (nada) → accidente          Cámara → detección → evento → alerta → acción → dato
            └ se revisa el video                                                  └ tendencia
              después                                                               y prioridad
```

Convierte cada incumplimiento en un **hallazgo**: *"en Chancado Primario, entre las 02:10:14 y
las 02:10:52, una persona estuvo sin casco"* — con evidencia recortada, severidad, un responsable
que debe actuar y un registro de que actuó.

## Las cinco decisiones que lo sostienen

| # | Decisión | Por qué importa |
|---|---|---|
| 1 | **El evento, no el cuadro, es la unidad** | Sin esto un turno son 200.000 alertas. Con esto, 12 hallazgos. |
| 2 | **La fuente de video está detrás de un puerto** | La v1 lee archivos y la v2 leerá RTSP. El resto no se entera. |
| 3 | **El reloj viene de la captura, no del procesamiento** | Un video de la semana pasada fecha sus eventos la semana pasada. Es irreparable si se hace mal. |
| 4 | **Las reglas viven en la base de datos, versionadas** | Cambiar un requisito de EPP no puede exigir un despliegue. |
| 5 | **El sistema no identifica personas** | Requisito legal, condición de aceptación sindical y simplificación técnica, todo a la vez. |

## Qué **no** es

- **No es vigilancia individual.** No hay reconocimiento facial, no hay registro por trabajador y
  no alimenta procesos disciplinarios. Reporta por área y turno.
- **No es un detector de objetos.** El detector es una pieza; el proyecto es la plataforma que
  convierte detecciones en decisiones.
- **No reemplaza al prevencionista.** Le dice dónde mirar. Es **complemento** de la supervisión,
  nunca sustituto.

## Pila técnica

| Capa | Elección | Por qué esta y no la obvia |
|---|---|---|
| Detector | **RF-DETR** (Apache-2.0) | La opción obvia es AGPL-3.0 y **alcanza a los pesos que uno mismo entrena** |
| Seguidor | Por solapamiento de cajas (IoU), propio | ByteTrack vía `roboflow/trackers` choca con OpenCV sin interfaz; se decide en PT-08. El paquete cómodo del ecosistema es AGPL |
| Etapa 2 | VLM local, **solo describe** | Un VLM decidiendo hace el sistema no auditable |
| Backend | **FastAPI + PostgreSQL** | Contrato OpenAPI verificado en CI: el frontend nunca espera al backend |
| Frontend | **React + Vite** | Dos personas dedicadas necesitan trabajar en paralelo |
| Entorno | **uv workspace**, 5 paquetes | Las dos máquinas sin GPU levantan la API sin descargar CUDA |

Cada elección está justificada en un [ADR](docs/arquitectura/adr/).

## Documentación

| | |
|---|---|
| 🎯 [Problema y visión](docs/producto/01-problema-y-vision.md) | Qué se construye y para quién |
| 🏛️ [Arquitectura](docs/arquitectura/00-arquitectura.md) | La especificación técnica |
| 🗃️ [Modelo de datos](docs/arquitectura/01-modelo-de-datos.md) | Esquema, roles y retención |
| 📐 [Decisiones (ADR)](docs/arquitectura/adr/) | Por qué cada elección, y qué se descartó |
| 📊 [Plan de evaluación](docs/arquitectura/02-plan-de-evaluacion.md) | Las métricas y el QA |
| 🔔 [Alertas](docs/arquitectura/03-alertas.md) | Cómo se avisa sin quemar al usuario |
| 🔒 [Privacidad y cumplimiento](docs/producto/02-privacidad-y-cumplimiento.md) | El marco legal, traducido a diseño |
| ⚠️ [Verificaciones críticas](docs/producto/06-verificaciones-criticas.md) | **Léelo antes de escribir código** |
| 📅 [Plan de trabajo](docs/producto/03-plan-de-trabajo.md) | Las 18 semanas |
| 🧭 [Plan de desarrollo](docs/producto/09-plan-de-desarrollo-vision.md) | Visión, ingesta, API y datos: paquetes de trabajo S5-S15 |
| 🎨 [Diseño de interfaz](docs/producto/05-diseno-interfaz.md) | Las 10 pantallas y el estilo |
| ▶️ [Recorrido de punta a punta](docs/operacion/recorrido-h2.md) | Del video a la bandeja en un portátil sin GPU, y el guion de la demo |

## Estructura del repositorio

```
Fase 1/  Fase 2/  Fase 3/     Entregables de la asignatura (Evidencias Grupales,
                              Individuales y, en la Fase 2, del Proyecto)
Fase 2/sistema/               El código
├── packages/
│   ├── gepp-core/            Dominio puro: sin torch, sin cv2, sin framework web
│   ├── gepp-bd/              Esquema, migraciones y repositorios: dueño de la base (ADR-012)
│   ├── gepp-vision/          Detector, seguidor, privacidad, pipeline de la Etapa 1
│   ├── gepp-api/             FastAPI + PostgreSQL — NO importa gepp-vision
│   └── gepp-worker/          Ingesta: carpeta vigilada (v1) y RTSP (v2)
├── apps/web/                 React + Vite
├── perfiles/                 El dominio como configuración: construcción (ADR-011)
├── demo/                     Guion del detector simulado para `make demo`
└── contracts/                El OpenAPI congelado, verificado en CI
docs/                         Arquitectura, producto y decisiones
```

## Empezar

```bash
git clone https://github.com/EdgarTolentino/proyecto-capstone-2026.git
cd "proyecto-capstone-2026/Fase 2/sistema"

make setup      # máquinas sin GPU y CI
make setup-gpu  # la máquina con GPU

make up        # PostgreSQL y Redis (Docker)
make test       # 227 pruebas sin GPU; 90 de ellas usan la base de `make up` (sin ella se omiten)
make lint
make demo VIDEO=ruta.mp4   # recorrido de punta a punta: ver docs/operacion/recorrido-h2.md
make api        # la API real en :8000
make ayuda      # todos los comandos
```

## Equipo

| | Responsabilidad |
|---|---|
| [@EdgarTolentino](https://github.com/EdgarTolentino) | Líder · visión, backend, datos, arquitectura |
| [@miguelOrtega33](https://github.com/miguelOrtega33) | Frontend · bandeja, visor, reglas |
| [@laincs](https://github.com/laincs) | Frontend · analítica, reportes, administración |

Flujo de trabajo: rama por tarea → Pull Request → CI en verde → revisión → *squash merge*.
Las decisiones técnicas de fondo se escriben como [ADR](docs/arquitectura/adr/), no se discuten
en el chat.

## Sobre los datos de este repositorio

Este repositorio es **público**, y eso condiciona qué puede entrar:

- ❌ **Ninguna imagen ni video de trabajadores reales.** Ni un cuadro. Lo bloquean el
  `.gitignore` y un gancho de pre-commit.
- ❌ **Ningún dato personal** en las Evidencias Individuales: los documentos con RUT se entregan
  por el canal oficial de la asignatura.
- ❌ **Ningún peso de modelo ni dataset.** Van a *releases* o a almacenamiento externo.
- ✅ Código, documentación, esquemas y métricas agregadas.

El corpus de video y el dataset etiquetado viven **fuera del repositorio**, en infraestructura
controlada. No es una precaución retórica: subir un solo lote de CCTV de faena a un servicio
público es un incidente de datos personales.

## Licencia

Pendiente de decisión del equipo. La elección está condicionada por las licencias de los modelos
—ver [ADR-002](docs/arquitectura/adr/002-detector-y-licencias.md)— y hay que cerrarla **antes** de
la S15, no después.
