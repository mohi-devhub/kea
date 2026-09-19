"use client";

import { CaretRight, WarningCircle } from "@phosphor-icons/react";
import { Badge, type BadgeTone, EmptyState, SectionLabel, Skeleton } from "@/components/ui";
import { useKea } from "@/lib/store";
import type { AgentTrace, InvestigationResult } from "@/lib/types";

const MODE_TONE: Record<InvestigationResult["mode"], BadgeTone> = { LIVE: "accent", REPLAYED: "warn", TEMPLATE: "neutral" };

/** Evidence chip: hovering or focusing it highlights the service the evidence is about. */
function EvidenceChip({ id, service }: { id: string; service?: string }) {
  const setHighlight = useKea((s) => s.setHighlight);
  const on = () => service && setHighlight([service]);
  const off = () => setHighlight([]);
  return (
    <button
      type="button"
      onMouseEnter={on}
      onMouseLeave={off}
      onFocus={on}
      onBlur={off}
      title={service ? `Evidence about ${service}` : "Evidence"}
      className="num pressable rounded-md border border-line-strong bg-surface px-1.5 py-0.5 text-[11px] text-text-2 [@media(hover:hover)]:hover:border-accent [@media(hover:hover)]:hover:text-accent"
    >
      {id}
    </button>
  );
}

function TraceList({ steps, live }: { steps: AgentTrace[]; live?: boolean }) {
  if (!steps.length) return <p className="text-[12px] text-text-3">No trace steps recorded yet.</p>;
  return (
    <ol className="divide-y divide-line">
      {steps.map((step, i) => (
        <li key={`${step.step}-${step.name}-${i}`} className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-baseline gap-x-2 py-1.5 text-[12px]">
          <span className="num text-text-3">{step.step}</span>
          <span className="min-w-0">
            <span className="font-medium text-text">{step.name}</span>
            {step.result_summary && (
              <span className="block truncate text-text-3" title={step.result_summary}>
                {step.result_summary}
              </span>
            )}
          </span>
          <span className={live && i === steps.length - 1 ? "num text-accent" : "num text-text-3"}>{step.duration_ms}ms</span>
        </li>
      ))}
    </ol>
  );
}

export function InvestigateTab() {
  const incident = useKea((s) => s.incident);
  const investigation = useKea((s) => s.investigation);

  if (!incident) return <EmptyState>Start a run to investigate an incident.</EmptyState>;
  if (!investigation) {
    return <EmptyState>No investigation yet. Use Investigate in the Overview tab to explain this incident from its evidence.</EmptyState>;
  }
  if (investigation.status === "running") {
    return (
      <div className="space-y-4" role="status" aria-live="polite">
        <div className="flex items-center gap-2">
          <Badge tone="accent">Investigating</Badge>
          <span className="text-[13px] text-text-2">Reading the incident evidence.</span>
        </div>
        {investigation.steps.length ? <TraceList steps={investigation.steps} live /> : <Skeleton className="h-16 w-full" />}
      </div>
    );
  }
  if (!investigation.result) {
    return (
      <div role="alert" className="flex items-start gap-2 rounded-control bg-bad-bg px-3 py-2 text-[13px] text-bad">
        <WarningCircle size={16} weight="bold" aria-hidden className="mt-0.5 shrink-0" />
        {investigation.error ?? "The investigation failed."}
      </div>
    );
  }

  const result = investigation.result;
  const serviceOf = new Map(result.evidence.map((e) => [e.evidence_id, (e.data as { service?: string }).service]));
  const reason = result.disagreement ? String((result.disagreement as { reason?: unknown }).reason ?? "") : "";

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <SectionLabel>Investigation</SectionLabel>
        <div className="flex items-center gap-1.5">
          <Badge tone={MODE_TONE[result.mode]}>{result.mode}</Badge>
          <span className="num text-[11px] text-text-3">{result.provider === "template" ? "template" : `${result.provider} / ${result.model}`}</span>
        </div>
      </div>

      {result.mode === "TEMPLATE" && (
        <p className="-mt-2 text-[12px] text-text-3">Explanation generated from the incident evidence (template mode). No language model was used.</p>
      )}
      <p className="text-[14px] leading-relaxed text-text">{result.summary}</p>

      {result.disagreement && (
        <div role="note" className="flex gap-2 rounded-control bg-warn-bg px-3 py-2 text-[13px] text-warn">
          <WarningCircle size={16} weight="bold" aria-hidden className="mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">The agent flagged a concern about the top candidate.</p>
            {reason && <p className="mt-0.5 text-[12px]">{reason}</p>}
            <p className="mt-0.5 text-[12px]">The ranking shown elsewhere is unchanged.</p>
          </div>
        </div>
      )}

      <section className="space-y-1">
        <SectionLabel>Causal narrative</SectionLabel>
        <ol className="divide-y divide-line">
          {result.narrative_steps.map((step, i) => (
            <li key={`${i}-${step.text}`} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-x-2 py-2.5">
              <span className="num pt-0.5 text-[12px] text-text-3">{i + 1}</span>
              <div>
                <p className="text-[13px] leading-relaxed text-text">{step.text}</p>
                {step.evidence_ids.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {step.evidence_ids.map((id) => (
                      <EvidenceChip key={id} id={id} service={serviceOf.get(id)} />
                    ))}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      </section>

      {result.caveats.length > 0 && (
        <section className="space-y-1.5">
          <SectionLabel>Caveats</SectionLabel>
          <ul className="list-disc space-y-1 pl-5 text-[12px] text-text-2">
            {result.caveats.map((caveat) => (
              <li key={caveat}>{caveat}</li>
            ))}
          </ul>
        </section>
      )}

      <details className="group border-t border-line pt-3">
        <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] font-medium text-text-3 [@media(hover:hover)]:hover:text-text">
          <CaretRight size={12} weight="bold" aria-hidden className="transition-transform duration-150 group-open:rotate-90" />
          Trace, {result.trace.length} {result.trace.length === 1 ? "step" : "steps"}
        </summary>
        <div className="pt-2">
          <TraceList steps={result.trace} />
        </div>
      </details>
    </div>
  );
}
