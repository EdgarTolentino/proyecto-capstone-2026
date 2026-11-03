import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

// Espejo de la cámara por WHEP: el navegador manda su oferta SDP al mismo origen (`/espejo/…`, el
// nginx le pone la credencial) y recibe la respuesta. Solo video (sin audio) y sin trickle ICE: se
// espera a que termine la recolección y se manda la oferta completa.
export const RUTA_WHEP = "/espejo/camara/whep";
export const REINTENTO_ESPEJO_MS = 5_000;
const ESPERA_ICE_MS = 3_000;

export type EstadoEspejo = "conectando" | "en_vivo" | "apagada";

function esperarRecoleccion(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolver) => {
    const fin = () => {
      window.clearTimeout(plazo);
      pc.removeEventListener("icegatheringstatechange", alCambiar);
      resolver();
    };
    const alCambiar = () => {
      if (pc.iceGatheringState === "complete") fin();
    };
    const plazo = window.setTimeout(fin, ESPERA_ICE_MS);
    pc.addEventListener("icegatheringstatechange", alCambiar);
  });
}

export function useEspejoWhep(): { estado: EstadoEspejo; videoRef: RefObject<HTMLVideoElement | null> } {
  const [estado, setEstado] = useState<EstadoEspejo>("conectando");
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    let activo = true;
    let pc: RTCPeerConnection | undefined;
    let sesion: string | undefined; // URL del recurso WHEP (cabecera Location del POST)
    let reintento: number | undefined;

    // Cierra la conexión y borra el recurso en el servidor (DELETE al Location).
    const soltar = () => {
      const conexion = pc;
      const recurso = sesion;
      pc = undefined;
      sesion = undefined;
      if (conexion) {
        conexion.ontrack = null;
        conexion.onconnectionstatechange = null;
        conexion.close();
      }
      if (videoRef.current) videoRef.current.srcObject = null;
      if (recurso) void fetch(recurso, { method: "DELETE" }).catch(() => undefined);
    };

    const fallar = () => {
      soltar();
      if (!activo) return;
      setEstado("apagada");
      reintento = window.setTimeout(() => {
        void conectar();
      }, REINTENTO_ESPEJO_MS);
    };

    const conectar = async () => {
      if (!activo) return;
      const conexion = new RTCPeerConnection();
      pc = conexion;
      try {
        conexion.addTransceiver("video", { direction: "recvonly" });
        conexion.ontrack = (evento) => {
          if (videoRef.current && evento.streams[0]) videoRef.current.srcObject = evento.streams[0];
          if (activo) setEstado("en_vivo");
        };
        conexion.onconnectionstatechange = () => {
          if (["failed", "disconnected", "closed"].includes(conexion.connectionState) && pc === conexion) fallar();
        };
        await conexion.setLocalDescription(await conexion.createOffer());
        await esperarRecoleccion(conexion);
        const respuesta = await fetch(RUTA_WHEP, {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          body: conexion.localDescription?.sdp ?? "",
        });
        if (!respuesta.ok) throw new Error(`WHEP ${respuesta.status}`);
        const ubicacion = respuesta.headers.get("Location");
        if (ubicacion) sesion = new URL(ubicacion, new URL(RUTA_WHEP, window.location.origin)).toString();
        if (!activo) {
          soltar(); // se desmontó mientras se esperaba la respuesta
          return;
        }
        await conexion.setRemoteDescription({ type: "answer", sdp: await respuesta.text() });
      } catch {
        if (pc === conexion) fallar();
      }
    };

    void conectar();
    return () => {
      activo = false;
      window.clearTimeout(reintento);
      soltar();
    };
  }, []);

  return { estado, videoRef };
}
