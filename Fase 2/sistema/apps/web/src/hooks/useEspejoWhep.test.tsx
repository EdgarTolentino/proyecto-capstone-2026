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
  expect(init.headers).toEqual({ "Content-Type": "application/sdp" });
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
