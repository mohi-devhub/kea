"use client";

import { useEffect } from "react";
import { IncidentPanel } from "@/components/incident/IncidentPanel";
import { TopologyGraph } from "@/components/graph/TopologyGraph";
import { StatRow } from "@/components/StatRow";
import { Timeline } from "@/components/timeline/Timeline";
import { Panel } from "@/components/ui";
import { initSession } from "@/lib/session";
import { useKea } from "@/lib/store";

function Banners() {
  const mode = useKea((s) => s.mode);
  const conn = useKea((s) => s.conn);
  const loadError = useKea((s) => s.loadError);
  return (
    <>
      {mode === "fixture" && (
        <div role="status" className="border-b border-line bg-warn-bg px-6 py-1.5 text-[12px] font-medium text-warn">
          FIXTURE REPLAY: recorded data played back, not a live run.
        </div>
      )}
      {mode === "live" && (conn === "reconnecting" || loadError) && (
        <div role="status" className="border-b border-line bg-bad-bg px-6 py-1.5 text-[12px] font-medium text-bad">
          {loadError ?? "Can't reach the backend. Retrying..."}
        </div>
      )}
    </>
  );
}

export function Dashboard() {
  useEffect(() => initSession(), []);
  return (
    <>
      <Banners />
      <main className="flex min-h-0 flex-1 flex-col gap-4 px-6 pb-6 pt-5">
        <header className="text-center">
          <h1 className="text-[30px] font-light leading-tight tracking-[-0.02em] text-text">Overview</h1>
          <p className="mt-1 text-[14px] text-text-2">Watch a simulated incident from first anomaly to root cause.</p>
        </header>
        <StatRow />
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_440px] gap-4">
          <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_220px] gap-4">
            <Panel label="Topology" className="min-h-0 overflow-hidden">
              <TopologyGraph />
            </Panel>
            <Panel label="Timeline" className="min-h-0 overflow-hidden">
              <Timeline />
            </Panel>
          </div>
          <Panel label="Incident" className="min-h-0 overflow-hidden">
            <IncidentPanel />
          </Panel>
        </div>
      </main>
    </>
  );
}
