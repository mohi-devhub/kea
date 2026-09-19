"use client";

import { WarningCircle } from "@phosphor-icons/react";
import { Badge, CardHeader, EmptyState, Segmented } from "@/components/ui";
import { type Tab, useKea } from "@/lib/store";
import { InvestigateTab } from "./InvestigateTab";
import { OverviewTab } from "./OverviewTab";

const TABS: { value: Tab; label: string }[] = [
  { value: "overview", label: "Overview" },
  { value: "investigate", label: "Investigate" },
  { value: "fix", label: "Fix" },
];

/** Incident card: header with id and state, segmented tabs, and a body that scrolls inside itself. */
export function IncidentPanel() {
  const tab = useKea((s) => s.tab);
  const setTab = useKea((s) => s.setTab);
  const incident = useKea((s) => s.incident);
  const resolved = incident?.state === "resolved";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-line pb-3">
        <CardHeader
          icon={<WarningCircle size={20} weight="bold" />}
          title="Incident"
          right={
            incident ? (
              <>
                <span className="num text-[13px] text-text">{incident.incident_id}</span>
                <Badge tone={resolved ? "ok" : "bad"}>{incident.state}</Badge>
              </>
            ) : undefined
          }
        />
        <div className="px-4 pt-3">
          <Segmented label="Incident views" value={tab} options={TABS} onChange={setTab} />
        </div>
      </div>
      <div role="tabpanel" aria-label={`${tab} tab`} tabIndex={0} className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {tab === "overview" && <OverviewTab />}
        {tab === "investigate" && <InvestigateTab />}
        {tab === "fix" && <EmptyState>No fix proposal available yet.</EmptyState>}
      </div>
    </div>
  );
}
