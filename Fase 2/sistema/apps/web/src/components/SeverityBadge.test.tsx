import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SeverityBadge } from "./SeverityBadge";

describe("SeverityBadge", () => {
  it.each([
    [4, "◆", "Crítica"],
    [3, "▲", "Alta"],
    [2, "●", "Media"],
    [1, "○", "Baja"],
  ] as const)("muestra la severidad %s con forma y palabra", (nivel, forma, palabra) => {
    render(<SeverityBadge severidad={nivel} />);

    expect(screen.getByLabelText(`Severidad ${palabra}`)).toHaveTextContent(forma);
    expect(screen.getByLabelText(`Severidad ${palabra}`)).toHaveTextContent(palabra);
  });
});
