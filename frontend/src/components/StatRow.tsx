"use client";

import { Graph, WarningCircle } from "@phosphor-icons/react";
import { Panel } from "@/components/ui";
import { useKea } from "@/lib/store";

function Chip({ icon, label, value, caption }: { icon: React.ReactNode; label: string; value: React.ReactNode; caption: string }) {
  return (
    <Panel className="flex min-w-0 items-center gap-3 px-3.5 py-2">
      <span className="text-text-3">{icon}</span>
      <span className="text-[12px] text-text-3">{label}</span>
      <span className="tnum text-[15px] font-medium text-text">{value}</span>
      <span className="min-w-0 truncate text-[12px] text-text-3">{caption}</span>
    </Panel>
  );
}

/** Two slim status chips; the working area below keeps all the vertical space. */
export function StatRow() {
  const incident = useKea((s) => s.incident);
  const health = useKea((s) => s.health);
  const total = useKea((s) => s.topology?.services.length ?? 8);
  const run = useKea((s) => s.run);

  const unhealthy = Object.values(health).filter((h) => h !== "healthy").length;
  const affected = incident ? incident.blast_radius.services.length : unhealthy;
  const facing = incident?.blast_radius.customer_facing_affected.length ?? 0;

  const state = !run ? "No run" : !incident ? "Healthy" : incident.state === "open" ? "Open" : "Resolved";
  const caption = !run ? "Pick a scenario and press Start" : !incident ? "No incident opened" : `${incident.incident_id}, revision ${incident.revision}`;

  return (
    <div className="grid grid-cols-2 gap-4">
      <Chip icon={<WarningCircle size={16} weight="bold" aria-hidden />} label="Incident" value={state} caption={caption} />
      <Chip
        icon={<Graph size={16} weight="bold" aria-hidden />}
        label="Services affected"
        value={
          <>
            {affected}
            <span className="font-normal text-text-3">/{total}</span>
          </>
        }
        caption={incident ? `${facing} customer-facing` : "Across the dependency graph"}
      />
    </div>
  );
}
