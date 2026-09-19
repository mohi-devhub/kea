"use client";

import { Clock, Graph, Target, WarningCircle } from "@phosphor-icons/react";
import { StatCard } from "@/components/ui";
import { useKea } from "@/lib/store";

/** Four headline numbers above the working area (the reference's stat cards). */
export function StatRow() {
  const incident = useKea((s) => s.incident);
  const health = useKea((s) => s.health);
  const total = useKea((s) => s.topology?.services.length ?? 0);
  const run = useKea((s) => s.run);

  const unhealthy = Object.values(health).filter((h) => h !== "healthy").length;
  const affected = incident ? incident.blast_radius.services.length : unhealthy;
  const facing = incident?.blast_radius.customer_facing_affected.length ?? 0;
  const top = incident?.candidates[0];
  const detect = incident ? Math.max(0, Math.round((incident.opened_ts - incident.first_anomaly_ts) / 1000)) : null;

  const state = !run ? "No run" : !incident ? "Healthy" : incident.state === "open" ? "Open" : "Resolved";
  const stateCaption = !run
    ? "Pick a scenario and press Start"
    : !incident
      ? "No incident opened"
      : `${incident.incident_id}, revision ${incident.revision}`;

  return (
    <div className="grid grid-cols-4 gap-4">
      <StatCard label="Incident" value={state} caption={stateCaption} icon={<WarningCircle size={16} weight="bold" aria-hidden />} />
      <StatCard
        label="Services affected"
        value={
          <>
            {affected}
            <span className="text-[15px] font-normal text-text-3">/{total || 8}</span>
          </>
        }
        caption={incident ? `${facing} customer-facing` : "Across the dependency graph"}
        progress={total ? affected / total : 0}
        icon={<Graph size={16} weight="bold" aria-hidden />}
      />
      <StatCard
        label="Top hypothesis"
        value={top ? top.score.toFixed(2) : "None"}
        caption={top ? (top.kind === "deployment" ? `Deployment ${top.deployment_id} on ${top.service}` : `Service fault: ${top.service}`) : "Heuristic score, not a probability"}
        progress={top?.score}
        icon={<Target size={16} weight="bold" aria-hidden />}
      />
      <StatCard
        label="Time to detect"
        value={detect === null ? "None" : `${detect}s`}
        caption={detect === null ? "First anomaly to incident" : "From first anomaly to incident open"}
        icon={<Clock size={16} weight="bold" aria-hidden />}
      />
    </div>
  );
}
