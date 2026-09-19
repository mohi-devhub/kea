"use client";

import { ArrowUUpLeft, Graph, MagnifyingGlass, Path } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";
import { errorText, loadBlast, recoverRun } from "@/lib/session";
import { selectCanRecover, useKea } from "@/lib/store";

/** Incident actions. Each one states why it is disabled instead of silently doing nothing. */
export function ActionBar() {
  const incident = useKea((s) => s.incident);
  const canRecover = useKea(selectCanRecover);
  const mode = useKea((s) => s.mode);
  const overlay = useKea((s) => s.overlayCandidateId);
  const setOverlay = useKea((s) => s.setOverlay);
  const blast = useKea((s) => s.blast);
  const setBlast = useKea((s) => s.setBlast);
  const setTab = useKea((s) => s.setTab);
  const beginInvestigation = useKea((s) => s.beginInvestigation);
  const [busy, setBusy] = useState<"blast" | "recover" | "investigate" | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!incident) return null;
  const top = incident.candidates[0];
  const pathOn = top !== undefined && overlay === top.candidate_id;
  const recoverWhy =
    mode === "fixture"
      ? "Fixture replay plays the recovery by itself."
      : canRecover
        ? undefined
        : "This incident is already resolved.";

  const act = async (name: "blast" | "recover", fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(name);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const investigate = async () => {
    if (busy || mode === "fixture") return;
    setBusy("investigate");
    setError(null);
    try {
      const started = await api.investigate(incident.incident_id);
      beginInvestigation(started.investigation_id);
      setTab("investigate");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <div className="grid grid-cols-2 gap-2">
        <Button disabled={!top} aria-pressed={pathOn} onClick={() => top && setOverlay(pathOn ? null : top.candidate_id)}>
          <Path size={14} weight="bold" aria-hidden /> {pathOn ? "Hide causal path" : "Show causal path"}
        </Button>
        <Button busy={busy === "blast"} onClick={() => act("blast", blast ? async () => setBlast(null) : loadBlast)}>
          <Graph size={14} weight="bold" aria-hidden /> {blast ? "Clear blast radius" : "Blast radius"}
        </Button>
        <Button variant="primary" busy={busy === "recover"} disabled={!canRecover} title={recoverWhy} onClick={() => act("recover", recoverRun)}>
          <ArrowUUpLeft size={14} weight="bold" aria-hidden /> Recover
        </Button>
        <Button
          busy={busy === "investigate"}
          disabled={mode === "fixture"}
          title={mode === "fixture" ? "Investigation needs the live API" : "Run the evidence-backed investigation"}
          onClick={investigate}
        >
          <MagnifyingGlass size={14} weight="bold" aria-hidden /> Investigate
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-[12px] text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
