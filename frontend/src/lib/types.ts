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

export type EvalMetric = { k: number; n: number; ci_low: number; ci_high: number };
export type EvalAggregate = {
  approach: string;
  scenario: string;
  n: number;
  top1_correct: EvalMetric;
  top3_contains: EvalMetric;
  false_blame: EvalMetric;
  false_alarm: EvalMetric;
  /** runs that produced no answer (not_run, provider_error); never in the denominator */
  unscored?: Record<string, number>;
  /** malformed answers: scored as incorrect and disclosed */
  parse_errors?: number;
  extra: Record<string, unknown>;
};
export type EvalReport = {
  meta: {
    generated_at: string;
    git_commit: string;
    seed_set: string;
    seeds: number[];
    scenarios: string[];
    approaches: string[];
    runs: number;
    baseline_provider: string | null;
    baseline_model: string | null;
    agent_provider: string | null;
    agent_model: string | null;
    reasoning_effort: string;
    prompt_version: string;
    heldout_eval_count: number;
  };
  results: EvalAggregate[];
  warnings?: string[];
  engine_config?: { weights?: number[]; [key: string]: unknown };
  limitations: string[];
  runs?: EvalRun[];
  cost?: Record<string, EvalCost>;
  consistency?: Pick<EvalReport, "results" | "cost" | "meta">;
  scale?: ScaleReport;
  rcaeval?: RcaEvalReport;
};

export type EvalCost = {
  analyses: number;
  median_latency_ms: number | null;
  median_tokens: number | null;
  total_tokens: number;
};
export type ScalePoint = {
  services: number;
  approach: string;
  n: number;
  top1_correct: number;
  median_tokens: number | null;
  median_latency_ms: number | null;
};
export type ScaleReport = { points: ScalePoint[]; notes?: string[] };
export type RcaEvalReport = { cases: number; results: EvalAggregate[]; notes?: string[] };

export type EvalRun = {
  approach: string;
  scenario: string;
  seed: number;
  run_index: number;
  input_sha256: string;
  raw_output?: string | null;
  parsed_output?: Record<string, unknown> | null;
  grade: Record<string, unknown>;
  latency_ms?: number | null;
  usage?: Record<string, number>;
  error?: string | null;
  status?: "ok" | "not_run" | "provider_error" | "parse_error";
};
