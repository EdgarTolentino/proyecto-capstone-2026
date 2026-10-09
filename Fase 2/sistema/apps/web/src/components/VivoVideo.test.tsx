import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../api/client";
import type { CuadroVivo, CuadrosVivo } from "../api/client";
import { VivoVideo } from "./VivoVideo";

vi.mock("../api/client", () => ({
  ApiError: class extends Error {
    constructor(message: string, public readonly status: number, public readonly codigo?: string) { super(message); }
  },
  obtenerCuadrosVivo: vi.fn(),
}));

// --- Entorno simulado ---------------------------------------------------------------------------
// requestAnimationFrame, createImageBitmap y el lienzo no existen en jsdom: se simulan. Todas las
// posiciones y pasos son potencias de 2 (0,0625; 0,125; 0,5) para que los límites sean exactos.

interface Bitmap { seq: number; width: number; height: number; close: ReturnType<typeof vi.fn> }

const ETIQUETA = "Vista del modelo: personas y EPP detectados";
let bitmaps: Bitmap[];
let pendientes: Map<number, FrameRequestCallback>;
let marca: number;
let idAnimacion: number;
let cancelar: ReturnType<typeof vi.fn>;
let contexto: { drawImage: ReturnType<typeof vi.fn>; clearRect: ReturnType<typeof vi.fn> };
let guion: Array<CuadrosVivo | Error>;
let ultimoServido: number;

function nuevoBitmap(blob: Blob): Bitmap {
  // El tamaño del Blob es el `seq` del cuadro (ver `lote`): así se sabe qué cuadro se dibuja.
  const bitmap: Bitmap = { seq: blob.size, width: 640, height: 360, close: vi.fn() };
  bitmaps.push(bitmap);
  return bitmap;
}

function visibilidad(estado: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => estado });
  document.dispatchEvent(new Event("visibilitychange"));
}

beforeEach(() => {
  vi.useFakeTimers();
  bitmaps = [];
  pendientes = new Map();
  marca = 0;
  idAnimacion = 0;
  guion = [];
  ultimoServido = 0;
  cancelar = vi.fn((id: number) => { pendientes.delete(id); });
  contexto = { drawImage: vi.fn(), clearRect: vi.fn() };
  vi.stubGlobal("requestAnimationFrame", (llamada: FrameRequestCallback) => {
    idAnimacion += 1;
    pendientes.set(idAnimacion, llamada);
    return idAnimacion;
  });
  vi.stubGlobal("cancelAnimationFrame", cancelar);
  vi.stubGlobal("createImageBitmap", vi.fn(async (blob: Blob) => nuevoBitmap(blob)));
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(contexto as never);
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
  vi.mocked(api.obtenerCuadrosVivo).mockImplementation(async (_id, desde) => {
    const paso = guion.shift();
    if (paso instanceof Error) throw paso;
    if (paso) {
      ultimoServido = paso.ultimo_seq;
      return paso;
    }
    return { cuadros: [], ultimo_seq: Math.max(ultimoServido, desde) };
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.resetAllMocks();
  vi.useRealTimers();
});

// Cuadros `desde..hasta` (ambos incluidos); el cuadro `seq` está en la posición (seq - 1) * paso.
function lote(desde: number, hasta: number, paso = 0.0625): CuadroVivo[] {
  const cuadros: CuadroVivo[] = [];
  for (let seq = desde; seq <= hasta; seq += 1) {
    cuadros.push({ seq, posicion_s: (seq - 1) * paso, jpeg: btoa("x".repeat(seq)) });
  }
  return cuadros;
}

const respuesta = (desde: number, hasta: number, paso = 0.0625): CuadrosVivo => ({ cuadros: lote(desde, hasta, paso), ultimo_seq: hasta });
const servir = (...pasos: Array<CuadrosVivo | Error>) => { guion.push(...pasos); };
const error = (status: number) => new api.ApiError("fallo", status);
const montar = (videoId = 88) => render(<VivoVideo videoId={videoId} archivo="v.mp4" />);

const vaciar = () => act(async () => { await vi.advanceTimersByTimeAsync(0); });
const avanzar = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });
// Un tick de animación: `ms` milisegundos después del anterior.
const tick = (ms: number) => act(() => {
  marca += ms;
  const llamadas = [...pendientes.values()];
  pendientes.clear();
  for (const llamada of llamadas) llamada(marca);
});
const ticks = (cantidad: number, ms = 62.5) => { for (let i = 0; i < cantidad; i += 1) tick(ms); };

