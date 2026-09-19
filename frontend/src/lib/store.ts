import { create } from "zustand";
import { humanizeMetric } from "@/lib/fmt";
import type {
  Anomaly,
  BlastRadius,
  Health,
  Incident,
  InvestigationState,
  AgentTrace,
  MetricPoint,
  Prediction,
  PredictionVerification,
  RawEvent,
  RunStarted,
  ScenarioInfo,
  TopologyResponse,
  WsMessage,
} from "@/lib/types";

export type Conn = "connecting" | "connected" | "reconnecting" | "fixture";
export type TimelineKind = "deployment" | "rollback" | "anomaly" | "health" | "incident" | "log" | "prediction";
export type Tone = "neutral" | "ok" | "warn" | "bad";
export type Tab = "overview" | "investigate" | "fix";

export const TIMELINE_KINDS: TimelineKind[] = [
  "deployment",
  "rollback",
  "anomaly",
  "health",
  "incident",
  "log",
  "prediction",
];

export type TimelineItem = {
  id: string;
  ts: number;
  kind: TimelineKind;
  tone: Tone;
  statement: string;
  service?: string;
};

export type RunInfo = {
  run_id: string;
  scenario: string | null;
  seed: number | null;
  speed: number | null;
  status: string; // running | completed | stopped | resolved
  warmup_end_ts?: number;
};

/** `frozen: false` is a live preview from GET /incidents/{id}/prediction; true = made at Recover. */
export type PredictionState = Prediction & { frozen: boolean };

type KeaState = {
  // environment
  mode: "live" | "fixture";
  conn: Conn;
  topology: TopologyResponse | null;
  scenarios: ScenarioInfo[];
  loadError: string | null;
  // run-scoped (reset on run.started / reset)
  run: RunInfo | null;
  simTs: number;
  health: Record<string, Health>;
  anomalies: Record<string, Anomaly>;
  incident: Incident | null;
  watching: string | null;
  prediction: PredictionState | null;
  verification: PredictionVerification | null;
  investigation: InvestigationState | null;
  timeline: TimelineItem[];
  deployments: RawEvent[];
  // hot path, kept in its own fields so graph selectors never see it change
  metricsLatest: Record<string, MetricPoint>;
  metricCount: number;
  // ui
  selectedService: string | null;
  overlayCandidateId: string | null; // causal path overlay
  blast: BlastRadius | null;
  highlight: string[]; // services highlighted from timeline or evidence hover
  filters: Record<TimelineKind, boolean>;
  tab: Tab;
  // actions
  setEnv: (p: Partial<Pick<KeaState, "mode" | "conn" | "topology" | "scenarios" | "loadError">>) => void;
  applyMessage: (m: WsMessage) => void;
  clearRun: () => void;
  setPreview: (p: Prediction | null) => void;
  beginInvestigation: (investigationId: string) => void;
  selectService: (name: string | null) => void;
  setOverlay: (candidateId: string | null) => void;
  setBlast: (b: BlastRadius | null) => void;
  setHighlight: (services: string[]) => void;
  toggleFilter: (k: TimelineKind) => void;
  setTab: (t: Tab) => void;
};

/** Recover applies to an open incident, not to a publisher still running: a scripted run can finish
 * (at 10x within seconds) while the system is still failing, and recovery must stay available. */
export const selectCanRecover = (s: KeaState): boolean =>
  s.mode === "live" && s.run !== null && s.incident?.state === "open";

const MAX_TIMELINE = 400;
const RUN_SCOPED = {
  simTs: 0,
  health: {} as Record<string, Health>,
  anomalies: {} as Record<string, Anomaly>,
  incident: null as Incident | null,
  watching: null as string | null,
  prediction: null as PredictionState | null,
  verification: null as PredictionVerification | null,
  investigation: null as InvestigationState | null,
  timeline: [] as TimelineItem[],
  deployments: [] as RawEvent[],
  metricsLatest: {} as Record<string, MetricPoint>,
  metricCount: 0,
  selectedService: null as string | null,
  overlayCandidateId: null as string | null,
  blast: null as BlastRadius | null,
  highlight: [] as string[],
};

