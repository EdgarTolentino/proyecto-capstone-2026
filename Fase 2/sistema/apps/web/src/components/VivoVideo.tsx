import { useEffect, useRef, useState } from "react";

import { ApiError, obtenerCuadrosVivo, type CuadroVivo } from "../api/client";
import { ESPERA_VIVO_SIN_CUADRO_MS, INTERVALO_VIVO_MS } from "../api/videos";
import { ReproductorVivo, type CuadroListo, type Imagen } from "./reproductorVivo";

type Vista =
  | { tipo: "esperando" }
  | { tipo: "imagen" }
  | { tipo: "error" }
  | { tipo: "sin_permiso" };

async function decodificar(cuadro: CuadroVivo): Promise<CuadroListo> {
  if (!Number.isFinite(cuadro.seq) || !Number.isFinite(cuadro.posicion_s) || typeof cuadro.jpeg !== "string") {
    throw new Error("Cuadro inválido.");
  }
  const bytes = Uint8Array.from(atob(cuadro.jpeg), (caracter) => caracter.charCodeAt(0));
  const imagen = await createImageBitmap(new Blob([bytes], { type: "image/jpeg" }));
  return { seq: cuadro.seq, posicion_s: cuadro.posicion_s, imagen };
}

// Ventana «en vivo» de un video que se está procesando (prototipo local). El servidor entrega los
// últimos cuadros ya anonimizados, cada uno con su posición en el video; aquí se guardan en un
// buffer y se reproducen por esa posición, con ~1 s de atraso (ver `ReproductorVivo`). Se pide
// en cadena con autorización, solo con la pestaña visible; cada bitmap se cierra al dejar de usarse.
export function VivoVideo({ videoId, archivo }: { videoId: number; archivo: string }) {
  const [vista, setVista] = useState<Vista>({ tipo: "esperando" });
  const lienzoRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let controlador: AbortController | undefined;
    let enVuelo = false;
    let corriendo = false;
    let bloqueado = false; // sin permiso: no se vuelve a pedir
    let minimoPasado = true; // ya pasó el mínimo desde el inicio del último pedido
    let dibujado = false;
    let temporizadorMinimo: number | undefined;
    let temporizadorReintento: number | undefined;
    let idAnimacion: number | undefined;

    const dibujar = (imagen: Imagen) => {
      const lienzo = lienzoRef.current;
      if (!lienzo) return;
      const bitmap = imagen as ImageBitmap;
      if (lienzo.width !== bitmap.width) lienzo.width = bitmap.width;
      if (lienzo.height !== bitmap.height) lienzo.height = bitmap.height;
      lienzo.getContext("2d")?.drawImage(bitmap, 0, 0);
      if (!dibujado) {
        dibujado = true;
        setVista({ tipo: "imagen" });
      }
    };
    const reproductor = new ReproductorVivo(dibujar);

    // Error o 404: se deja de mostrar lo anterior y se vuelve a cargar desde cero.
    const olvidarImagen = () => {
      reproductor.vaciar();
      const lienzo = lienzoRef.current;
      if (dibujado && lienzo) lienzo.getContext("2d")?.clearRect(0, 0, lienzo.width, lienzo.height);
      dibujado = false;
    };

    const limpiarTemporizadores = () => {
      window.clearTimeout(temporizadorMinimo);
      window.clearTimeout(temporizadorReintento);
      temporizadorMinimo = undefined;
      temporizadorReintento = undefined;
    };

    const pausar = () => {
      corriendo = false;
      limpiarTemporizadores();
      if (idAnimacion !== undefined) cancelAnimationFrame(idAnimacion);
      idAnimacion = undefined;
      controlador?.abort();
      controlador = undefined;
      enVuelo = false;
      minimoPasado = true;
      reproductor.vaciar();
    };

    // Pide los siguientes cuadros solo si no hay otro pedido en vuelo y ya pasó el mínimo.
    const seguir = () => {
      if (corriendo && !bloqueado && !enVuelo && minimoPasado && temporizadorReintento === undefined) void pedir();
    };

    const pedir = async () => {
      if (enVuelo) return;
      enVuelo = true;
      minimoPasado = false;
      temporizadorMinimo = window.setTimeout(() => {
        temporizadorMinimo = undefined;
        minimoPasado = true;
        seguir();
      }, INTERVALO_VIVO_MS);
      const propio = new AbortController();
      controlador = propio;
      let despues: "seguir" | "esperar" | "nada" = "nada";
      try {
        const desde = reproductor.ultimoSeq;
        const respuesta = await obtenerCuadrosVivo(videoId, desde, propio.signal);
        if (!propio.signal.aborted) { // una respuesta tardía se ignora
          const cuadros = Array.isArray(respuesta.cuadros) ? respuesta.cuadros : [];
          const resultados = await Promise.allSettled(cuadros.map(decodificar));
          const listos = resultados.flatMap((resultado) => (resultado.status === "fulfilled" ? [resultado.value] : []));
          if (propio.signal.aborted) {
            for (const cuadro of listos) cuadro.imagen.close();
          } else {
            if (respuesta.ultimo_seq < desde) reproductor.reiniciarSecuencia();
            reproductor.agregar(listos);
            setVista((actual) => (actual.tipo === "error" ? { tipo: "esperando" } : actual));
            despues = "seguir";
          }
        }
      } catch (error) {
        if (!propio.signal.aborted) {
          olvidarImagen();
          if (error instanceof ApiError && [401, 403].includes(error.status)) {
            bloqueado = true;
            pausar();
            setVista({ tipo: "sin_permiso" });
          } else {
            // 404: todavía no hay cuadro (o es viejo). Otro error: aviso corto. En ambos se espera.
            setVista(error instanceof ApiError && error.status === 404 ? { tipo: "esperando" } : { tipo: "error" });
            despues = "esperar";
          }
        }
      }
      if (controlador === propio) enVuelo = false;
      if (despues === "seguir") {
        seguir();
      } else if (despues === "esperar") {
        minimoPasado = true;
        temporizadorReintento = window.setTimeout(() => {
          temporizadorReintento = undefined;
          seguir();
        }, ESPERA_VIVO_SIN_CUADRO_MS);
      }
    };

    const animar = (marca: number) => {
      idAnimacion = requestAnimationFrame(animar);
      reproductor.avanzar(marca);
    };

    const arrancar = () => {
      if (bloqueado || corriendo || document.visibilityState === "hidden") return;
      corriendo = true;
      idAnimacion = requestAnimationFrame(animar);
      seguir();
    };

    const alCambiarVisibilidad = () => {
      if (document.visibilityState === "hidden") pausar();
      else arrancar();
    };

    document.addEventListener("visibilitychange", alCambiarVisibilidad);
    arrancar();
    return () => {
      document.removeEventListener("visibilitychange", alCambiarVisibilidad);
      pausar();
    };
  }, [videoId]);

  if (vista.tipo === "sin_permiso") return null;
  return (
    <section className="video-live" aria-label={`Vista del modelo de ${archivo}`}>
      <figure hidden={vista.tipo !== "imagen"}>
        <canvas ref={lienzoRef} role="img" aria-label="Vista del modelo: personas y EPP detectados" />
        <figcaption>Vista del modelo · en vivo (~1 s de atraso)</figcaption>
      </figure>
      {vista.tipo === "esperando" && <p role="status">Esperando el primer cuadro…</p>}
      {vista.tipo === "error" && <p role="status">No fue posible actualizar la vista del modelo.</p>}
    </section>
  );
}