const dibujados = () => contexto.drawImage.mock.calls.map(([bitmap]) => (bitmap as Bitmap).seq);
const cerrados = () => bitmaps.filter((b) => b.close.mock.calls.length > 0).map((b) => b.seq).sort((a, b) => a - b);
const rango = (desde: number, hasta: number) => Array.from({ length: hasta - desde + 1 }, (_, i) => desde + i);
const pedidos = () => vi.mocked(api.obtenerCuadrosVivo).mock.calls;

// --- Arranque y colchón de 1 s ---------------------------------------------------------------------

it("no arranca con 0,9375 s de buffer y sí con 1 s exacto", async () => {
  servir(respuesta(1, 16)); // posiciones 0 … 0,9375
  montar();
  await vaciar();
  ticks(4);
  expect(dibujados()).toEqual([]);
  expect(screen.getByText("Esperando el primer cuadro…")).toBeVisible();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();

  servir(respuesta(17, 17)); // posición 1,0 → el buffer llega justo a 1 s
  await avanzar(500);
  tick(62.5);

  expect(dibujados()).toEqual([1]);
  expect(screen.getByRole("img", { name: ETIQUETA })).toBeVisible();
  expect(screen.queryByText("Esperando el primer cuadro…")).not.toBeInTheDocument();
});

it("dibuja en un lienzo con el rótulo accesible y el texto de atraso", async () => {
  servir(respuesta(1, 17));
  montar();
  await vaciar();
  tick(0);

  const lienzo = screen.getByRole("img", { name: ETIQUETA });
  expect(lienzo.tagName).toBe("CANVAS");
  expect(lienzo).toHaveAttribute("width", "640");
  expect(lienzo).toHaveAttribute("height", "360");
  expect(screen.getByText("Vista del modelo · en vivo (~1 s de atraso)")).toBeVisible();
  expect(screen.getByRole("region", { name: "Vista del modelo de v.mp4" })).toBeVisible();
});

// --- Ritmo: la posición del cuadro manda, no el reloj de pared -----------------------------------------

it("tras 0,5 s de reloj de reproducción se ve el cuadro de la posición 0,5, no el siguiente", async () => {
  servir(respuesta(1, 30));
  montar();
  await vaciar();
  tick(0); // arranca y muestra el primero
  ticks(8); // 8 × 62,5 ms = 0,5 s

  expect(dibujados()).toEqual(rango(1, 9)); // el cuadro 9 está justo en la posición 0,5
  expect(cerrados()).toEqual(rango(1, 9));
});

it("un tick largo salta a la mayor posición que no pasa el reloj y descarta los intermedios", async () => {
  servir(respuesta(1, 30));
  montar();
  await vaciar();
  tick(0);
  tick(500); // el reloj pasa de 0 a 0,5 de golpe

  expect(dibujados()).toEqual([1, 9]);
  expect(cerrados()).toEqual(rango(1, 9)); // los intermedios (2…8) se cerraron sin dibujarse
});

it("con los cuadros llegando en ráfaga no se muestran todos de golpe: se reproducen por su posición", async () => {
  servir(respuesta(1, 30));
  montar();
  await vaciar();
  tick(0);
  tick(62.5);

  expect(dibujados()).toEqual([1, 2]); // el 30 ya estaba en el buffer, pero su posición no llegó
});

// --- Buffer vacío ---------------------------------------------------------------------------------

it("si el buffer se vacía se queda en el último cuadro, recarga 1 s y sigue sin acelerar ni repetir", async () => {
  servir(respuesta(1, 17)); // 1 s de video
  montar();
  await vaciar();
  tick(0);
  ticks(16); // llega a la posición 1,0: se muestra el 17 y el buffer queda vacío
  expect(dibujados()).toEqual(rango(1, 17));

  ticks(10); // sin cuadros nuevos: se queda congelado, sin repetir
  expect(dibujados()).toEqual(rango(1, 17));
  expect(screen.getByRole("img", { name: ETIQUETA })).toBeVisible();

  servir(respuesta(18, 33)); // 0,9375 s de video nuevo: todavía no alcanza
  await avanzar(500);
  ticks(4);
  expect(dibujados()).toEqual(rango(1, 17));

  servir(respuesta(34, 34)); // ahora sí hay 1 s
  await avanzar(500);
  tick(62.5);
  tick(62.5);
  tick(62.5);
  expect(dibujados()).toEqual([...rango(1, 17), 18, 19, 20]); // un cuadro por tick, sin acelerar
});

