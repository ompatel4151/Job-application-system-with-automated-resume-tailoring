import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("renders the human label for a status", () => {
    render(<StatusBadge status="interview" />);
    expect(screen.getByText("Interview")).toBeInTheDocument();
  });

  it("renders each status with its own label", () => {
    const { rerender } = render(<StatusBadge status="offer" />);
    expect(screen.getByText("Offer")).toBeInTheDocument();
    rerender(<StatusBadge status="rejected" />);
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });
});
