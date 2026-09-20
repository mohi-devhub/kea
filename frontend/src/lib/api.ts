import { API_URL } from "@/lib/config";
import type {
  BlastRadius,
  EvalReport,
  FixCreated,
  FixProposal,
  InvestigationResult,
  PredictionView,
  ScenarioInfo,
  TopologyResponse,
} from "@/lib/types";

/** Backend errors use `{error: {code, message}}` (CONTRACTS section 3). */
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("UNREACHABLE", "Can't reach the backend. Retrying...", 0);
  }
  if (!res.ok) {
    // most routes wrap the reason in `error`; FastAPI's own aborts carry a bare `detail` string
    const body = (await res.json().catch(() => null)) as
      | { error?: { code: string; message: string }; detail?: string }
      | null;
    const message = body?.error?.message ?? (typeof body?.detail === "string" ? body.detail : null);
    throw new ApiError(body?.error?.code ?? "ERROR", message ?? res.statusText, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  topology: () => request<TopologyResponse>("/topology"),
  scenarios: () => request<ScenarioInfo[]>("/scenarios"),
  health: () => request<{ status: string; kafka: boolean; neo4j: boolean }>("/health"),
  simulate: (scenario: string, body: { seed: number; speed: number }) =>
    request<{ run_id: string }>(`/simulate/${scenario}`, { method: "POST", body: JSON.stringify(body) }),
  recover: (runId: string) => request<{ run_id: string }>(`/runs/${runId}/recover`, { method: "POST" }),
  reset: () => request<{ status: string }>("/reset", { method: "POST" }),
  blastRadius: (incidentId: string) => request<BlastRadius>(`/incidents/${incidentId}/blast-radius`),
  prediction: (incidentId: string) => request<PredictionView>(`/incidents/${incidentId}/prediction`),
  investigate: (incidentId: string) =>
    request<{ investigation_id: string; incident_id: string; status: string }>(
      `/incidents/${incidentId}/investigate`,
      { method: "POST" },
    ),
  investigation: (investigationId: string) =>
    request<{
      investigation_id: string;
      incident_id: string;
      run_id: string;
      status: string;
      result: InvestigationResult | null;
      error: string | null;
    }>(`/investigations/${investigationId}`),
  evalLatest: () => request<EvalReport>("/eval/results/latest"),
  createFixProposal: (incidentId: string) =>
    request<FixCreated>(`/incidents/${incidentId}/fix-proposals`, { method: "POST" }),
  fixProposals: (incidentId: string) => request<FixProposal[]>(`/incidents/${incidentId}/fix-proposals`),
  fixProposal: (proposalId: string) => request<FixProposal>(`/fix-proposals/${proposalId}`),
  /** `diffHash` must be the exact string the server returned: approval is bound to it. */
  approveFix: (proposalId: string, diffHash: string, approver: string) =>
    request<FixProposal>(`/fix-proposals/${proposalId}/approve`, {
      method: "POST",
      body: JSON.stringify({ diff_hash: diffHash, approver }),
    }),
  rejectFix: (proposalId: string, reason?: string) =>
    request<FixProposal>(`/fix-proposals/${proposalId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  regenerateFix: (proposalId: string) =>
    request<FixCreated>(`/fix-proposals/${proposalId}/regenerate`, { method: "POST" }),
};