// --- Saltos de seq y tope --------------------------------------------------------------------------

it("si el servidor devuelve solo los más nuevos (salta el seq), descarta lo viejo y sigue desde lo nuevo", async () => {
  servir(respuesta(1, 30), respuesta(61, 90));
  montar();
  await vaciar();
  tick(0);
  ticks(2); // se muestran 1, 2 y 3
  expect(dibujados()).toEqual([1, 2, 3]);

  await avanzar(500); // llega 61…90: faltan el 31…60
  tick(0); // el reloj salta a la posición del 61 (3,75 s) y lo muestra

  expect(dibujados()).toEqual([1, 2, 3, 61]);
  expect(cerrados()).toEqual([...rango(1, 30), 61]); // lo viejo sin mostrar (4…30) se cerró
  expect(pedidos()[1][1]).toBe(30); // el segundo pedido salió con desde = 30
  await avanzar(500);
  expect(pedidos()[2][1]).toBe(90); // y el tercero, desde lo último recibido
});

it("un salto de seq corto (sin llegar al tope) también descarta lo viejo y el reloj salta a lo nuevo", async () => {
  servir(respuesta(1, 17), respuesta(33, 49)); // el segundo lote empieza en la posición 2,0
  montar();
  await vaciar();
  tick(0);
  ticks(2);
  expect(dibujados()).toEqual([1, 2, 3]);

  await avanzar(500);
  expect(cerrados()).toEqual([...rango(1, 17)]); // 4…17 se cerraron al saltar
  tick(0);

  expect(dibujados()).toEqual([1, 2, 3, 33]); // sigue desde lo nuevo, sin esperar a que el reloj llegue a 2,0
});

it("si el tope descarta cuadros que aún no se mostraban, el reloj salta a lo más viejo que queda", async () => {
  servir(respuesta(1, 9, 0.125), respuesta(10, 41, 0.125)); // sin salto de seq: 10 sigue al 9
  montar();
  await vaciar();
  tick(0); // arranca y muestra el 1; el reloj queda en 0
  expect(dibujados()).toEqual([1]);

  await avanzar(500); // buffer 2…41 → sobran 1,875 s: se descarta hasta el 16, queda desde la posición 2,0
  expect(cerrados()).toEqual(rango(1, 16));
  tick(0);

  expect(dibujados()).toEqual([1, 17]);
});

it("sin salto de seq no se descarta nada", async () => {
  servir(respuesta(1, 20), respuesta(21, 40));
  montar();
  await vaciar();
  tick(0);
  await avanzar(500);

  expect(cerrados()).toEqual([1]); // solo el ya dibujado
});

it("el buffer guarda como mucho 3 s: lo más viejo que sobra se cierra y se descarta", async () => {
  servir(respuesta(1, 30, 0.125)); // posiciones 0 … 3,625: sobran 0,625 s
  montar();
  await vaciar();

  expect(cerrados()).toEqual(rango(1, 5)); // quedan 0,625 … 3,625: justo 3 s
  tick(0);
  expect(dibujados()).toEqual([6]); // arranca desde lo más viejo que quedó
});

it("con exactamente 3 s en el buffer no se descarta nada, y con 3,125 s se descarta el más viejo", async () => {
  servir(respuesta(1, 25, 0.125)); // 0 … 3,0
  montar();
  await vaciar();
  expect(cerrados()).toEqual([]);
  cleanup();
  bitmaps = [];

  servir(respuesta(1, 26, 0.125)); // 0 … 3,125
  montar();
  await vaciar();
  expect(cerrados()).toEqual([1]);
});

it("si un seq repetido o anterior llega otra vez, no se duplica y se cierra", async () => {
  servir(respuesta(1, 17), { cuadros: lote(10, 17), ultimo_seq: 17 });
  montar();
  await vaciar();
  await avanzar(500);

  expect(bitmaps.length).toBe(17 + 8);
  expect(cerrados()).toEqual(rango(10, 17)); // los 8 repetidos se cierran; los originales siguen en el buffer
  tick(0);
  ticks(16);
  expect(dibujados()).toEqual(rango(1, 17)); // cada cuadro se dibuja una sola vez
});

