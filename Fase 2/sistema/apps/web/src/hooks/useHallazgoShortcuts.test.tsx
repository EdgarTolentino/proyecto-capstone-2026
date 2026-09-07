import { fireEvent, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Hallazgo } from "../api/types";
import { useHallazgoShortcuts } from "./useHallazgoShortcuts";

const hallazgos = [{ id: 1 }, { id: 2 }, { id: 3 }] as Hallazgo[];

describe("useHallazgoShortcuts", () => {
  it("usa j, k y Enter para navegar y abrir", () => {
    const onActivate = vi.fn();
    const onOpen = vi.fn();
    renderHook(() => useHallazgoShortcuts({
      hallazgos,
      activoId: 2,
      enabled: true,
      permiteTriar: true,
      visorAbierto: false,
      onActivate,
      onOpen,
      onConfirm: vi.fn(),
      onFalsePositive: vi.fn(),
    }));

    fireEvent.keyDown(window, { key: "j" });
    fireEvent.keyDown(window, { key: "k" });
    fireEvent.keyDown(window, { key: "Enter" });

    expect(onActivate).toHaveBeenNthCalledWith(1, 3);
    expect(onActivate).toHaveBeenNthCalledWith(2, 1);
    expect(onOpen).toHaveBeenCalledWith(2);
  });

  it("ignora los atajos cuando el usuario escribe", () => {
    const onConfirm = vi.fn();
    const input = document.createElement("input");
    document.body.appendChild(input);
    renderHook(() => useHallazgoShortcuts({
      hallazgos,
      activoId: 1,
      enabled: true,
      permiteTriar: true,
      visorAbierto: false,
      onActivate: vi.fn(),
      onOpen: vi.fn(),
      onConfirm,
      onFalsePositive: vi.fn(),
    }));

    fireEvent.keyDown(input, { key: "c" });

    expect(onConfirm).not.toHaveBeenCalled();
    input.remove();
  });
});
