"use client";

import type { ReactNode } from "react";
import { EmptyState } from "@/components/ui";
import { useKea } from "@/lib/store";
import { ActionBar } from "./ActionBar";
import { BlastRadiusSection } from "./BlastRadiusSection";
import { CandidateCard } from "./CandidateCard";
import { IncidentHeader } from "./IncidentHeader";
import { PredictionCard } from "./PredictionCard";
import { RejectedList } from "./RejectedList";
import { WhatChanged } from "./WhatChanged";

function Divided({ children }: { children: ReactNode }) {
  return <div className="border-t border-line pt-4">{children}</div>;
}

export function OverviewTab() {
  const run = useKea((s) => s.run);
  const incident = useKea((s) => s.incident);
  const watching = useKea((s) => s.watching);

  if (!run) return <EmptyState>Pick a scenario and press Start.</EmptyState>;
  if (!incident) {
    return (
      <div role="status">
        <EmptyState>{watching ? `Watching ${watching} (needs corroboration)` : "All systems healthy"}</EmptyState>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <IncidentHeader incident={incident} />
      <WhatChanged data={incident.what_changed} />
      <Divided>
        <section aria-labelledby="candidates-heading">
          <h3 id="candidates-heading" className="mb-2 text-[12px] font-medium text-text-3">
            Ranked candidates
          </h3>
          {incident.candidates.length === 0 ? (
            <p className="text-[13px] text-text-2">No root-cause candidate has been found yet.</p>
          ) : (
            <div className="space-y-3">
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
          <p className="mt-2 text-[12px] text-text-3">Heuristic score, not a probability.</p>
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
