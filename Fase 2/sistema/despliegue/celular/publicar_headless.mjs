// Un «celular» sin celular: Chromium headless con cámara falsa abre la página de publicación de
// MediaMTX y pulsa «publish» (WHIP por WebRTC). Prueba la ruta navegador -> MediaMTX -> segmentos.
//
//   node publicar_headless.mjs <url> <segundos> [inseguro]
//   url       http://mediamtx:8889/camara/publish
//   inseguro  si se pasa, trata el origen http como seguro; sin él, getUserMedia NO existe en un
//             origen http que no sea localhost (por eso el celular necesita HTTPS).
// El paquete `playwright` se instala solo dentro del contenedor desechable (ver README).
import { chromium } from "playwright";

const [url, segundos = "20", inseguro] = process.argv.slice(2);
const origen = new URL(url).origin;
const args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"];
if (inseguro) args.push(`--unsafely-treat-insecure-origin-as-secure=${origen}`);

const navegador = await chromium.launch({ headless: true, args });
// MediaMTX exige usuario y clave para publicar: `publicador` y CAMARA_CLAVE (del entorno).
const credenciales = process.env.CAMARA_CLAVE
  ? { httpCredentials: { username: "publicador", password: process.env.CAMARA_CLAVE } }
  : {};
const contexto = await navegador.newContext({ permissions: ["camera", "microphone"], ...credenciales });
const pagina = await contexto.newPage();
pagina.on("console", (m) => console.log("[consola]", m.text()));
await pagina.goto(url);
await pagina.waitForTimeout(1500);
const mensaje = async () => (await pagina.locator("#message").innerText()).trim();
const hayControles = await pagina.locator("#publish-button").isVisible();
console.log(`secure_context=${await pagina.evaluate(() => window.isSecureContext)} controles=${hayControles} mensaje="${await mensaje()}"`);
if (hayControles) {
  // H264 a propósito: Chromium elige AV1 por defecto y el trabajador (OpenCV) no lo decodifica:
  // el video quedaría `listo` con 0 cuadros analizados, sin error (ver el doc).
  const codecs = await pagina.locator("#video-codec option").allInnerTexts();
  console.log("códecs ofrecidos:", codecs.join(" | "));
  const h264 = codecs.find((c) => /h264/i.test(c));
  if (h264) await pagina.selectOption("#video-codec", { label: h264 });
  await pagina.fill("#video-width", "640");
  await pagina.fill("#video-height", "480");
  await pagina.fill("#video-framerate", "15");
  await pagina.fill("#video-bitrate", "1500");
  await pagina.click("#publish-button");
  await pagina.waitForTimeout(3000);
  console.log(`tras publicar: mensaje="${await mensaje()}"`);
  await pagina.waitForTimeout(Number(segundos) * 1000);
}
await navegador.close();
