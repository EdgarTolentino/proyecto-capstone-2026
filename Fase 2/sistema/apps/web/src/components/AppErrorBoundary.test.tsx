import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";

import { AppErrorBoundary } from "./AppErrorBoundary";

function Broken(): ReactNode {
  throw new Error("fallo de render");
}

it("mantiene una salida utilizable ante un error de render", () => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);

  render(<AppErrorBoundary><Broken /></AppErrorBoundary>);

  expect(screen.getByRole("alert")).toHaveTextContent("No fue posible mostrar la aplicación");
  expect(screen.getByRole("button", { name: "Recargar" })).toBeEnabled();
});
