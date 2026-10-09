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

export function formatDuracion(segundos: number) {
  const minutos = Math.floor(segundos / 60);
  const resto = Math.round(segundos % 60);
  return minutos ? `${minutos} m ${String(resto).padStart(2, "0")} s` : `${resto} s`;
}
