"use client";

import { useEffect } from "react";
import { Header } from "@/components/Header";
import { IncidentPanel } from "@/components/incident/IncidentPanel";
import { TopologyGraph } from "@/components/graph/TopologyGraph";
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
        <div role="status" className="border-b border-line bg-warn-bg px-4 py-1 text-[12px] font-medium text-warn">
          FIXTURE REPLAY: recorded data played back, not a live run.
        </div>
      )}
      {mode === "live" && (conn === "reconnecting" || loadError) && (
        <div role="status" className="border-b border-line bg-bad-bg px-4 py-1 text-[12px] font-medium text-bad">
          {loadError ?? "Can't reach the backend. Retrying..."}
        </div>
      )}
    </>
  );
}

export function Dashboard() {
  useEffect(() => initSession(), []);
  return (
    <div className="flex h-dvh flex-col">
      <Header />
      <Banners />
      <main className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_480px] gap-3 p-3">
        <div className="grid min-h-0 grid-rows-[minmax(0,1fr)_240px] gap-3">
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
      </main>
    </div>
  );
}