let itemSeq = 0;
function item(ts: number, kind: TimelineKind, tone: Tone, statement: string, service?: string): TimelineItem {
  return { id: `t${++itemSeq}`, ts, kind, tone, statement, service };
}

const HEALTH_TONE: Record<Health, Tone> = { healthy: "ok", degraded: "warn", failing: "bad" };

export const useKea = create<KeaState>((set, get) => ({
  mode: "live",
  conn: "connecting",
  topology: null,
  scenarios: [],
  loadError: null,
  run: null,
  ...RUN_SCOPED,
  filters: Object.fromEntries(TIMELINE_KINDS.map((k) => [k, true])) as Record<TimelineKind, boolean>,
  tab: "overview",

  setEnv: (p) => set(p),
  clearRun: () => set({ run: null, ...RUN_SCOPED }),
  setPreview: (p) =>
    set((s) => (s.prediction?.frozen ? s : { prediction: p ? { ...p, frozen: false } : null })),
  beginInvestigation: (investigationId) =>
    set({
      investigation: {
        investigation_id: investigationId,
        status: "running",
        result: null,
        steps: [],
      },
    }),
  selectService: (name) => set({ selectedService: name }),
  setOverlay: (candidateId) => set({ overlayCandidateId: candidateId }),
  setBlast: (blast) => set({ blast }),
  setHighlight: (highlight) => set({ highlight }),
  toggleFilter: (k) => set((s) => ({ filters: { ...s.filters, [k]: !s.filters[k] } })),
  setTab: (tab) => set({ tab }),

  applyMessage: (m) => {
    const s = get();
    const push = (...items: TimelineItem[]) =>
      set({ timeline: [...s.timeline, ...items].slice(-MAX_TIMELINE) });
    switch (m.type) {
      case "snapshot": {
        const r = m.payload.runs.at(-1);
        if (!r) {
          // server has no run (fresh start or restart): drop any stale state we still hold
          if (s.run) set({ run: null, ...RUN_SCOPED });
          return;
        }
        set({
          ...RUN_SCOPED,
          run: { run_id: r.run_id, scenario: r.scenario, seed: r.seed, speed: null, status: r.status },
          simTs: r.sim_ts,
          health: r.health,
          incident: r.incident,
          anomalies: Object.fromEntries((r.incident?.anomalies ?? []).map((a) => [a.anomaly_id, a])),
          prediction: r.prediction ? { ...r.prediction, frozen: true } : null,
          verification: r.verification,
        });
        return;
      }
      case "run.started": {
        const p: RunStarted = m.payload;
        set({
          ...RUN_SCOPED,
          run: {
            run_id: m.run_id ?? "run",
            scenario: p.scenario,
            seed: p.seed,
            speed: p.speed,
            status: "running",
            warmup_end_ts: p.warmup_end_ts,
          },
        });
        return;
      }
      case "run.stopped":
        if (s.run) set({ run: { ...s.run, status: m.payload.status ?? "stopped" } });
        return;
      case "sim.clock":
        set({ simTs: m.payload.sim_ts });
        return;
      case "metrics.batch": {
        const latest = { ...s.metricsLatest };
        for (const p of m.payload) latest[`${p.service}.${p.metric}`] = p;
        set({ metricsLatest: latest, metricCount: s.metricCount + m.payload.length, simTs: m.sim_ts });
        return;
      }
      case "log.batch":
        push(
          ...m.payload.map((e) =>
            item(e.ts, "log", e.payload.level === "ERROR" ? "bad" : e.payload.level === "WARN" ? "warn" : "neutral",
              `${e.service}: ${String(e.payload.message ?? "")}`, e.service),
          ),
        );
        return;
      case "deployment.observed": {
        const e = m.payload;
        const id = String(e.payload.deployment_id ?? "");
        const rollback = e.kind === "rollback";
        set({ deployments: [...s.deployments, e] });
        push(
          item(
            e.ts,
            rollback ? "rollback" : "deployment",
            rollback ? "ok" : "neutral",
            rollback ? `Rollback of ${id} on ${e.service}` : `Deployment ${id} (${String(e.payload.version ?? "")}) on ${e.service}`,
            e.service,
          ),
        );
        return;
      }
      case "anomaly.opened":
      case "anomaly.resolved": {
        const a = m.payload;
        const opened = m.type === "anomaly.opened";
        set({
          anomalies: { ...s.anomalies, [a.anomaly_id]: a },
          watching: opened && !s.incident ? `${a.service}: ${humanizeMetric(a.metric)}` : s.watching,
        });
        push(
          item(
            opened ? a.detected_ts : (a.resolved_ts ?? a.detected_ts),
            "anomaly",
            opened ? "warn" : "ok",
            opened
              ? `${a.service} ${humanizeMetric(a.metric)} reached ${a.ratio.toFixed(1)}x baseline`
              : `${a.service} ${humanizeMetric(a.metric)} back to normal`,
            a.service,
          ),
        );
        return;
      }
      case "service.health":
        set({ health: { ...s.health, [m.payload.service]: m.payload.health } });
        push(item(m.sim_ts, "health", HEALTH_TONE[m.payload.health], `${m.payload.service} is ${m.payload.health}`, m.payload.service));
        return;
      case "incident.opened":
      case "incident.updated":
      case "incident.resolved": {
        const inc = m.payload;
        // stale updates never overwrite newer state
        if (s.incident && s.incident.incident_id === inc.incident_id && inc.revision <= s.incident.revision) return;
        const label =
          m.type === "incident.opened"
            ? `Incident ${inc.incident_id} opened`
            : m.type === "incident.resolved"
              ? `Incident ${inc.incident_id} resolved`
              : `Incident ${inc.incident_id} updated, revision ${inc.revision}`;
        set({
          incident: inc,
          watching: null,
          anomalies: { ...s.anomalies, ...Object.fromEntries(inc.anomalies.map((a) => [a.anomaly_id, a])) },
          run: s.run && m.type === "incident.resolved" ? { ...s.run, status: "resolved" } : s.run,
        });
        // updates arrive in bursts as anomalies join; only opened and resolved are timeline-worthy
        if (m.type !== "incident.updated") push(item(m.sim_ts, "incident", m.type === "incident.resolved" ? "ok" : "bad", label));
        return;
      }
      case "prediction.made":
        set({ prediction: { ...m.payload, frozen: true }, verification: null });
        push(item(m.sim_ts, "prediction", "neutral", `Prediction recorded for ${m.payload.candidate_id}`));
        return;
      case "prediction.verified":
        set({ verification: m.payload });
        push(item(m.sim_ts, "prediction", m.payload.verdict === "confirmed" ? "ok" : "warn", `Prediction ${m.payload.verdict}`));
        return;
      case "agent.step": {
        const step = m.payload as AgentTrace & { investigation_id: string };
        const current = s.investigation;
        set({
          investigation: {
            investigation_id: step.investigation_id,
            status: "running",
            result: current?.result ?? null,
            steps: [...(current?.steps ?? []), step],
          },
        });
        return;
      }
      case "agent.done": {
        if (!("mode" in m.payload)) {
          set({
            investigation: {
              investigation_id: m.payload.investigation_id,
              status: "failed",
              result: null,
              steps: s.investigation?.steps ?? [],
              error: m.payload.error,
            },
          });
          return;
        }
        set({
          investigation: {
            investigation_id: m.payload.investigation_id,
            status: "completed",
            result: m.payload,
            steps: m.payload.trace,
          },
        });
        return;
      }
    }
  },
}));