it("si el servidor empieza una secuencia nueva (ultimo_seq menor que desde), el siguiente pedido vuelve a desde 0", async () => {
  servir(respuesta(1, 17), { cuadros: [], ultimo_seq: 2 });
  montar();
  await vaciar();
  expect(cerrados()).toEqual([]); // los 17 siguen en el buffer
  await avanzar(500); // llega ultimo_seq 2 < desde 17: el trabajador empezó un intento nuevo
  expect(cerrados()).toEqual(rango(1, 17)); // el buffer viejo se vació cerrando sus bitmaps
  await avanzar(500);

  expect(pedidos().map(([, desde]) => desde)).toEqual([0, 17, 0]);
});

it("tras el reinicio de la secuencia vuelve a cargar y reproduce los cuadros nuevos desde el seq 1", async () => {
  servir(respuesta(1, 17), { cuadros: [], ultimo_seq: 2 }, respuesta(1, 17));
  montar();
  await vaciar();
  await avanzar(500);
  await avanzar(500);
  tick(0);

  expect(dibujados()).toEqual([1]); // el cuadro 1 del intento nuevo (los del viejo estaban cerrados)
  expect(bitmaps).toHaveLength(34);
  expect(bitmaps.slice(17).every((b) => b.close.mock.calls.length <= 1)).toBe(true);
  ticks(16);
  expect(dibujados()).toEqual(rango(1, 17));
});

it("un cuadro con base64 inválido se salta y los demás se reproducen", async () => {
  const cuadros = lote(1, 17);
  cuadros[4] = { ...cuadros[4], jpeg: "@@@" };
  servir({ cuadros, ultimo_seq: 17 });
  montar();
  await vaciar();
  tick(0);
  ticks(16);

  expect(dibujados()).toEqual(rango(1, 17).filter((seq) => seq !== 5));
});

// --- Cadena de pedidos ----------------------------------------------------------------------------

it("con respuesta inmediata el siguiente pedido sale a los 500 ms: a los 499 no, a los 500 sí", async () => {
  montar();
  await vaciar();
  expect(pedidos()).toHaveLength(1);

  await avanzar(499);
  expect(pedidos()).toHaveLength(1);
  await avanzar(1);
  expect(pedidos()).toHaveLength(2);
  await avanzar(499);
  expect(pedidos()).toHaveLength(2);
  await avanzar(1);
  expect(pedidos()).toHaveLength(3);
});

it("con respuestas de 400 ms sale cada 500 ms; con respuestas de 700 ms sale al llegar; nunca hay dos en vuelo", async () => {
  for (const [duracion, esperados] of [[400, [0, 500, 1000, 1500, 2000]], [700, [0, 700, 1400, 2100]]] as const) {
    const inicio = Date.now();
    const inicios: number[] = [];
    let enVuelo = 0;
    let maximo = 0;
    vi.mocked(api.obtenerCuadrosVivo).mockImplementation(async (_id, desde) => {
      inicios.push(Date.now() - inicio);
      enVuelo += 1;
      maximo = Math.max(maximo, enVuelo);
      await new Promise((resolver) => setTimeout(resolver, duracion));
      enVuelo -= 1;
      return { cuadros: [], ultimo_seq: desde };
    });
    montar();
    await vaciar();
    await avanzar(2400);

    expect(inicios.slice(0, esperados.length)).toEqual(esperados);
    expect(inicios.length).toBe(duracion === 400 ? 5 : 4);
    expect(maximo).toBe(1);
    cleanup();
  }
});

it("no apila pedidos: si el anterior no termina, no sale otro", async () => {
  vi.mocked(api.obtenerCuadrosVivo).mockReturnValue(new Promise(() => undefined));
  montar();
  await vaciar();
  await avanzar(6000);

  expect(pedidos()).toHaveLength(1);
});

it("cada pedido lleva una señal de aborto y el desde del último seq recibido", async () => {
  servir(respuesta(1, 17));
  montar();
  await vaciar();
  await avanzar(500);

  expect(pedidos()[0]).toEqual([88, 0, expect.any(AbortSignal)]);
  expect(pedidos()[1]).toEqual([88, 17, expect.any(AbortSignal)]);
});

// --- Pestaña oculta ---------------------------------------------------------------------------------

