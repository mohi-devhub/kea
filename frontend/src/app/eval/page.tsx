"use client";

import { WarningCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Findings, ScenarioGrid, Verdicts } from "@/components/WhyKea";
import { Badge, EmptyState, Panel, Segmented } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { EvalAggregate, EvalReport, EvalRun } from "@/lib/types";

type Tab = "findings" | "matrix" | "method";

export default function EvalPage() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("findings");
  useEffect(() => {
    api
      .evalLatest()
      .then(setReport)
      .catch((reason) => {
        setError(
          reason instanceof ApiError && reason.status === 404
            ? "No eval report yet. Run `make eval`."
            : "Could not load the latest report.",
        );
      });
  }, []);
  return (
    <main className="scroll-quiet flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 pb-8 pt-5">
      <div className="mx-auto flex w-full max-w-[1180px] flex-col gap-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[28px] font-light leading-tight tracking-[-0.02em] text-text">Eval</h1>
            <p className="mt-0.5 max-w-[60ch] text-[14px] text-text-2">The same incidents given to the engine and to an LLM, compared on what matters in production.</p>
          </div>
          {report && <SeedBadge report={report} />}
        </header>
        {report?.warnings?.length ? <Warnings items={report.warnings} /> : null}
        {error && <EmptyState>{error}</EmptyState>}
        {!report && !error && <EmptyState>Loading the latest report...</EmptyState>}
        {report && (
          <>
            <Verdicts report={report} />
            <Segmented<Tab>
              label="Eval sections"
              value={tab}
              onChange={setTab}
              options={[
                { value: "findings", label: "Findings" },
                { value: "matrix", label: "Scenario grid" },
                { value: "method", label: "Method and runs" },
              ]}
            />
            {tab === "findings" && <Findings report={report} />}
            {tab === "matrix" && (
              <>
                <ScenarioGrid rows={report.results} />
                <NotScored rows={report.results} />
              </>
            )}
            {tab === "method" && (
              <>
                <Methodology report={report} />
                <RunDrilldown runs={report.runs ?? []} />
              </>
            )}
          </>
        )}
      </div>
    </main>
  );
}

function NotScored({ rows }: { rows: EvalAggregate[] }) {
  const items = rows.filter((r) => notScored(r) !== "none");
  if (!items.length) return null;
  return (
    <Panel label="Not scored" className="p-4 text-[12px] text-text-2">
      <h3 className="mb-1 text-[13px] font-medium text-text">Not scored</h3>
      {items.map((r) => <p key={`${r.approach}-${r.scenario}`}>{r.approach}, {r.scenario}: {notScored(r)}</p>)}
    </Panel>
  );
}

function SeedBadge({ report }: { report: EvalReport }) {
  const final = report.meta.seed_set === "heldout";
  return <Badge tone={final ? "ok" : "warn"}>{final ? "Held-out seeds" : "Tuning seeds, not the final run"}</Badge>;
}

function Warnings({ items }: { items: string[] }) {
  return (
    <div role="alert" className="mx-4 mt-4 flex gap-2 rounded-control bg-bad-bg px-3 py-2 text-[13px] text-bad">
      <WarningCircle size={16} weight="bold" aria-hidden className="mt-0.5 shrink-0" />
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function notScored(row: EvalAggregate) {
  const parts = Object.entries(row.unscored ?? {}).map(([reason, count]) => `${count} ${reason.replace("_", " ")}`);
  if (row.parse_errors) parts.push(`${row.parse_errors} malformed (counted wrong)`);
  return parts.length ? parts.join(", ") : "none";
}

function Methodology({ report }: { report: EvalReport }) {
  const m = report.meta;
  const rows: [string, string][] = [
    ["Baseline model", m.baseline_model ? `${m.baseline_provider} / ${m.baseline_model}` : "not run"],
    ["Agent model", m.agent_model ? `${m.agent_provider} / ${m.agent_model}` : "template"],
    ["Reasoning effort", m.reasoning_effort],
    ["Prompt version", m.prompt_version],
    ["Seeds", `${m.seeds.length} (${m.seeds[0]} to ${m.seeds[m.seeds.length - 1]}), ${m.runs} run(s) per case`],
    ["Held-out evaluations", String(m.heldout_eval_count)],
    ["Engine weights", (report.engine_config?.weights ?? []).join(", ")],
    ["Code commit", m.git_commit.slice(0, 10)],
  ];
  return (
    <Panel label="Methodology and limitations" className="p-4">
      <h2 className="text-[14px] font-medium text-text">Methodology and limitations</h2>
      <dl className="mt-3 grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1 text-[12px]">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-text-3">{label}</dt>
            <dd className="num text-text-2">{value}</dd>
          </div>
        ))}
      </dl>
      <ul className="mt-4 list-disc space-y-1 border-t border-line pt-3 pl-5 text-[12px] leading-relaxed text-text-2">
        {report.limitations.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Panel>
  );
}

function RunDrilldown({ runs }: { runs: EvalRun[] }) {
  if (!runs.length) return null;
  return (
    <Panel label="Run drill-down" className="overflow-hidden">
      <div className="scroll-quiet max-h-[420px] overflow-y-auto px-4 py-2">
        {runs.map((run) => (
          <details key={`${run.approach}-${run.scenario}-${run.seed}-${run.run_index}`} className="border-b border-line py-2 last:border-0">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[12px] text-text-2">
              <span>
                <span className="font-medium text-text">{run.approach}</span>, {run.scenario}, seed {run.seed}
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={run.status && run.status !== "ok" ? "warn" : "neutral"}>{runLabel(run)}</Badge>
                <span className="num text-text-3">{run.latency_ms != null ? `${run.latency_ms} ms` : "-"}</span>
              </span>
            </summary>
            <div className="grid gap-3 pb-2 pt-3 text-[11px] text-text-3 md:grid-cols-3">
              <div>
                <div className="mb-1">Input hash</div>
                <code className="num break-all text-text-2">{run.input_sha256}</code>
              </div>
              <div>
                <div className="mb-1">Grading</div>
                <pre className="scroll-quiet num max-h-40 overflow-auto whitespace-pre-wrap text-text-2">{JSON.stringify(run.grade, null, 2)}</pre>
              </div>
              <div>
                <div className="mb-1">Output</div>
                <pre className="scroll-quiet num max-h-40 overflow-auto whitespace-pre-wrap text-text-2">
                  {run.error ?? JSON.stringify(run.parsed_output ?? run.raw_output ?? "No output", null, 2)}
                </pre>
              </div>
            </div>
          </details>
        ))}
      </div>
    </Panel>
  );
}

function runLabel(run: EvalRun) {
  if (run.status && run.status !== "ok") return run.status.replace("_", " ");
  return typeof run.grade.mode === "string" ? run.grade.mode : "scored";
}

