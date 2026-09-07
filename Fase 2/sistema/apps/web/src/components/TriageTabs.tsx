import type { PaginaHallazgos, VistaTriage } from "../api/types";

interface TriageTabsProps {
  vista: VistaTriage;
  contadores?: PaginaHallazgos["contadores"];
  onChange: (vista: VistaTriage) => void;
}

const pestanas: { id: VistaTriage; texto: string; contador: keyof PaginaHallazgos["contadores"] }[] = [
  { id: "por_revisar", texto: "Por revisar", contador: "por_revisar" },
  { id: "confirmados", texto: "Confirmados", contador: "confirmado" },
  { id: "descartados", texto: "Descartados", contador: "descartado" },
  { id: "reincidentes", texto: "Reincidentes", contador: "reincidente" },
  { id: "todos", texto: "Todos", contador: "todos" },
];

export function TriageTabs({ vista, contadores, onChange }: TriageTabsProps) {
  return (
    <div className="triage-tabs" role="tablist" aria-label="Estados de triage">
      {pestanas.map((pestana) => (
        <button
          type="button"
          role="tab"
          aria-selected={vista === pestana.id}
          className={vista === pestana.id ? "is-active" : ""}
          key={pestana.id}
          onClick={() => onChange(pestana.id)}
        >
          {pestana.texto}
          <span>{contadores?.[pestana.contador] ?? "—"}</span>
        </button>
      ))}
      <div className="shortcut-help" aria-label="Atajos disponibles">
        <kbd>j</kbd><kbd>k</kbd> navegar <kbd>c</kbd> confirmar <kbd>x</kbd> falso positivo <kbd>↵</kbd> abrir
      </div>
    </div>
  );
}