it("con la pestaña oculta cancela la animación, cierra el buffer y no pide; al volver pide de nuevo con el mismo desde", async () => {
  servir(respuesta(1, 17));
  montar();
  await vaciar();
  tick(0);
  expect(dibujados()).toEqual([1]);

  act(() => visibilidad("hidden"));
  expect(pendientes.size).toBe(0);
  expect(cancelar).toHaveBeenCalled();
  expect(cerrados()).toEqual(rango(1, 17)); // el buffer se vació
  await avanzar(10_000);
  expect(pedidos()).toHaveLength(1);

  servir(respuesta(18, 34));
  act(() => visibilidad("visible"));
  await vaciar();
  expect(pedidos()).toHaveLength(2);
  expect(pedidos()[1][1]).toBe(17);
  expect(pendientes.size).toBe(1); // la animación se reanuda
  tick(0);
  expect(dibujados()).toEqual([1, 18]); // vuelve a cargar y arranca desde lo nuevo
});

it("si arranca con la pestaña oculta no pide ni anima hasta que se vea", async () => {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
  montar();
  await avanzar(6000);

  expect(pedidos()).toHaveLength(0);
  expect(pendientes.size).toBe(0);
  act(() => visibilidad("visible"));
  await vaciar();
  expect(pedidos()).toHaveLength(1);
  expect(pendientes.size).toBe(1);
});

it("al ocultar aborta el pedido en vuelo y su respuesta tardía se ignora", async () => {
  let resolver: (valor: CuadrosVivo) => void = () => undefined;
  let senal: AbortSignal | undefined;
  vi.mocked(api.obtenerCuadrosVivo).mockImplementation((_id, _desde, signal) => {
    senal = signal;
    return new Promise<CuadrosVivo>((resolve) => { resolver = resolve; });
  });
  montar();
  await vaciar();

  act(() => visibilidad("hidden"));
  expect(senal?.aborted).toBe(true);
  resolver(respuesta(1, 17));
  await vaciar();

  expect(bitmaps).toHaveLength(0); // ni se decodificó
  expect(dibujados()).toEqual([]);
});

it("si la decodificación estaba en curso al ocultar, los bitmaps que terminan después se cierran sin dibujarse", async () => {
  const terminar: Array<() => void> = [];
  vi.stubGlobal("createImageBitmap", vi.fn((blob: Blob) => new Promise<Bitmap>((resolve) => {
    terminar.push(() => resolve(nuevoBitmap(blob)));
  })));
  servir(respuesta(1, 17));
  montar();
  await vaciar();
  expect(terminar).toHaveLength(17);

  act(() => visibilidad("hidden"));
  for (const finalizar of terminar) finalizar();
  await vaciar();

  expect(bitmaps).toHaveLength(17);
  expect(cerrados()).toEqual(rango(1, 17));
  expect(dibujados()).toEqual([]);
});

it("si se oculta con un pedido en vuelo que al abortar rechaza, al volver pide de nuevo", async () => {
  vi.mocked(api.obtenerCuadrosVivo)
    .mockImplementationOnce((_id, _desde, signal) => new Promise<CuadrosVivo>((_resolve, rechazar) => {
      signal?.addEventListener("abort", () => rechazar(new DOMException("abortado", "AbortError")));
    }))
    .mockResolvedValue(respuesta(1, 17));
  montar();
  await vaciar();

  act(() => visibilidad("hidden"));
  await vaciar();
  expect(screen.queryByText("No fue posible actualizar la vista del modelo.")).not.toBeInTheDocument();
  act(() => visibilidad("visible"));
  await vaciar();

  expect(pedidos()).toHaveLength(2);
});

it("si se oculta y se vuelve a ver mientras esperaba tras un 404, pide de inmediato y sin reintentos duplicados", async () => {
  servir(error(404));
  montar();
  await vaciar();
  expect(pedidos()).toHaveLength(1);

  await avanzar(100);
  act(() => visibilidad("hidden"));
  await avanzar(100);
  act(() => visibilidad("visible"));
  await vaciar();
  expect(pedidos()).toHaveLength(2); // de inmediato, sin esperar el segundo

  await avanzar(499);
  expect(pedidos()).toHaveLength(2);
  await avanzar(1);
  expect(pedidos()).toHaveLength(3);
  await avanzar(1000); // el reintento viejo no debe haber quedado vivo: solo 2 más por el mínimo de 500
  expect(pedidos()).toHaveLength(5);
});

// --- Desmontaje y cambio de video --------------------------------------------------------------------

