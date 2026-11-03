import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { RUTA_WHEP, useEspejoWhep } from "./useEspejoWhep";

// jsdom no trae WebRTC: se simulan `RTCPeerConnection` y `fetch`.
class ConexionFalsa extends EventTarget {
  static todas: ConexionFalsa[] = [];
  iceGatheringState = "complete";
  connectionState = "new";
  localDescription = { type: "offer", sdp: "oferta-completa" };
  ontrack: ((e: { streams: unknown[] }) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;
  transceivers: Array<[string, unknown]> = [];
  remota?: { type: string; sdp: string };
  close = vi.fn();
  constructor() {
    super();
    ConexionFalsa.todas.push(this);
  }
  addTransceiver(tipo: string, opciones: unknown) {
    this.transceivers.push([tipo, opciones]);
  }
  async createOffer() {
    return { type: "offer", sdp: "oferta" };
  }
  async setLocalDescription() {}
  async setRemoteDescription(d: { type: string; sdp: string }) {
    this.remota = d;
  }
}

let respuestas: Array<Response | Error>;
let fetchFalso: ReturnType<typeof vi.fn>;

const llamadas = (metodo: string) => fetchFalso.mock.calls.filter(([, init]) => init?.method === metodo);

beforeEach(() => {
  vi.useFakeTimers();
  ConexionFalsa.todas = [];
  respuestas = [];
  fetchFalso = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "DELETE") return new Response(null, { status: 200 });
    const siguiente = respuestas.shift() ?? new Error("sin respuesta");
    if (siguiente instanceof Error) throw siguiente;
    return siguiente;
  });
  vi.stubGlobal("RTCPeerConnection", ConexionFalsa);
  vi.stubGlobal("fetch", fetchFalso);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const REINTENTO_ESPEJO_MS = 5_000; // literal a propósito: si cambia la constante, el test debe enterarse
const ok = () => new Response("respuesta-sdp", { status: 201, headers: { Location: "/espejo/camara/whep/abc" } });
const asentar = () => act(async () => { await vi.advanceTimersByTimeAsync(0); });

it("manda la oferta completa por POST como application/sdp, solo con video, y no recibe audio", async () => {
  respuestas = [ok()];
  const { result } = renderHook(() => useEspejoWhep());
  await asentar();
  const [url, init] = llamadas("POST")[0];
  expect(url).toBe(RUTA_WHEP);
  expect(init.headers.get("Content-Type")).toBe("application/sdp");
  expect(init.body).toBe("oferta-completa");
  expect(ConexionFalsa.todas[0].transceivers).toEqual([["video", { direction: "recvonly" }]]);
  expect(ConexionFalsa.todas[0].remota).toEqual({ type: "answer", sdp: "respuesta-sdp" });
  expect(result.current.estado).toBe("conectando"); // «en vivo» solo cuando llega el video
  act(() => ConexionFalsa.todas[0].ontrack?.({ streams: [{}] }));
  expect(result.current.estado).toBe("en_vivo");
});

it("espera a que termine la recolección de candidatos antes de mandar la oferta", async () => {
  respuestas = [ok()];
  const original = ConexionFalsa.prototype.createOffer;
  ConexionFalsa.prototype.createOffer = async function (this: ConexionFalsa) {
    this.iceGatheringState = "gathering";
    return original.call(this);
  };
  try {
    renderHook(() => useEspejoWhep());
    await asentar();
    expect(llamadas("POST")).toHaveLength(0);
    const conexion = ConexionFalsa.todas[0];
    conexion.iceGatheringState = "complete";
    await act(async () => { conexion.dispatchEvent(new Event("icegatheringstatechange")); });
    await asentar();
    expect(llamadas("POST")).toHaveLength(1);
  } finally {
    ConexionFalsa.prototype.createOffer = original;
  }
});

it("al desmontar borra el recurso con DELETE al Location y cierra la conexión", async () => {
  respuestas = [ok()];
  const { unmount } = renderHook(() => useEspejoWhep());
  await asentar();
  expect(llamadas("DELETE")).toHaveLength(0);
  unmount();
  expect(llamadas("DELETE").map(([url]) => url)).toEqual([`${window.location.origin}/espejo/camara/whep/abc`]);
  expect(ConexionFalsa.todas[0].close).toHaveBeenCalled();
});

it.each([503, 404])("con %i muestra «apagada» y reintenta cada ~5 s sin romper", async (codigo) => {
  respuestas = [new Response("", { status: codigo }), ok()];
  const { result } = renderHook(() => useEspejoWhep());
  await asentar();
  expect(result.current.estado).toBe("apagada");
  expect(llamadas("POST")).toHaveLength(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(REINTENTO_ESPEJO_MS - 1); });
  expect(llamadas("POST")).toHaveLength(1); // todavía no
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(llamadas("POST")).toHaveLength(2);
  act(() => ConexionFalsa.todas[1].ontrack?.({ streams: [{}] }));
  expect(result.current.estado).toBe("en_vivo");
});

it("un error de red también deja «apagada» y reintenta", async () => {
  respuestas = [new Error("red"), ok()];
  const { result } = renderHook(() => useEspejoWhep());
  await asentar();
  expect(result.current.estado).toBe("apagada");
  await act(async () => { await vi.advanceTimersByTimeAsync(REINTENTO_ESPEJO_MS); });
  expect(llamadas("POST")).toHaveLength(2);
});

