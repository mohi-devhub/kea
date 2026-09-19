import { API_URL } from "@/lib/config";
import type {
  BlastRadius,
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
    const body = (await res.json().catch(() => null)) as { error?: { code: string; message: string } } | null;
    throw new ApiError(body?.error?.code ?? "ERROR", body?.error?.message ?? res.statusText, res.status);
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
};
