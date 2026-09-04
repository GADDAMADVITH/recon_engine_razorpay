import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../App";
import { mockReport, mockSummary } from "./fixtures";

vi.mock("../hooks/useApi", () => ({
  useReconciliationReport: vi.fn(() => ({
    data: mockReport,
    loading: false,
    refreshing: false,
    error: null,
    refetch: vi.fn(),
  })),
  useReconciliationSummary: vi.fn(() => ({
    data: mockSummary,
    loading: false,
    refreshing: false,
    error: null,
    refetch: vi.fn(),
  })),
  useHealth: vi.fn(() => ({
    data: { status: "ok", service: "recon-engine-api", version: "v1" },
    loading: false,
    refreshing: false,
    error: null,
    refetch: vi.fn(),
  })),
  useFinanceControllerBatch: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  useFinanceControllerAgentRun: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  useEvaluation: vi.fn(() => ({
    data: {
      metadata: {
        evaluator: "test",
        evaluation_grain: "order",
        orders_evaluated: 50,
        report_generated_at: "",
        ground_truth_generated_at: "",
        evaluation_policy: {},
      },
      summary: {
        orders_evaluated: 50,
        binary_accuracy: 1,
        binary_precision: 1,
        binary_recall: 1,
        binary_f1_score: 1,
        strict_status_accuracy: 0.78,
        relaxed_status_accuracy: 1,
        primary_settlement_match_rate: 1,
        primary_bank_match_rate: 1,
        valid_bank_set_match_rate: 1,
      },
      binary_classification: {
        true_positives: 26,
        false_positives: 0,
        false_negatives: 0,
        true_negatives: 24,
        accuracy: 1,
        precision: 1,
        recall: 1,
        f1_score: 1,
        mismatch_count: 0,
        mismatches: [],
      },
      status_evaluation: {
        strict: { correct: 39, incorrect: 11, accuracy: 0.78, mismatches: [] },
        relaxed: { equivalence_policy: [], correct: 50, incorrect: 0, accuracy: 1, mismatches: [] },
      },
      scenario_evaluation: {},
      link_level_evaluation: {},
      global_exception_evaluation: {},
      amount_validation: {},
    },
    loading: false,
    refreshing: false,
    error: null,
    refetch: vi.fn(),
  })),
}));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe("marketing landing page", () => {
  it("renders the editorial hero and live summary metrics", async () => {
    renderAt("/");

    expect(await screen.findByRole("heading", { name: /Reconcile on facts/i }, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByText("Financial reconciliation infrastructure")).toBeInTheDocument();
    expect(screen.getByText(/Live reconciliation engine/i)).toBeInTheDocument();
    expect(screen.getAllByText("100").length).toBeGreaterThan(0);
    expect(screen.getAllByText("52").length).toBeGreaterThan(0);
    expect(screen.getAllByText("48").length).toBeGreaterThan(0);
    expect(screen.getAllByText("52.0%").length).toBeGreaterThan(0);
  }, 10000);

  it("routes Open ReconEngine and Open Console to the console", async () => {
    renderAt("/");

    const openLinks = await screen.findAllByRole("link", { name: /Open ReconEngine/i }, { timeout: 8000 });
    expect(openLinks.length).toBeGreaterThan(0);
    openLinks.forEach((link) => expect(link).toHaveAttribute("href", "/console"));

    expect(screen.getByRole("link", { name: /Open Console/i })).toHaveAttribute("href", "/console");
  });

  it("links API documentation to the FastAPI docs endpoint", async () => {
    renderAt("/");

    const docs = await screen.findAllByRole("link", { name: /View API Docs|View API Documentation/i }, { timeout: 8000 });
    expect(docs.length).toBeGreaterThan(0);
    docs.forEach((link) => expect(link).toHaveAttribute("href", "http://127.0.0.1:8001/docs"));
  });

  it("labels evaluation as ground-truth assessment only", async () => {
    renderAt("/");

    expect(await screen.findByText(/Engine evaluation/i, undefined, { timeout: 8000 })).toBeInTheDocument();
    expect(
      screen.getByText(/Ground truth is an evaluation input only/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Precision").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Recall").length).toBeGreaterThan(0);
    expect(screen.getAllByText("F1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Accuracy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("100.0%").length).toBeGreaterThanOrEqual(3);
    expect(
      screen.getByText(/50 orders evaluated against labeled ground truth/i),
    ).toBeInTheDocument();
  });

  it("does not mount the console shell on the marketing route", async () => {
    renderAt("/");

    expect(
      await screen.findByRole("heading", { name: /Reconcile on facts/i }, { timeout: 8000 }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Reconciliation Command Center" }),
    ).not.toBeInTheDocument();
  });

  it("renders the Ask ReconEngine AI entry point", async () => {
    renderAt("/");
    expect(
      await screen.findByRole("button", { name: /Ask ReconEngine AI/i }, { timeout: 8000 }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("recon-ai-chat-button")).toBeInTheDocument();
  });
});

describe("console routes remain intact", () => {
  it("serves the command center at /console", () => {
    renderAt("/console");

    expect(
      screen.getByRole("heading", { name: "Reconciliation Command Center" }),
    ).toBeInTheDocument();
  });
});
