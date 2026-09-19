"use client";

import { IncidentPanel } from "@/components/incident/IncidentPanel";
import { TopologyGraph } from "@/components/graph/TopologyGraph";
import { StatRow } from "@/components/StatRow";
import { Panel } from "@/components/ui";

export function Dashboard() {
  return (
    <main className="flex min-h-0 flex-1 flex-col gap-3 px-6 pb-6 pt-5">
      <header className="text-center">
        <h1 className="text-[28px] font-light leading-tight tracking-[-0.02em] text-text">Overview</h1>
        <p className="mt-0.5 text-[14px] text-text-2">Watch a simulated incident from first anomaly to root cause.</p>
      </header>
      <StatRow />
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_380px] gap-4">
        <Panel label="Topology" className="min-h-0 overflow-hidden">
          <TopologyGraph />
        </Panel>
        <Panel label="Incident" className="min-h-0 overflow-hidden">
          <IncidentPanel />
        </Panel>
      </div>
    </main>
  );
}