it("al desmontar aborta el pedido, cancela la animación, cierra el buffer y deja de pedir", async () => {
  let senal: AbortSignal | undefined;
  vi.mocked(api.obtenerCuadrosVivo).mockImplementation(async (_id, _desde, signal) => {
    senal = signal;
    return respuesta(1, 17);
  });
  const { unmount } = montar();
  await vaciar();
  tick(0);

  unmount();
  expect(senal?.aborted).toBe(true);
  expect(pendientes.size).toBe(0);
  expect(cerrados()).toEqual(rango(1, 17));
  await avanzar(10_000);
  expect(pedidos()).toHaveLength(1);
});

it("una respuesta tardía tras desmontar no dibuja ni deja bitmaps abiertos", async () => {
  let resolver: (valor: CuadrosVivo) => void = () => undefined;
  vi.mocked(api.obtenerCuadrosVivo).mockImplementation(() => new Promise<CuadrosVivo>((resolve) => { resolver = resolve; }));
  const { unmount } = montar();
  await vaciar();

  unmount();
  resolver(respuesta(1, 17));
  await vaciar();

  expect(dibujados()).toEqual([]);
  expect(bitmaps.every((b) => b.close.mock.calls.length === 1)).toBe(true);
});

it("al cambiar de video aborta el anterior, cierra sus bitmaps y empieza de cero con el nuevo", async () => {
  const señales: AbortSignal[] = [];
  vi.mocked(api.obtenerCuadrosVivo).mockImplementation(async (_id, _desde, signal) => {
    señales.push(signal as AbortSignal);
    return respuesta(1, 17);
  });
  const { rerender } = montar();
  await vaciar();

  rerender(<VivoVideo videoId={89} archivo="b.mp4" />);
  await vaciar();

  expect(señales[0].aborted).toBe(true);
  expect(bitmaps).toHaveLength(34);
  expect(bitmaps.slice(0, 17).every((b) => b.close.mock.calls.length === 1)).toBe(true); // los del video 88
  expect(bitmaps.slice(17).every((b) => b.close.mock.calls.length === 0)).toBe(true); // los del 89 siguen en su buffer
  expect(pedidos().map(([id, desde]) => [id, desde])).toEqual([[88, 0], [89, 0]]);
  expect(screen.getByRole("region", { name: "Vista del modelo de b.mp4" })).toBeVisible();
});

// --- Cada bitmap se cierra una sola vez --------------------------------------------------------------

it("todo bitmap creado se cierra exactamente una vez: dibujado, saltado, descartado por tope o por salto de seq", async () => {
  servir(respuesta(1, 30, 0.125), respuesta(61, 90, 0.125));
  const { unmount } = montar();
  await vaciar();
  tick(0);
  ticks(3, 125);
  await avanzar(500);
  tick(125);
  tick(1000);
  unmount();

  expect(bitmaps.length).toBe(60);
  for (const bitmap of bitmaps) expect(bitmap.close).toHaveBeenCalledTimes(1);
});

// --- Errores ---------------------------------------------------------------------------------------

it("con 404 espera el primer cuadro y reintenta a los 1000 ms, no a los 999", async () => {
  servir(error(404), respuesta(1, 17));
  montar();
  await vaciar();

  expect(screen.getByText("Esperando el primer cuadro…")).toBeVisible();
  await avanzar(999);
  expect(pedidos()).toHaveLength(1);
  await avanzar(1);
  expect(pedidos()).toHaveLength(2);
  tick(0);
  expect(dibujados()).toEqual([1]);
});

it("cuando vuelve el 200 después de un 404, retoma el ritmo de 500 ms", async () => {
  servir(error(404), respuesta(1, 17));
  montar();
  await vaciar();
  await avanzar(1000);
  expect(pedidos()).toHaveLength(2);

  await avanzar(499);
  expect(pedidos()).toHaveLength(2);
  await avanzar(1);
  expect(pedidos()).toHaveLength(3);
});

it("si después de mostrar cuadros llega un 404, deja de mostrar lo anterior y espera", async () => {
  servir(respuesta(1, 17), error(404));
  montar();
  await vaciar();
  tick(0);
  expect(screen.getByRole("img", { name: ETIQUETA })).toBeVisible();

  await avanzar(500);

  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByText("Esperando el primer cuadro…")).toBeVisible();
  expect(contexto.clearRect).toHaveBeenCalled();
  expect(cerrados()).toEqual(rango(1, 17));
  ticks(5);
  expect(dibujados()).toEqual([1]); // nada del buffer viejo se dibuja
});

