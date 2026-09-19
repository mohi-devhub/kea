"use client";

import { Eye, Graph } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { IconTile, SectionLabel } from "@/components/ui";
import { useKea } from "@/lib/store";
import { ActionBar } from "./ActionBar";
import { BlastRadiusSection } from "./BlastRadiusSection";
import { CandidateCard } from "./CandidateCard";
import { IncidentHeader } from "./IncidentHeader";
import { PredictionCard } from "./PredictionCard";
import { RejectedList } from "./RejectedList";
import { WhatChanged } from "./WhatChanged";

function Divided({ children }: { children: ReactNode }) {
  return <div className="border-t border-line pt-5">{children}</div>;
}

/** A composed empty state: icon tile, a short title, one sentence on what to do next. */
function Empty({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div role="status" className="flex flex-col items-center px-6 py-14 text-center">
      <IconTile>{icon}</IconTile>
      <p className="mt-4 text-[15px] font-medium text-text">{title}</p>
      <p className="mt-1 max-w-[280px] text-[13px] leading-snug text-text-3">{children}</p>
    </div>
  );
}

export function OverviewTab() {
  const run = useKea((s) => s.run);
  const incident = useKea((s) => s.incident);
  const watching = useKea((s) => s.watching);

  if (!run) {
    return (
      <Empty icon={<Graph size={18} weight="bold" />} title="No run yet">
        Pick a scenario and press Start.
      </Empty>
    );
  }
  if (!incident) {
    return watching ? (
      <Empty icon={<Eye size={18} weight="bold" />} title="Watching">
        {`Watching ${watching} (needs corroboration)`}
      </Empty>
    ) : (
      <Empty icon={<Graph size={18} weight="bold" />} title="All systems healthy">
        No incident has opened. It appears here as soon as anomalies line up.
      </Empty>
    );
  }

  return (
    <div className="space-y-5">
      <IncidentHeader incident={incident} />
      <WhatChanged data={incident.what_changed} />
      <Divided>
        <section aria-labelledby="candidates-heading">
          <div id="candidates-heading">
            <SectionLabel>Ranked candidates</SectionLabel>
          </div>
          {incident.candidates.length === 0 ? (
            <p className="mt-2 text-[13px] text-text-2">No root-cause candidate has been found yet.</p>
          ) : (
            <div className="mt-2.5 space-y-3">
              {incident.candidates.map((c) => (
                <CandidateCard
                  key={c.candidate_id}
                  candidate={c}
                  evidence={incident.evidence}
                  margin={c.rank === 1 && incident.candidates.length > 1 ? incident.margin : null}
                />
              ))}
            </div>
          )}
          <p className="mt-3 text-[12px] text-text-3">Heuristic score, not a probability.</p>
        </section>
      </Divided>
      {incident.rejected_candidates.length > 0 && (
        <Divided>
          <RejectedList items={incident.rejected_candidates} />
        </Divided>
      )}
      <Divided>
        <BlastRadiusSection incident={incident} />
      </Divided>
      <PredictionSlot />
      <Divided>
        <ActionBar />
      </Divided>
    </div>
  );
}

function PredictionSlot() {
  const prediction = useKea((s) => s.prediction);
  if (!prediction) return null;
  return (
    <Divided>
      <PredictionCard />
    </Divided>
  );
}
