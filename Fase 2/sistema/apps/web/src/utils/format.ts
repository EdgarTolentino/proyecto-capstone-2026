export function formatHora(fecha: string) {
  return new Intl.DateTimeFormat("es-CL", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(fecha));
}

const UNIDADES_BYTES = ["B", "KB", "MB", "GB", "TB"];

// Tamaño legible con base 1024. Un valor que redondea a 1024,0 pasa a la unidad siguiente.
export function formatearBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  let valor = bytes;
  let unidad = 0;
  while (valor >= 1023.95 && unidad < UNIDADES_BYTES.length - 1) {
    valor /= 1024;
    unidad += 1;
  }
  const texto = unidad === 0 ? String(valor) : valor.toFixed(1).replace(".", ",");
  return `${texto} ${UNIDADES_BYTES[unidad]}`;
}

function segundosEnteros(segundos: number): number | null {
  return Number.isFinite(segundos) && segundos >= 0 ? Math.floor(segundos) : null;
}

// Reloj de avance: «2:30», o «1:02:03» desde la hora. Un valor inválido da «—».
export function formatearReloj(segundos: number): string {
  const total = segundosEnteros(segundos);
  if (total === null) return "—";
  const horas = Math.floor(total / 3600);
  const minutos = Math.floor((total % 3600) / 60);
  const resto = total % 60;
  const ss = String(resto).padStart(2, "0");
  return horas > 0 ? `${horas}:${String(minutos).padStart(2, "0")}:${ss}` : `${minutos}:${ss}`;
}

function plural(cantidad: number, singular: string, pluralTexto: string): string {
  return `${cantidad} ${cantidad === 1 ? singular : pluralTexto}`;
}

// La misma duración dicha en palabras, para lectores de pantalla: «2 minutos 30 segundos».
export function duracionEnPalabras(segundos: number): string {
  const total = segundosEnteros(segundos);
  if (total === null) return "duración desconocida";
  const horas = Math.floor(total / 3600);
  const minutos = Math.floor((total % 3600) / 60);
  const resto = total % 60;
  const partes: string[] = [];
  if (horas > 0) partes.push(plural(horas, "hora", "horas"));
  if (minutos > 0) partes.push(plural(minutos, "minuto", "minutos"));
  if (resto > 0 || partes.length === 0) partes.push(plural(resto, "segundo", "segundos"));
  return partes.join(" ");
}

// Segundos de video analizados por segundo de reloj: 1,0 es tiempo real. Inválida: null.
export function formatearVelocidad(velocidad: number): string | null {
  if (!Number.isFinite(velocidad) || velocidad < 0) return null;
  return `${velocidad.toFixed(1).replace(".", ",")}× tiempo real`;
}

export function formatDuracion(segundos: number) {
  const minutos = Math.floor(segundos / 60);
  const resto = Math.round(segundos % 60);
  return minutos ? `${minutos} m ${String(resto).padStart(2, "0")} s` : `${resto} s`;
}
