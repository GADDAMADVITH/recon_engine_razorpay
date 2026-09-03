import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BankImportPage } from "../pages/BankImportPage";
import { mockReport } from "./fixtures";
import { ApiClientError } from "../api/client";

// Mock the api client
const importMock = vi.fn();

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      importBankCsv: (...args: unknown[]) => importMock(...args),
    },
  };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <BankImportPage />
    </MemoryRouter>,
  );
}

function mockReportWithScenarios() {
  return {
    ...mockReport,
    metadata: {
      ...mockReport.metadata,
      bank_source: "uploaded_csv",
      bank_rows_imported: 3,
    },
    summary: {
      ...mockReport.summary,
      total_orders: 4,
      reconciled_orders: 2,
      unreconciled_orders: 2,
      missing_bank_transactions: 1,
      bank_amount_mismatches: 1,
    },
    order_results: [
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0001",
        status: "reconciled" as const,
        reconciled: true,
        confidence_score: 100,
        primary_settlement_id: "SET_0001",
        valid_bank_transaction_id: "DEMO_BNK_0001",
      },
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0002",
        status: "unreconciled_settlement_amount" as const,
        reconciled: false,
        confidence_score: 40,
        primary_settlement_id: "SET_0002",
        valid_bank_transaction_id: "DEMO_BNK_0002",
        exceptions: [{ type: "BANK_AMOUNT_MISMATCH", message: "Bank amount differs." }],
      },
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0003",
        status: "unreconciled_missing_bank" as const,
        reconciled: false,
        confidence_score: 30,
        primary_settlement_id: "SET_0003",
        valid_bank_transaction_id: null,
        exceptions: [{ type: "MISSING_BANK_TRANSACTION", message: "No bank row." }],
      },
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0033",
        status: "reconciled_with_refund_adjustment" as const,
        reconciled: true,
        confidence_score: 100,
        primary_settlement_id: "SET_0029",
        valid_bank_transaction_id: "DEMO_BNK_0004",
      },
      {
        ...mockReport.order_results[0],
        order_id: "ORD_0024",
        status: "unreconciled_missing_settlement" as const,
        reconciled: false,
        confidence_score: 20,
        primary_settlement_id: null,
        valid_bank_transaction_id: null,
        exceptions: [{ type: "MISSING_SETTLEMENT", message: "No settlement." }],
      },
    ],
  };
}

describe("BankImportPage", () => {
  beforeEach(() => {
    importMock.mockReset();
    importMock.mockResolvedValue(mockReportWithScenarios());
  });

  it("renders the upload area and action buttons", () => {
    renderPage();
    expect(screen.getByRole("region", { name: /bank csv upload area/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run reconciliation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /load demo csv/i })).toBeInTheDocument();
  });

  it("shows Bank Import in page header", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: /bank csv import/i })).toBeInTheDocument();
  });

  it("run reconciliation button is disabled with no file selected", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /run reconciliation/i })).toBeDisabled();
  });

  it("load demo csv pre-fills a file and enables run", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    expect(screen.getByRole("button", { name: /run reconciliation/i })).not.toBeDisabled();
    expect(screen.getByText(/demo_bank\.csv/)).toBeInTheDocument();
  });

  it("calls importBankCsv when run reconciliation is clicked", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() => expect(importMock).toHaveBeenCalledTimes(1));
    const [file] = importMock.mock.calls[0] as [File];
    expect(file).toBeInstanceOf(File);
    expect(file.name).toBe("demo_bank.csv");
  });

  it("does not call live razorpay sync when importing", async () => {
    const syncMock = vi.fn();
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() => expect(importMock).toHaveBeenCalledTimes(1));
    expect(syncMock).not.toHaveBeenCalled();
  });

  it("shows reconciliation summary after successful import", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByText(/reconciliation summary/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/uploaded_csv/i)).toBeInTheDocument();
  });

  it("renders results table with order rows after import", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByTestId("import-results-table")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("demo-scenarios-table")).toBeInTheDocument();
    expect(screen.getByText(/demo scenarios/i)).toBeInTheDocument();
    expect(screen.getAllByText(/bank amount mismatch/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/missing bank/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/refund adjusted/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/missing settlement/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ORD_0001").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ORD_0002").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ORD_0003").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ORD_0033").length).toBeGreaterThanOrEqual(1);
  });

  it("clicking a demo scenario opens the order drawer", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByTestId("demo-scenarios-table")).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: /open ORD_0002/i }));
    expect(
      screen.getByRole("dialog", { name: /order details for ORD_0002/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /pipeline/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /audit trail/i })).toBeInTheDocument();
    expect(screen.getAllByText("Bank Amount Mismatch").length).toBeGreaterThanOrEqual(1);
  });

  it("shows all four scenario statuses in results", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByTestId("demo-scenarios-table")).toBeInTheDocument(),
    );
    // Statuses shown via StatusBadge (formatStatusLabel → sentence case)
    // Demo scenarios + full table duplicate badges; MetricCard also says "Reconciled".
    expect(screen.getAllByText("Reconciled").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Settlement amount").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Missing bank/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("With refund adjustment").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Missing settlement/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows error state when import fails", async () => {
    const user = userEvent.setup();
    importMock.mockRejectedValue(new ApiClientError("Server error", 500));
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() => expect(screen.getByText(/server error/i)).toBeInTheDocument());
    expect(screen.queryByTestId("import-results-table")).not.toBeInTheDocument();
  });

  it("shows error state when import returns validation error", async () => {
    const user = userEvent.setup();
    importMock.mockRejectedValue(
      new ApiClientError("Bank CSV is missing required columns: description", 400),
    );
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    await user.click(screen.getByRole("button", { name: /run reconciliation/i }));
    await waitFor(() =>
      expect(screen.getByText(/missing required columns/i)).toBeInTheDocument(),
    );
  });

  it("remove button clears file and resets state", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /load demo csv/i }));
    expect(screen.getByText(/demo_bank\.csv/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /remove/i }));
    expect(screen.queryByText(/demo_bank\.csv/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run reconciliation/i })).toBeDisabled();
  });
});
