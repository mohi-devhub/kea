"use client";

import { CaretRight, CheckCircle, Code, WarningCircle, XCircle } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import { Badge, type BadgeTone, Button, IconTile, SectionLabel, Segmented, Skeleton, cx } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { FIXTURE_MODE } from "@/lib/config";
import { errorText } from "@/lib/session";
import { useKea } from "@/lib/store";
import type { FixProposal, FixState, FixTraceEntry, TestRun } from "@/lib/types";
import { DiffView } from "./DiffView";
import { EvidenceChip } from "./InvestigateTab";

const POLL_MS = 1500;
const APPROVER = "local-user";
const ACTIVE: FixState[] = ["queued", "generating"];

const STATE_TONE: Record<FixState, BadgeTone> = {
  queued: "neutral",
  generating: "accent",
  proposed: "accent",
  approved: "ok",
  rejected: "neutral",
  superseded: "neutral",
  failed: "bad",
};
const MODE_TONE: Record<string, BadgeTone> = { LIVE: "accent", REPLAYED: "warn", TEMPLATE: "neutral" };

/** The first 12 hex characters of `sha256:<hex>`, enough to read out loud and compare. */
function shortHash(hash: string | null): string {
  if (!hash) return "not computed";
  return hash.replace(/^sha256:/, "").slice(0, 12);
}

/** The server reason repeats "Not enabled in this build"; drop that prefix so the card reads once. */
function applyReason(reason: string): string {
  const rest = reason.replace(/^not enabled in this build:\s*/i, "");
  return rest.charAt(0).toUpperCase() + rest.slice(1);
}

