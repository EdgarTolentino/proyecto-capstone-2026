-- Guardián EPP — datos de ejemplo (perfil de construcción, ADR-011).
-- GENERADO: base vacía + `make migrar` + `make semilla` (perfiles/construccion.yaml) y
-- pg_dump --data-only --inserts. Sin datos personales: los usuarios son roles con correo .invalid
-- (se quitaron las cuentas del equipo, que el perfil trae solo para el desarrollo local).
-- Se carga sobre esquema.sql: psql -f esquema.sql && psql -f datos-ejemplo.sql

--
-- PostgreSQL database dump
--


-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: faena; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.faena VALUES (1, 'Obra de referencia', 'America/Santiago', '2026-10-13 18:57:02.737735+00');


--
-- Data for Name: area; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.area VALUES (1, 1, 'Acceso y patio de materiales', 2);
INSERT INTO public.area VALUES (2, 1, 'Frente de obra gruesa', 3);


--
-- Data for Name: fuente; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.fuente VALUES (1, 1, 'Cámara 01 · acceso', 'carpeta', '/datos/videos/entrada/camara_01', 5, true, NULL);
INSERT INTO public.fuente VALUES (2, 2, 'Cámara 02 · obra gruesa', 'carpeta', '/datos/videos/entrada/camara_02', 5, true, NULL);


--
-- Data for Name: usuario; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.usuario VALUES (1, 'prevencionista@obra.invalid', 'Prevencionista de turno', 'prevencionista', NULL, true);
INSERT INTO public.usuario VALUES (2, 'supervisor.acceso@obra.invalid', 'Supervisor de acceso', 'supervisor', 1, true);
INSERT INTO public.usuario VALUES (3, 'administrador@obra.invalid', 'Administrador del sistema', 'administrador', NULL, true);
INSERT INTO public.usuario VALUES (4, 'auditor@obra.invalid', 'Auditor externo', 'auditor', NULL, true);


--
-- Data for Name: zona; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.zona VALUES (1, 1, 1, 'Todo el cuadro', 'interes', '[[0, 0], [1, 0], [1, 1], [0, 1]]', 0.5, NULL, '{casco,chaleco}');
INSERT INTO public.zona VALUES (2, 2, 2, 'Todo el cuadro', 'interes', '[[0, 0], [1, 0], [1, 1], [0, 1]]', 0.5, NULL, '{casco,chaleco}');


--
-- Data for Name: regla; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.regla VALUES (1, 1, NULL, 'Casco y chaleco en acceso', 1, '{casco,chaleco}', 2, 3, 0.45, 3, NULL, NULL, NULL, true, 'obligacion_legal', 'DS 594 art. 53', 'Verificar el uso del EPP obligatorio al ingresar a la obra', 30, NULL, '2026-10-13 18:57:02.737735+00');
INSERT INTO public.regla VALUES (2, 2, NULL, 'Casco y chaleco en obra gruesa', 1, '{casco,chaleco}', 2, 3, 0.45, 4, NULL, NULL, NULL, true, 'obligacion_legal', 'DS 594 art. 53', 'Verificar el uso del EPP obligatorio en el frente de trabajo', 30, NULL, '2026-10-13 18:57:02.737735+00');


--
-- Data for Name: video; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: hallazgo; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: accion_correctiva; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: auditoria; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: deteccion; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: dotacion; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: evidencia; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: notificacion; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: pedido_ingesta; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Name: accion_correctiva_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.accion_correctiva_id_seq', 1, false);


--
-- Name: area_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.area_id_seq', 2, true);


--
-- Name: auditoria_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.auditoria_id_seq', 1, false);


--
-- Name: deteccion_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.deteccion_id_seq', 1, false);


--
-- Name: dotacion_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.dotacion_id_seq', 1, false);


--
-- Name: evidencia_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.evidencia_id_seq', 1, false);


--
-- Name: faena_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.faena_id_seq', 1, true);


--
-- Name: fuente_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.fuente_id_seq', 2, true);


--
-- Name: hallazgo_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.hallazgo_id_seq', 1, false);


--
-- Name: notificacion_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.notificacion_id_seq', 1, false);


--
-- Name: pedido_ingesta_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.pedido_ingesta_id_seq', 1, false);


--
-- Name: regla_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.regla_id_seq', 2, true);


--
-- Name: usuario_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.usuario_id_seq', 6, true);


--
-- Name: video_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.video_id_seq', 1, false);


--
-- Name: zona_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.zona_id_seq', 2, true);


--
-- PostgreSQL database dump complete
--