it.each([401, 403])("con un %i no muestra nada, cancela la animación y no vuelve a pedir", async (status) => {
  servir(error(status));
  const { container } = montar();
  await vaciar();

  expect(container).toBeEmptyDOMElement();
  expect(pendientes.size).toBe(0);
  await avanzar(10_000);
  expect(pedidos()).toHaveLength(1);
});

it("con otro error muestra un aviso corto, espera 1000 ms y se recupera solo", async () => {
  servir(error(500), respuesta(1, 17));
  montar();
  await vaciar();

  expect(screen.getByText("No fue posible actualizar la vista del modelo.")).toBeVisible();
  await avanzar(999);
  expect(pedidos()).toHaveLength(1);
  await avanzar(1);
  expect(pedidos()).toHaveLength(2);
  tick(0);
  expect(screen.getByRole("img", { name: ETIQUETA })).toBeVisible();
  expect(screen.queryByText("No fue posible actualizar la vista del modelo.")).not.toBeInTheDocument();
});

it("si tras un error llegan respuestas sin cuadros, el aviso de error pasa a «esperando»", async () => {
  servir(error(500), { cuadros: [], ultimo_seq: 0 });
  montar();
  await vaciar();
  await avanzar(1000);

  expect(screen.queryByText("No fue posible actualizar la vista del modelo.")).not.toBeInTheDocument();
  expect(screen.getByText("Esperando el primer cuadro…")).toBeVisible();
});

// --- Correcciones de la revisión ---------------------------------------------------------------

it("a ~31 cuadros/s, con el cliente atrasado y lotes de 30 con saltos de seq, igual empieza a mostrar", async () => {
  const paso = 0.03125; // 30 cuadros = 0,906 s: nunca llegan solos a 1 s de buffer
  servir(respuesta(1, 30, paso), respuesta(61, 90, paso), respuesta(121, 150, paso));
  montar();
  await vaciar();
  ticks(2, 31.25);
  await avanzar(500);
  ticks(2, 31.25);
  await avanzar(500);
  ticks(4, 31.25);

  expect(dibujados().length).toBeGreaterThan(0);
  expect(screen.getByRole("img", { name: ETIQUETA })).toBeVisible();
  expect(screen.queryByText("Esperando el primer cuadro…")).not.toBeInTheDocument();
});

it("sin saltos, un lote de 30 a ~31 cuadros/s sigue esperando 1 s de buffer (el colchón no se pierde)", async () => {
  servir(respuesta(1, 30, 0.03125));
  montar();
  await vaciar();
  ticks(4, 31.25);

  expect(dibujados()).toEqual([]);
  expect(screen.getByText("Esperando el primer cuadro…")).toBeVisible();
});

const SEGUNDO = 1000;
const terminada = () => screen.queryByText("La vista del modelo terminó.");

it("tras 59 s de 404 seguidos sigue esperando y pidiendo; al llegar a 60 s declara que la vista terminó y deja de pedir", async () => {
  servir(...Array.from({ length: 200 }, () => error(404)));
  montar();
  await vaciar();

  await avanzar(59 * SEGUNDO);
  expect(terminada()).not.toBeInTheDocument();
  expect(screen.getByText("Esperando el primer cuadro…")).toBeVisible();
  const antes = pedidos().length;

  await avanzar(1 * SEGUNDO);
  expect(terminada()).toBeVisible();
  expect(screen.queryByText("Esperando el primer cuadro…")).not.toBeInTheDocument();
  const alTerminar = pedidos().length;
  expect(alTerminar).toBeGreaterThan(antes);

  await avanzar(30 * SEGUNDO);
  expect(pedidos().length).toBe(alTerminar);
});

it("un cuadro recibido reinicia la cuenta de los 404 seguidos", async () => {
  servir(...Array.from({ length: 50 }, () => error(404)), respuesta(1, 4), ...Array.from({ length: 200 }, () => error(404)));
  montar();
  await vaciar();

  await avanzar(95 * SEGUNDO); // 50 s de 404, un 200, y luego ~45 s de 404: ninguna racha llega a 60 s
  expect(terminada()).not.toBeInTheDocument();
});

it("otro error entre los 404 también corta la racha", async () => {
  servir(...Array.from({ length: 40 }, () => error(404)), error(500), ...Array.from({ length: 200 }, () => error(404)));
  montar();
  await vaciar();

  await avanzar(95 * SEGUNDO);
  expect(terminada()).not.toBeInTheDocument();
});
