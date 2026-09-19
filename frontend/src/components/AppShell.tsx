"use client";

import { useEffect } from "react";
import { Sidebar } from "@/components/Sidebar";
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

/** Sidebar plus a content column. The session (live socket or fixture player) lives here so it
 * survives navigation between Overview, Timeline and Eval. */
export function AppShell({ children }: { children: React.ReactNode }) {
  useEffect(() => initSession(), []);
  return (
    <div className="flex h-dvh">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Banners />
        {children}
      </div>
    </div>
  );
}
