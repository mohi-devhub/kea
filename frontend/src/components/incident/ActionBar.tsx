"use client";

import { ArrowUUpLeft, Graph, MagnifyingGlass, Path } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui";
import { errorText, loadBlast, recoverRun } from "@/lib/session";
import { useKea } from "@/lib/store";

/** Incident actions. Each one states why it is disabled instead of silently doing nothing. */
export function ActionBar() {
  const incident = useKea((s) => s.incident);
  const run = useKea((s) => s.run);
  const mode = useKea((s) => s.mode);
  const overlay = useKea((s) => s.overlayCandidateId);
  const setOverlay = useKea((s) => s.setOverlay);
  const blast = useKea((s) => s.blast);
  const setBlast = useKea((s) => s.setBlast);
  const [busy, setBusy] = useState<"blast" | "recover" | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!incident) return null;
  const top = incident.candidates[0];
  const pathOn = top !== undefined && overlay === top.candidate_id;
  const canRecover = run?.status === "running" && mode === "live";
  const recoverWhy =
    mode === "fixture"
      ? "Fixture replay plays the recovery by itself."
      : run?.status !== "running"
        ? "Recover is available while a run is in progress."
        : undefined;

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

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!top} aria-pressed={pathOn} onClick={() => top && setOverlay(pathOn ? null : top.candidate_id)}>
          <Path size={14} weight="bold" aria-hidden /> {pathOn ? "Hide causal path" : "Show causal path"}
        </Button>
        <Button busy={busy === "blast"} onClick={() => act("blast", blast ? async () => setBlast(null) : loadBlast)}>
          <Graph size={14} weight="bold" aria-hidden /> {blast ? "Clear blast radius" : "Blast radius"}
        </Button>
        <Button busy={busy === "recover"} disabled={!canRecover} title={recoverWhy} onClick={() => act("recover", recoverRun)}>
          <ArrowUUpLeft size={14} weight="bold" aria-hidden /> Recover
        </Button>
        <Button disabled title="The investigation agent is not enabled in this build.">
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
