import type { components } from "@/types/api";

/** Contract types, generated from the backend models (`make types`). Never hand-edit shapes. */
type S = components["schemas"];
export type Incident = S["Incident"];
export type Anomaly = S["Anomaly"];
export type Candidate = S["Candidate"];
export type Factor = Candidate["factors"][string];
export type ChainStep = Candidate["chain"][number];
export type RejectedCandidate = S["RejectedCandidate"];
export type Evidence = S["Evidence"];
export type WhatChanged = S["WhatChanged"];
export type Prediction = S["Prediction"];
export type PredictionVerification = S["PredictionVerification"];
export type ScenarioInfo = S["ScenarioInfo"];
export type TopologyResponse = S["TopologyResponse"];
export type ServiceNode = S["ServiceNode"];
export type TopologyEdge = S["TopologyEdge"];
export type Health = Incident["service_health"][string];

export type MetricPoint = { service: string; metric: string; ts: number; value: number };

/** A metric, deployment, rollback or log event as broadcast by the API (CONTRACTS section 1). */
export type RawEvent = {
  event_id: string;
  run_id: string;
  seq: number;
  ts: number;
  service: string;
  kind: "metric" | "deployment" | "rollback" | "log";
  payload: Record<string, unknown> & {
    deployment_id?: string;
    version?: string;
    summary?: string;
    level?: string;
    message?: string;
  };
};

export type RunStarted = {
  scenario: string;
  seed: number;
  speed: number;
  warmup_end_ts?: number;
};

export type SnapshotRun = {
  run_id: string;
  scenario: string | null;
  seed: number | null;
  status: string;
  sim_ts: number;
  health: Record<string, Health>;
  incident: Incident | null;
  prediction: Prediction | null;
  verification: PredictionVerification | null;
};

/** WebSocket messages (CONTRACTS section 4), discriminated on `type`. */
type Env<T extends string, P> = { type: T; run_id: string | null; seq: number; sim_ts: number; payload: P };
export type WsMessage =
  | Env<"snapshot", { runs: SnapshotRun[] }>
  | Env<"run.started", RunStarted>
  | Env<"run.stopped", { status?: string }>
  | Env<"sim.clock", { sim_ts: number; speed: number }>
  | Env<"metrics.batch", MetricPoint[]>
  | Env<"log.batch", RawEvent[]>
  | Env<"deployment.observed", RawEvent>
  | Env<"anomaly.opened" | "anomaly.resolved", Anomaly>
  | Env<"service.health", { service: string; health: Health }>
  | Env<"incident.opened" | "incident.updated" | "incident.resolved", Incident>
  | Env<"prediction.made", Prediction>
  | Env<"prediction.verified", PredictionVerification>
  | Env<"agent.step", { investigation_id: string } & AgentTrace>
  | Env<"agent.done", InvestigationResult | { investigation_id: string; status: "failed"; error: string }>;

export type BlastRadius = {
  customer_facing_affected: string[];
  services: string[];
  root_service: string | null;
  callers: { service: string; customer_facing: boolean; hops: number }[];
  cypher: string;
  parameters: Record<string, string | null>;
};

export type PredictionView = Prediction & {
  frozen: boolean;
  verification: PredictionVerification | null;
};

export type AgentTrace = S["TraceEntry"];
export type InvestigationResult = S["InvestigationResult"];

export type InvestigationState = {
  investigation_id: string;
  status: "running" | "completed" | "failed" | "cancelled";
  result: InvestigationResult | null;
  steps: AgentTrace[];
  error?: string | null;
};