function utc(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${d.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

const FUTURE_STEPS = [
  "Create a branch from the base commit.",
  "Commit the exact approved diff.",
  "Draft a pull request (a local patch file first, then a GitHub draft PR).",
];

function Note({ children }: { children: React.ReactNode }) {
  return <p className="text-[12px] leading-relaxed text-text-3">{children}</p>;
}

function FutureList() {
  return (
    <div className="space-y-1">
      <SectionLabel>Future expansion</SectionLabel>
      <ul className="list-disc space-y-0.5 pl-5 text-[12px] text-text-3">
        {FUTURE_STEPS.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ul>
    </div>
  );
}

function Box({ children, className, tone }: { children: React.ReactNode; className?: string; tone?: "ok" | "warn" }) {
  const look = tone === "ok" ? "border-transparent bg-ok-bg" : tone === "warn" ? "border-transparent bg-warn-bg" : "border-line bg-surface";
  return <div className={cx("rounded-control border p-3", look, className)}>{children}</div>;
}

function HeaderRow({ proposal }: { proposal: FixProposal }) {
  const model = proposal.provider
    ? proposal.provider === "template"
      ? "template"
      : `${proposal.provider} / ${proposal.model ?? "unknown"}`
    : null;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
      <Badge tone={STATE_TONE[proposal.state]}>{proposal.state}</Badge>
      <Badge>{proposal.backend}</Badge>
      {proposal.mode && <Badge tone={MODE_TONE[proposal.mode] ?? "neutral"}>{proposal.mode}</Badge>}
      {model && <span className="num text-[11px] text-text-3">{model}</span>}
      {proposal.base_commit && (
        <span className="num ml-auto text-[11px] text-text-3" title={`Base commit ${proposal.base_commit}`}>
          base {proposal.base_commit.slice(0, 12)}
        </span>
      )}
    </div>
  );
}

function FilesChanged({ proposal }: { proposal: FixProposal }) {
  if (!proposal.files_changed.length) return null;
  return (
    <section className="space-y-1.5">
      <SectionLabel>
        Files changed, {proposal.files_changed.length}
      </SectionLabel>
      <ul className="divide-y divide-line">
        {proposal.files_changed.map((f) => (
          <li key={f.path} className="flex items-baseline gap-3 py-1.5">
            <span className="num min-w-0 break-all text-[12px] text-text">{f.path}</span>
            <span className="num ml-auto shrink-0 text-[11px] tnum">
              <span className="text-ok">+{f.additions}</span> <span className="text-bad">-{f.deletions}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function TestBadge({ run, label }: { run: TestRun | null; label: string }) {
  if (!run) {
    return (
      <div className="flex items-baseline gap-2">
        <span className="w-12 shrink-0 text-[12px] text-text-3">{label}</span>
        <span className="text-[12px] text-text-3">not recorded</span>
      </div>
    );
  }
  const Icon = run.passed ? CheckCircle : XCircle;
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-12 shrink-0 text-[12px] text-text-3">{label}</span>
      <Badge tone={run.passed ? "ok" : "bad"}>
        <Icon size={12} weight="bold" aria-hidden />
        {run.passed ? "passed" : "failed"}
      </Badge>
      <span className="min-w-0 text-[12px] text-text-2">{run.summary}</span>
    </div>
  );
}

function OutputTail({ run, label }: { run: TestRun | null; label: string }) {
  if (!run?.output_tail) return null;
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] font-medium text-text-3 [@media(hover:hover)]:hover:text-text">
        <CaretRight size={12} weight="bold" aria-hidden className="transition-transform duration-150 group-open:rotate-90" />
        {label} output
      </summary>
      <pre className="scroll-quiet mt-1.5 max-h-48 overflow-auto whitespace-pre rounded-control bg-surface-2 p-2 font-mono text-[11px] leading-[1.6] text-text-2">
        {run.output_tail}
      </pre>
    </details>
  );
}

function VerificationCard({ proposal }: { proposal: FixProposal }) {
  const v = proposal.verification;
  return (
    <section className="space-y-2">
      <SectionLabel>Verification</SectionLabel>
      <Box className="space-y-2">
        <p className="num break-all text-[12px] text-text-2">{v.command || "no command recorded"}</p>
        <TestBadge run={v.before} label="Before" />
        <TestBadge run={v.after} label="After" />
        {v.tests_modified && (
          <div role="note" className="flex gap-2 rounded-control bg-warn-bg px-2.5 py-2 text-[12px] text-warn">
            <WarningCircle size={15} weight="bold" aria-hidden className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">The agent changed test files.</p>
              <p className="mt-0.5">
                A passing run after a test edit proves less. Read the test diff before approving
                {v.modified_tests.length > 0 ? `: ${v.modified_tests.join(", ")}.` : "."}
              </p>
            </div>
          </div>
        )}
        <div className="space-y-1.5 pt-0.5">
          <OutputTail run={proposal.verification.before} label="Before" />
          <OutputTail run={proposal.verification.after} label="After" />
        </div>
      </Box>
    </section>
  );
}

function ExplanationCard({ proposal }: { proposal: FixProposal }) {
  const incident = useKea((s) => s.incident);
  const explanation = proposal.explanation;
  if (!explanation) return null;
  const serviceOf = new Map(
    (incident?.evidence ?? []).map((e) => [e.evidence_id, (e.data as { service?: string }).service]),
  );
  return (
    <section className="space-y-2">
      <SectionLabel>Explanation</SectionLabel>
      <Box className="space-y-2.5">
        <p className="text-[13px] leading-relaxed text-text">{explanation.summary}</p>
        {explanation.why_it_fixes && (
          <div>
            <p className="text-[12px] font-medium text-text-3">Why it fixes the incident</p>
            <p className="mt-0.5 text-[13px] leading-relaxed text-text-2">{explanation.why_it_fixes}</p>
          </div>
        )}
        {explanation.evidence_ids.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {explanation.evidence_ids.map((id) => (
              <EvidenceChip key={id} id={id} service={serviceOf.get(id)} />
            ))}
          </div>
        )}
        {explanation.risks.length > 0 && (
          <div>
            <p className="text-[12px] font-medium text-text-3">Risks</p>
            <ul className="mt-0.5 list-disc space-y-0.5 pl-5 text-[12px] text-text-2">
              {explanation.risks.map((risk) => (
                <li key={risk}>{risk}</li>
              ))}
            </ul>
          </div>
        )}
      </Box>
    </section>
  );
}

function TraceList({ steps, live }: { steps: FixTraceEntry[]; live?: boolean }) {
  if (!steps.length) return <p className="text-[12px] text-text-3">No agent steps recorded yet.</p>;
  return (
    <ol className="divide-y divide-line">
      {steps.map((step, i) => (
        <li key={`${step.step}-${step.tool}-${i}`} className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-baseline gap-x-2 py-1.5 text-[12px]">
          <span className="num text-text-3">{step.step}</span>
          <span className="min-w-0">
            <span className="font-medium text-text">{step.tool}</span>
            {step.args_summary && <span className="ml-1.5 text-text-3">{step.args_summary}</span>}
            {step.result_summary && (
              <span className="block truncate text-text-3" title={step.result_summary}>
                {step.result_summary}
              </span>
            )}
          </span>
          <span className={cx("num", live && i === steps.length - 1 ? "text-accent" : "text-text-3")}>{step.duration_ms}ms</span>
        </li>
      ))}
    </ol>
  );
}

function ApprovalBar({
  proposal,
  busy,
  onApprove,
  onReject,
  onRegenerate,
}: {
  proposal: FixProposal;
  busy: string | null;
  onApprove: () => void;
  onReject: () => void;
  onRegenerate: () => void;
}) {
  const blocked = !proposal.approvable || !proposal.diff_hash;
  const reason = proposal.approve_blocked_reason ?? (proposal.diff_hash ? null : "This proposal has no diff hash to bind an approval to.");
  return (
    <section aria-labelledby="fix-approval" className="space-y-2">
      <div id="fix-approval">
        <SectionLabel>Approval</SectionLabel>
      </div>
      <Box className="space-y-3">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-[12px] text-text-3">Diff hash</span>
          <span className="num text-[12px] text-text" title={proposal.diff_hash ?? undefined}>
            sha256:{shortHash(proposal.diff_hash)}
          </span>
        </div>
        <div className="space-y-1">
          <p className="text-[12px] font-medium text-text-3">On approve</p>
          <p className="text-[13px] leading-relaxed text-text">
            Record your approval against this exact diff (sha256:{shortHash(proposal.diff_hash)}). Nothing is applied: no
            branch, no commit, no PR.
          </p>
          <Note>Coming later: create a branch, commit the approved diff, draft a PR.</Note>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            busy={busy === "approve"}
            disabled={blocked}
            title={blocked ? (reason ?? "This proposal cannot be approved.") : "Record an approval bound to this diff hash"}
            onClick={onApprove}
          >
            <CheckCircle size={14} weight="bold" aria-hidden /> Approve
          </Button>
          <Button busy={busy === "reject"} onClick={onReject}>
            <XCircle size={14} weight="bold" aria-hidden /> Reject
          </Button>
          <Button variant="ghost" busy={busy === "regenerate"} onClick={onRegenerate}>
            Regenerate
          </Button>
        </div>
        {blocked && reason && (
          <p role="note" className="text-[12px] text-warn">
            Approve is unavailable. {reason}
          </p>
        )}
      </Box>
    </section>
  );
}

function ApprovedCard({ proposal }: { proposal: FixProposal }) {
  const approval = proposal.approval;
  return (
    <section className="space-y-2">
      <Box tone="ok" className="space-y-2">
        <p className="flex items-center gap-2 text-[13px] font-medium text-ok">
          <CheckCircle size={16} weight="bold" aria-hidden />
          {approval ? `Approved by ${approval.approver} at ${utc(approval.approved_at)}` : "Approved"}
        </p>
        <p className="num break-all text-[12px] text-text-2">{approval?.diff_hash ?? proposal.diff_hash ?? ""}</p>
        <p className="text-[12px] text-text-2">Apply is not enabled in this build. {applyReason(proposal.apply.reason)}</p>
      </Box>
      <FutureList />
    </section>
  );
}

function Terminal({ tone, title, children }: { tone: "bad" | "neutral"; title: string; children?: React.ReactNode }) {
  return (
    <div
      role="note"
      className={cx(
        "flex gap-2 rounded-control px-3 py-2.5 text-[13px]",
        tone === "bad" ? "bg-bad-bg text-bad" : "bg-surface-2 text-text-2",
      )}
    >
      <WarningCircle size={16} weight="bold" aria-hidden className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium">{title}</p>
        {children}
      </div>
    </div>
  );
}

/** Propose-only fix review: diff, explanation, tests, and an approval bound to the diff hash. */
export function FixTab() {
  const incident = useKea((s) => s.incident);
  const incidentId = incident?.incident_id ?? null;
  const proposal = useKea((s) => (incidentId ? (s.fixProposals[incidentId] ?? null) : null));
  const signal = useKea((s) => s.fixSignal);
  const setFixProposal = useKea((s) => s.setFixProposal);

  const [view, setView] = useState<"unified" | "split">("unified");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);

  const loadLatest = useCallback(async () => {
    if (!incidentId || FIXTURE_MODE) return;
    try {
      const list = await api.fixProposals(incidentId);
      const pick = [...list].reverse().find((p) => p.state !== "superseded") ?? list.at(-1);
      if (pick) setFixProposal(pick);
    } catch {
      // the tab keeps showing whatever it already has; the next poll or signal retries
    }
  }, [incidentId, setFixProposal]);

  // first look at this incident
  useEffect(() => {
    void loadLatest();
  }, [loadLatest]);

  // a fix.state message only carries the state; fetch the full proposal
  const signalKey = signal && signal.incident_id === incidentId ? `${signal.proposal_id}:${signal.state}` : null;
  useEffect(() => {
    const id = signalKey?.split(":")[0];
    if (!id || FIXTURE_MODE) return;
    api
      .fixProposal(id)
      .then(setFixProposal)
      .catch(() => undefined);
  }, [signalKey, setFixProposal]);

  // fallback for a missed WebSocket message while the agent works
  const working = proposal !== null && ACTIVE.includes(proposal.state);
  const workingId = working ? proposal.proposal_id : null;
  useEffect(() => {
    if (!workingId || FIXTURE_MODE) return;
    const timer = setInterval(() => {
      api
        .fixProposal(workingId)
        .then(setFixProposal)
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [workingId, setFixProposal]);

  const act = async (name: string, fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(name);
    setError(null);
    try {
      await fn();
    } catch (e) {
      if (name === "propose" && e instanceof ApiError && e.status === 409) setBlocked(e.message);
      else setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const propose = () =>
    act("propose", async () => {
      if (!incidentId) return;
      setBlocked(null);
      const created = await api.createFixProposal(incidentId);
      setFixProposal(await api.fixProposal(created.proposal_id));
    });

  const regenerate = () =>
    act("regenerate", async () => {
      if (!proposal) return;
      const created = await api.regenerateFix(proposal.proposal_id);
      setFixProposal(await api.fixProposal(created.proposal_id));
    });

  const approve = () =>
    act("approve", async () => {
      if (!proposal?.diff_hash) return;
      setFixProposal(await api.approveFix(proposal.proposal_id, proposal.diff_hash, APPROVER));
    });

  const reject = () =>
    act("reject", async () => {
      if (!proposal) return;
      setFixProposal(await api.rejectFix(proposal.proposal_id));
    });

  const intro = (
    <p className="text-[12px] leading-relaxed text-text-3">
      Propose only. A human approves by exact diff hash; nothing is applied in this build.
    </p>
  );

  if (!incident) {
    return (
      <div className="space-y-4">
        {intro}
        <p className="text-[13px] text-text-3">Start a run and wait for an incident to open.</p>
      </div>
    );
  }

  const body = () => {
    if (!proposal) {
      return (
        <div className="flex flex-col items-center px-4 py-10 text-center">
          <IconTile>
            <Code size={18} weight="bold" />
          </IconTile>
          <p className="mt-4 text-[15px] font-medium text-text">No fix proposal yet</p>
          <p className="mt-1 max-w-[320px] text-[13px] leading-snug text-text-3">
            A coding agent opens the deployed commit in a sandbox, writes a candidate fix and runs the test suite before
            and after. You review the diff and record an approval against its exact hash.
          </p>
          {blocked ? (
            <p role="note" className="mt-4 max-w-[320px] text-[13px] text-text-2">
              {blocked}
            </p>
          ) : (
            <Button
              variant="primary"
              className="mt-4"
              busy={busy === "propose"}
              disabled={FIXTURE_MODE}
              title={FIXTURE_MODE ? "Needs the live backend" : "Ask the coding agent for a candidate fix"}
              onClick={propose}
            >
              <Code size={14} weight="bold" aria-hidden /> Propose a fix
            </Button>
          )}
          {FIXTURE_MODE && <p className="mt-2 text-[12px] text-text-3">Fix proposals need the live backend.</p>}
        </div>
      );
    }

    if (ACTIVE.includes(proposal.state)) {
      return (
        <div className="space-y-5" role="status" aria-live="polite">
          <HeaderRow proposal={proposal} />
          <p className="text-[13px] text-text-2">
            {proposal.state === "queued" ? "Waiting for a sandbox." : "The agent is writing and testing a fix."}
          </p>
          <section className="space-y-1.5">
            <SectionLabel>Agent steps</SectionLabel>
            <TraceList steps={proposal.agent_trace} live />
          </section>
          <div className="space-y-2">
            <SectionLabel>Diff</SectionLabel>
            <Skeleton className="h-40 w-full" />
          </div>
          <div className="space-y-2">
            <SectionLabel>Explanation</SectionLabel>
            <Skeleton className="h-16 w-full" />
          </div>
          <div className="space-y-2">
            <SectionLabel>Verification</SectionLabel>
            <Skeleton className="h-20 w-full" />
          </div>
        </div>
      );
    }

    if (proposal.state === "failed") {
      return (
        <div className="space-y-4">
          <HeaderRow proposal={proposal} />
          <Terminal tone="bad" title="The fix attempt failed.">
            <p className="mt-0.5 text-[12px]">{proposal.error ?? "No reason was recorded."}</p>
          </Terminal>
          <Button variant="primary" busy={busy === "regenerate"} onClick={regenerate}>
            Retry
          </Button>
        </div>
      );
    }

    const terminal =
      proposal.state === "rejected"
        ? "You rejected this proposal. Nothing was applied."
        : proposal.state === "superseded"
          ? "A newer proposal replaced this one."
          : null;

    return (
      <div className="space-y-5">
        <HeaderRow proposal={proposal} />
        {terminal && (
          <Terminal tone="neutral" title={terminal}>
            <p className="mt-0.5 text-[12px]">Regenerate to ask the agent for another candidate.</p>
          </Terminal>
        )}
        {proposal.state === "approved" && <ApprovedCard proposal={proposal} />}
        <FilesChanged proposal={proposal} />
        <section className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <SectionLabel>Diff</SectionLabel>
            <Segmented
              label="Diff layout"
              value={view}
              onChange={setView}
              options={[
                { value: "unified", label: "Unified" },
                { value: "split", label: "Split" },
              ]}
            />
          </div>
          <DiffView diff={proposal.diff} counts={proposal.files_changed} view={view} />
        </section>
        <ExplanationCard proposal={proposal} />
        <VerificationCard proposal={proposal} />
        {proposal.agent_trace.length > 0 && (
          <details className="group border-t border-line pt-3">
            <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] font-medium text-text-3 [@media(hover:hover)]:hover:text-text">
              <CaretRight size={12} weight="bold" aria-hidden className="transition-transform duration-150 group-open:rotate-90" />
              Agent steps, {proposal.agent_trace.length}
            </summary>
            <div className="pt-2">
              <TraceList steps={proposal.agent_trace} />
            </div>
          </details>
        )}
        {proposal.state === "proposed" && (
          <ApprovalBar proposal={proposal} busy={busy} onApprove={approve} onReject={reject} onRegenerate={regenerate} />
        )}
        {proposal.state !== "approved" && proposal.state !== "proposed" && (
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" busy={busy === "regenerate"} onClick={regenerate}>
              Regenerate
            </Button>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {intro}
      {body()}
      {error && (
        <p role="alert" className="text-[12px] text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
