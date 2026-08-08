import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import DatabasePrepLoading from "../DatabasePrepLoading";

vi.mock("../../lib/api", () => ({
  fetchSchema: vi.fn(),
}));

import { fetchSchema } from "../../lib/api";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("DatabasePrepLoading", () => {
  it("actually calls fetchSchema — this is real work, not a bare timer", async () => {
    fetchSchema.mockResolvedValue({ database: "RetailDB", tables: [] });
    const onComplete = vi.fn();
    render(<DatabasePrepLoading dbName="RetailDB" onComplete={onComplete} />);

    await waitFor(() => expect(fetchSchema).toHaveBeenCalledTimes(1));
  });

  it("calls onComplete once the schema fetch and step animation finish", async () => {
    fetchSchema.mockResolvedValue({ database: "RetailDB", tables: [] });
    const onComplete = vi.fn();
    render(<DatabasePrepLoading dbName="RetailDB" onComplete={onComplete} />);

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1), { timeout: 5000 });
  });

  it("shows an error and still completes (degrades gracefully) if the fetch fails", async () => {
    fetchSchema.mockRejectedValue(new Error("Network error"));
    const onComplete = vi.fn();
    render(<DatabasePrepLoading dbName="RetailDB" onComplete={onComplete} />);

    expect(await screen.findByText(/Network error/)).toBeInTheDocument();
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1), { timeout: 5000 });
  });

  it("does not call onComplete before the schema fetch has resolved", async () => {
    let resolveSchema;
    fetchSchema.mockReturnValue(new Promise((resolve) => { resolveSchema = resolve; }));
    const onComplete = vi.fn();
    render(<DatabasePrepLoading dbName="RetailDB" onComplete={onComplete} />);

    await new Promise((r) => setTimeout(r, 600));
    expect(onComplete).not.toHaveBeenCalled();

    resolveSchema({ database: "RetailDB", tables: [] });
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1), { timeout: 5000 });
  });
});
