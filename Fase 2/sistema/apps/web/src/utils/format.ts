export function formatHora(fecha: string) {
  return new Intl.DateTimeFormat("es-CL", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(fecha));
}

export function formatDuracion(segundos: number) {
  const minutos = Math.floor(segundos / 60);
  const resto = Math.round(segundos % 60);
  return minutos ? `${minutos} m ${String(resto).padStart(2, "0")} s` : `${resto} s`;
}
