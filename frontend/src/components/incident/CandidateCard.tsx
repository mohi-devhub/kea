"use client";

import { CaretDown, CaretRight } from "@phosphor-icons/react";
import { useState } from "react";
import { Badge } from "@/components/ui";
import { clock } from "@/lib/fmt";
import { useKea } from "@/lib/store";
import type { Candidate, Evidence } from "@/lib/types";
import { FactorBar } from "./FactorBar";
import { candidateLabel, fixed, VIA_TEXT } from "./util";

/** One ranked hypothesis. The header selects it (drives the causal-path overlay); the caret expands the chain. */
export function CandidateCard({
  candidate,
  evidence,
  margin,
}: {
  candidate: Candidate;
  evidence: Evidence[];
  margin: number | null;
}) {
  const [open, setOpen] = useState(false);
  const overlay = useKea((s) => s.overlayCandidateId);
  const setOverlay = useKea((s) => s.setOverlay);
  const setHighlight = useKea((s) => s.setHighlight);
  const selectService = useKea((s) => s.selectService);
  const selected = overlay === candidate.candidate_id;
  const linked = evidence.filter((e) => candidate.evidence_ids.includes(e.evidence_id));
  const panelId = `chain-${candidate.candidate_id.replace(/[^a-z0-9]/gi, "-")}`;

  const highlightFor = (e: Evidence) => {
    const svc = e.data?.service;
    setHighlight(typeof svc === "string" ? [svc] : []);
  };

  return (
    <article
      className={`rounded-lg border bg-surface p-3.5 transition-colors duration-150 ${selected ? "border-accent ring-1 ring-accent/30" : "border-line"}`}
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          aria-pressed={selected}
          onClick={() => {
            setOverlay(selected ? null : candidate.candidate_id);
            selectService(selected ? null : candidate.service);
          }}
          className="pressable flex min-w-0 flex-1 items-start gap-3 rounded-control text-left"
        >
          <span className="num mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-surface-2 text-[12px] text-text-2">
            {candidate.rank}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[14px] font-medium leading-6 text-text">{candidateLabel(candidate)}</span>
            {candidate.rank === 1 && margin !== null && (
              <span className="num block text-[12px] text-text-3">margin over runner-up {fixed(margin)}</span>
            )}
          </span>
          <span className="shrink-0 text-right">
            <span className="num block text-[24px] font-medium leading-none tracking-tight text-text">
              {fixed(candidate.score)}
            </span>
            <span className="mt-1 block text-[11px] text-text-3">score</span>
          </span>
        </button>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          aria-label={open ? "Hide causal chain" : "Show causal chain"}
          onClick={() => setOpen((v) => !v)}
          className="pressable mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-text-3 [@media(hover:hover)]:hover:bg-surface-2 [@media(hover:hover)]:hover:text-text"
        >
          {open ? <CaretDown size={14} weight="bold" /> : <CaretRight size={14} weight="bold" />}
        </button>
      </div>

      <div className="mt-4">
        <FactorBar candidate={candidate} />
      </div>

      {open && (
        <div id={panelId} className="mt-4 space-y-4 border-t border-line pt-4">
          <div>
            <h4 className="mb-2 text-[12px] font-medium text-text-3">Causal chain</h4>
            <ol className="space-y-2">
              {candidate.chain.map((step) => (
                <li key={step.step} className="grid grid-cols-[20px_minmax(0,1fr)] gap-x-2 text-[13px]">
                  <span className="num pt-px text-[12px] text-text-3">{step.step}</span>
                  <span className="min-w-0">
                    <span className="text-text">{step.statement}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="num text-[11px] text-text-3">{clock(step.ts)}</span>
                      <span className="num rounded-md border border-line px-1.5 py-px text-[11px] text-text-2">{step.service}</span>
                      <Badge>{VIA_TEXT[step.via] ?? step.via}</Badge>
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
          <div>
            <h4 className="mb-2 text-[12px] font-medium text-text-3">Evidence</h4>
            {linked.length === 0 ? (
              <p className="text-[12px] text-text-3">No evidence items are linked to this candidate.</p>
            ) : (
              <ul className="space-y-2">
                {linked.map((e) => (
                  <li key={e.evidence_id} className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-2.5">
                    <button
                      type="button"
                      onPointerEnter={() => highlightFor(e)}
                      onPointerLeave={() => setHighlight([])}
                      onFocus={() => highlightFor(e)}
                      onBlur={() => setHighlight([])}
                      className="pressable num rounded-md border border-line bg-surface-2 px-1.5 py-0.5 text-[11px] text-text-2 [@media(hover:hover)]:hover:text-text"
                    >
                      {e.evidence_id}
                    </button>
                    <span className="text-[12px] text-text-2">{e.statement}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
