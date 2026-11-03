import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { listarVideos } from "../api/client";
import type { PaginaVideos } from "../api/types";
import { INTERVALO_SALA_MS } from "../api/videos";
import { sinPermiso, textoDeFallo } from "../utils/fallosSala";
import { VivoVideo } from "./VivoVideo";
import "./VideosPage.css";

interface ResultadoVideos {
  pagina?: PaginaVideos; // la última respuesta buena
  fallo?: unknown; // el error de la última consulta, hasta que una responda bien
}

export function VistaProcesada() {
  const cliente = useQueryClient();
  // «Reintentar» también remonta la vista del modelo: con 401 quedó bloqueada y no se recupera sola.
  const [reintentos, setReintentos] = useState(0);
  // Solo los `procesando`, filtrados en el servidor: un trozo de 5 s se procesa en pocos segundos y
  // la consulta es chica, así que se repite cada segundo para no perderlo. La consulta NO lanza: el
  // fallo viaja en el resultado, así vive en la caché (sobrevive a salir y volver) y `data` nunca
  // vuelve a `pending`, que es lo que hacía parpadear el aviso. Con 401 o 403 no se insiste.
  const videos = useQuery<ResultadoVideos>({
    queryKey: ["videos-sala"],
    queryFn: async () => {
      try {
        return { pagina: await listarVideos(undefined, "procesando") };
      } catch (fallo) {
        return { pagina: cliente.getQueryData<ResultadoVideos>(["videos-sala"])?.pagina, fallo };
      }
    },
    retry: false,
    refetchInterval: (consulta) => (sinPermiso(consulta.state.data?.fallo) ? false : INTERVALO_SALA_MS),
  });
  const { pagina, fallo } = videos.data ?? {};
  // Cada trozo de la cámara es un video distinto; con la `key`, el mismo video no se vuelve a montar.
  const actual = pagina?.items.find((video) => video.estado === "procesando");
  const hayFallo = fallo !== undefined;
  return (
    <section className="sala-panel" aria-labelledby="sala-procesada">
      <h2 id="sala-procesada">Vista procesada (≈ 10 s de retraso)</h2>
      {hayFallo && <p role="alert">{textoDeFallo(fallo, "videos")}</p>}
      {sinPermiso(fallo) && <button type="button" onClick={() => { setReintentos((n) => n + 1); void videos.refetch(); }}>Reintentar</button>}
      {!videos.data && <p role="status">Consultando…</p>}
      {actual && <VivoVideo key={`${actual.id}-${reintentos}`} videoId={actual.id} archivo={actual.archivo} />}
      {pagina && !actual && !hayFallo && <p role="status">Esperando el siguiente trozo…</p>}
    </section>
  );
}
