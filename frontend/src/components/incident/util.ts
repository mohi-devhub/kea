import type { Candidate } from "@/lib/types";

/** Fixed factor order: it maps to the validated series colors --f1..--f4 and must never change. */
export const FACTOR_ORDER = [
  "temporal",
  "dependency_consistency",
  "anomaly_strength",
  "downstream_impact",
] as const;

export type FactorKey = (typeof FACTOR_ORDER)[number];

export const FACTOR_COLOR: Record<FactorKey, string> = {
  temporal: "var(--f1)",
  dependency_consistency: "var(--f2)",
  anomaly_strength: "var(--f3)",
  downstream_impact: "var(--f4)",
};

export const fixed = (n: number, digits = 2) => n.toFixed(digits);

export function candidateLabel(c: Pick<Candidate, "kind" | "deployment_id" | "service">): string {
  return c.kind === "deployment" ? `Deployment ${c.deployment_id ?? ""} on ${c.service}` : `Service fault: ${c.service}`;
}

/** "deployment:dep-182" -> "Deployment dep-182", "service_fault:postgres" -> "Service fault: postgres". */
export function labelFromCandidateId(id: string): string {
  const [kind, ref] = id.split(":");
  return kind === "deployment" ? `Deployment ${ref}` : `Service fault: ${ref}`;
}

export const VIA_TEXT: Record<string, string> = {
  change: "change",
  self: "same service",
  fault: "failing dependency",
  load: "added load",
};