it("si la conexión se cae después de conectar, vuelve a «apagada» y reintenta", async () => {
  respuestas = [ok(), ok()];
  const { result } = renderHook(() => useEspejoWhep());
  await asentar();
  const primera = ConexionFalsa.todas[0];
  act(() => primera.ontrack?.({ streams: [{}] }));
  primera.connectionState = "failed";
  act(() => primera.onconnectionstatechange?.());
  expect(result.current.estado).toBe("apagada");
  await act(async () => { await vi.advanceTimersByTimeAsync(REINTENTO_ESPEJO_MS); });
  expect(llamadas("POST")).toHaveLength(2);
});

it("al desmontar deja de reintentar", async () => {
  respuestas = [new Response("", { status: 503 })];
  const { unmount } = renderHook(() => useEspejoWhep());
  await asentar();
  unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(REINTENTO_ESPEJO_MS * 3); });
  expect(llamadas("POST")).toHaveLength(1);
});

const conLocation = (ubicacion: string) => new Response("respuesta-sdp", { status: 201, headers: { Location: ubicacion } });

it.each([
  ["otro origen", "https://otro.example/espejo/x"],
  ["fuera de /espejo/", "/otra-ruta/x"],
])("un Location %s se trata como fallo y no se le manda nunca un DELETE", async (_caso, ubicacion) => {
  respuestas = [conLocation(ubicacion)];
  const { result, unmount } = renderHook(() => useEspejoWhep());
  await asentar();
  expect(result.current.estado).toBe("apagada");
  unmount();
  expect(llamadas("DELETE")).toHaveLength(0);
  expect(fetchFalso.mock.calls.every(([url]) => url === RUTA_WHEP)).toBe(true);
});

it("si se desmonta durante la recolección de candidatos, al vencer el plazo no manda el POST", async () => {
  respuestas = [ok()];
  const original = ConexionFalsa.prototype.createOffer;
  ConexionFalsa.prototype.createOffer = async function (this: ConexionFalsa) {
    this.iceGatheringState = "gathering"; // nunca termina
    return original.call(this);
  };
  try {
    const { unmount } = renderHook(() => useEspejoWhep());
    await asentar();
    unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(llamadas("POST")).toHaveLength(0);
  } finally {
    ConexionFalsa.prototype.createOffer = original;
  }
});

async function conectada() {
  respuestas = [ok(), ok()];
  const hook = renderHook(() => useEspejoWhep());
  await asentar();
  const conexion = ConexionFalsa.todas[0];
  act(() => conexion.ontrack?.({ streams: [{}] }));
  const cambiar = (estado: string) => act(() => {
    conexion.connectionState = estado;
    conexion.onconnectionstatechange?.();
  });
  return { ...hook, conexion, cambiar };
}
const GRACIA = 5_000; // literal a propósito, como el reintento

it("`disconnected` es transitorio: si vuelve a `connected` dentro del plazo, no se cierra ni se borra nada", async () => {
  const { result, conexion, cambiar } = await conectada();
  cambiar("disconnected");
  await act(async () => { await vi.advanceTimersByTimeAsync(GRACIA - 1); });
  expect(conexion.close).not.toHaveBeenCalled();
  expect(result.current.estado).toBe("en_vivo");
  cambiar("connected");
  await act(async () => { await vi.advanceTimersByTimeAsync(GRACIA * 2); });
  expect(conexion.close).not.toHaveBeenCalled();
  expect(llamadas("DELETE")).toHaveLength(0);
  expect(result.current.estado).toBe("en_vivo");
});

it("si `disconnected` no se recupera en el plazo, falla: «apagada», DELETE y reintento", async () => {
  const { result, conexion, cambiar } = await conectada();
  cambiar("disconnected");
  await act(async () => { await vi.advanceTimersByTimeAsync(GRACIA - 1); });
  expect(llamadas("DELETE")).toHaveLength(0);
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(result.current.estado).toBe("apagada");
  expect(conexion.close).toHaveBeenCalled();
  expect(llamadas("DELETE")).toHaveLength(1);
  await act(async () => { await vi.advanceTimersByTimeAsync(REINTENTO_ESPEJO_MS); });
  expect(llamadas("POST")).toHaveLength(2);
});

it.each(["failed", "closed"])("`%s` falla de inmediato, sin esperar el plazo", async (estado) => {
  const { result, cambiar } = await conectada();
  cambiar(estado);
  expect(result.current.estado).toBe("apagada");
});

it("el POST y el DELETE llevan la misma autorización que el cliente de la API (nginx la comprueba)", async () => {
  respuestas = [ok()];
  const { unmount } = renderHook(() => useEspejoWhep());
  await asentar();
  unmount();
  const { cabecerasApi } = await import("../api/client");
  const esperada = cabecerasApi().get("Authorization");
  expect(esperada).toMatch(/^Bearer .+/);
  const [post] = llamadas("POST");
  const [borrar] = llamadas("DELETE");
  expect(new Headers(post[1].headers).get("Authorization")).toBe(esperada);
  expect(new Headers(borrar[1].headers).get("Authorization")).toBe(esperada);
});
