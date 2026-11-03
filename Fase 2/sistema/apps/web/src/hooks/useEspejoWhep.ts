import { useEffect, useRef, useState } from "react";
import type { RefObject } from "react";

import { cabecerasApi } from "../api/client";

// Espejo de la cámara por WHEP: el navegador manda su oferta SDP al mismo origen (`/espejo/…`, el
// nginx le pone la credencial) y recibe la respuesta. Solo video (sin audio) y sin trickle ICE: se
// espera a que termine la recolección y se manda la oferta completa.
export const RUTA_WHEP = "/espejo/camara/whep";
export const REINTENTO_ESPEJO_MS = 5_000;
const ESPERA_ICE_MS = 3_000;
// `disconnected` suele ser transitorio (W3C): se le da este plazo para volver a `connected`.
export const GRACIA_DESCONEXION_MS = 5_000;
const PREFIJO_RECURSO = "/espejo/";

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
    let gracia: number | undefined; // plazo de una desconexión transitoria

    // Cierra la conexión y borra el recurso en el servidor (DELETE al Location).
    const soltar = () => {
      const conexion = pc;
      const recurso = sesion;
      pc = undefined;
      sesion = undefined;
      window.clearTimeout(gracia);
      gracia = undefined;
      if (conexion) {
        conexion.ontrack = null;
        conexion.onconnectionstatechange = null;
        conexion.close();
      }
      if (videoRef.current) videoRef.current.srcObject = null;
      if (recurso) void fetch(recurso, { method: "DELETE", headers: cabecerasApi() }).catch(() => undefined);
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
          if (pc !== conexion) return;
          const estadoConexion = conexion.connectionState;
          if (estadoConexion === "failed" || estadoConexion === "closed") {
            fallar();
          } else if (estadoConexion === "disconnected") {
            // Puede volver solo: se espera un poco antes de darla por perdida.
            gracia ??= window.setTimeout(() => {
              gracia = undefined;
              if (pc === conexion && conexion.connectionState !== "connected") fallar();
            }, GRACIA_DESCONEXION_MS);
          } else if (estadoConexion === "connected") {
            window.clearTimeout(gracia);
            gracia = undefined;
          }
        };
        await conexion.setLocalDescription(await conexion.createOffer());
        await esperarRecoleccion(conexion);
        if (!activo || pc !== conexion) return; // se desmontó durante la recolección: sin POST
        const respuesta = await fetch(RUTA_WHEP, {
          method: "POST",
          headers: cabecerasApi({ "Content-Type": "application/sdp" }),
          body: conexion.localDescription?.sdp ?? "",
        });
        if (!respuesta.ok) throw new Error(`WHEP ${respuesta.status}`);
        const ubicacion = respuesta.headers.get("Location");
        if (ubicacion) {
          // El DELETE solo va al mismo origen y bajo /espejo/: un Location ajeno es un fallo.
          const recurso = new URL(ubicacion, new URL(RUTA_WHEP, window.location.origin));
          if (recurso.origin !== window.location.origin || !recurso.pathname.startsWith(PREFIJO_RECURSO)) {
            throw new Error("Location inválido");
          }
          sesion = recurso.toString();
        }
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
