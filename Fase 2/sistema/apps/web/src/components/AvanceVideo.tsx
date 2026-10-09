import type { AvanceVideo as Avance } from "../api/types";
import { duracionEnPalabras, formatearReloj, formatearVelocidad } from "../utils/format";

function esConteo(valor: number): boolean {
  return Number.isInteger(valor) && valor >= 0;
}

function plural(cantidad: number, singular: string, pluralTexto: string): string {
  return `${cantidad} ${cantidad === 1 ? singular : pluralTexto}`;
}

// Lo detectado en el cuadro más reciente. NO es un total del video: el detector no identifica
// a una misma persona entre cuadros, así que sumarlos engañaría.
function textoDelCuadro(ultimo: Avance["ultimo"]): string {
  if (!ultimo || !esConteo(ultimo.persona) || !esConteo(ultimo.casco) || !esConteo(ultimo.chaleco)) {
    return "Sin datos del cuadro actual.";
  }
  const { persona, casco, chaleco } = ultimo;
  return `En el cuadro actual: ${plural(persona, "persona", "personas")}, ${plural(casco, "casco", "cascos")}, ${plural(chaleco, "chaleco", "chalecos")}.`;
}

function segundosValidos(valor: number): number {
  return Number.isFinite(valor) && valor > 0 ? valor : 0;
}

// Qué muestra la fila de un video `procesando`. Sin avance publicado solo dice «Procesando…».
export function AvanceVideo({ avance, archivo }: { avance: Avance | null | undefined; archivo: string }) {
  if (!avance) return <div className="video-progress"><span className="video-progress-text">Procesando…</span></div>;

  const guardando = avance.fase === "guardando";
  const hecho = segundosValidos(avance.segundos);
  const total = avance.total_segundos != null && Number.isFinite(avance.total_segundos) && avance.total_segundos > 0
    ? avance.total_segundos
    : null;
  const velocidad = avance.velocidad == null ? null : formatearVelocidad(avance.velocidad);

  // Barra completa al guardar; indeterminada (sin `aria-valuenow`) si no se conoce el total.
  const maximo = total ?? (guardando ? Math.max(hecho, 1) : null);
  const actual = guardando ? maximo : maximo === null ? null : Math.min(hecho, maximo);
  // Hacia abajo: 100 % solo cuando de verdad terminó de recorrer el video.
  const porcentaje = actual !== null && maximo !== null ? Math.floor((actual / maximo) * 100) : null;

  // Un total menor que 1 s no cabe en segundos enteros (daría «0 de 0»): ahí la barra habla en
  // porcentaje, lo mismo que se ve.
  const enPorcentaje = !guardando && total !== null && Math.floor(total) < 1;

  let textoVisible: string;
  let textoAccesible: string;
  if (guardando) {
    textoVisible = "Guardando resultados…";
    textoAccesible = "Guardando resultados";
  } else if (total !== null && actual !== null) {
    textoVisible = `${formatearReloj(actual)} de ${formatearReloj(total)} (${porcentaje} %)`;
    textoAccesible = enPorcentaje
      ? `${porcentaje} %`
      : `${duracionEnPalabras(actual)} de ${duracionEnPalabras(total)}`;
  } else {
    textoVisible = `${formatearReloj(hecho)} transcurridos`;
    textoAccesible = `${duracionEnPalabras(hecho)} transcurridos`;
  }

  return (
    <div className="video-progress">
      <div
        className={`video-progress-bar${actual === null ? " video-progress-bar--indeterminate" : ""}`}
        role="progressbar"
        aria-label={`Avance de ${archivo}`}
        aria-valuemin={0}
        aria-valuemax={maximo === null ? undefined : enPorcentaje ? 100 : Math.floor(maximo)}
        aria-valuenow={actual === null ? undefined : enPorcentaje ? porcentaje ?? undefined : Math.floor(actual)}
        aria-valuetext={textoAccesible}
      >
        <span style={porcentaje === null ? undefined : { width: `${porcentaje}%` }} />
      </div>
      <span className="video-progress-text">{textoVisible}</span>
      {!guardando && velocidad && <span className="video-progress-text">{velocidad}</span>}
      <span className="video-progress-text">{textoDelCuadro(avance.ultimo)}</span>
    </div>
  );
}
