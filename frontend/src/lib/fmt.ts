/** Simulated time is epoch ms; show it as UTC clock time. */
export function clock(ts: number): string {
  return new Date(ts).toISOString().slice(11, 19);
}

export function seconds(ms: number): string {
  return `${Math.round(ms / 1000)}s`;
}

export function score(value: number): string {
  return value.toFixed(2);
}

export function humanizeMetric(metric: string): string {
  return metric
    .replace("network_delay_ms", "network delay")
    .replace("packet_loss_pct", "packet loss")
    .replace("cpu_pct", "cpu")
    .replace(/_p95_ms$/, "")
    .replace(/_pct$/, "")
    .replace(/_/g, " ");
}

export const REASON_TEXT: Record<string, string> = {
  NO_ANOMALY_ON_SERVICE_OR_REACHABLE: "no dependency path to the affected services",
  ANOMALY_EXPLAINED_BY_EARLIER_CAUSE: "the anomalies near it are explained by an earlier cause",
  OUTSIDE_LOOKBACK_WINDOW: "the nearby anomalies began outside the lookback window",
  ANOMALY_PRECEDES_DEPLOYMENT: "the nearby anomalies began before it",
};

export const FACTOR_LABEL: Record<string, string> = {
  temporal: "Timing",
  dependency_consistency: "Explains incident",
  anomaly_strength: "Signal strength",
  downstream_impact: "Customer impact",
};
