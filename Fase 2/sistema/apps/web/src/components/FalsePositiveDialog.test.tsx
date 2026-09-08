import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { FalsePositiveDialog } from "./FalsePositiveDialog";

it("restaura el foco al control que abrió el diálogo", () => {
  const opener = document.createElement("button");
  document.body.appendChild(opener);
  opener.focus();
  const { unmount } = render(
    <FalsePositiveDialog count={1} onCancel={vi.fn()} onConfirm={vi.fn()} />,
  );
  expect(screen.getByRole("textbox")).toHaveFocus();

  unmount();

  expect(opener).toHaveFocus();
  opener.remove();
});
