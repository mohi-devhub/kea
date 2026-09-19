"use client";

import { ChartBar, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { Badge, CardHeader, EmptyState, Panel } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import type { EvalAggregate, EvalMetric, EvalReport, EvalRun } from "@/lib/types";

export default function EvalPage() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [error, setError] = useState<string | null>(null);
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
    <main className="scroll-quiet flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 pb-6 pt-5">
      <header className="text-center">
        <h1 className="text-[28px] font-light leading-tight tracking-[-0.02em] text-text">Eval</h1>
        <p className="mt-0.5 text-[14px] text-text-2">Same incidents, compared fairly across the engine and the baselines.</p>
      </header>
      <Panel label="Eval results" className="mx-auto w-full max-w-[1080px] shrink-0 overflow-hidden">
        <CardHeader
          icon={<ChartBar size={18} weight="bold" aria-hidden />}
          title="Headline matrix"
          right={report && <SeedBadge report={report} />}
        />
        {report?.warnings?.length ? <Warnings items={report.warnings} /> : null}
        {error ? <EmptyState>{error}</EmptyState> : report ? <Matrix report={report} /> : <EmptyState>Loading the latest report...</EmptyState>}
      </Panel>
      {report && (
        <>
          <Methodology report={report} />
          <RunDrilldown runs={report.runs ?? []} />
        </>
      )}
    </main>
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

/** k out of n, with the Wilson interval underneath. n = 0 means the approach did not run. */
function Cell({ metric }: { metric: EvalMetric }) {
  if (metric.n === 0) return <span className="text-warn">not run</span>;
  return (
    <span>
      <span className="text-text">
        {metric.k}/{metric.n}
      </span>
      <span className="block text-[11px] text-text-3">
        {metric.ci_low.toFixed(2)} to {metric.ci_high.toFixed(2)}
      </span>
    </span>
  );
}

function notScored(row: EvalAggregate) {
  const parts = Object.entries(row.unscored ?? {}).map(([reason, count]) => `${count} ${reason.replace("_", " ")}`);
  if (row.parse_errors) parts.push(`${row.parse_errors} malformed (counted wrong)`);
  return parts.length ? parts.join(", ") : "none";
}

function Matrix({ report }: { report: EvalReport }) {
  return (
    <div className="scroll-quiet mt-3 overflow-x-auto px-4 pb-4">
      <table className="w-full min-w-[760px] border-collapse text-left text-[12px]">
        <thead>
          <tr className="border-b border-line text-text-3">
            <th className="px-2 py-2 font-medium">Approach</th>
            <th className="px-2 py-2 font-medium">Scenario</th>
            <th className="px-2 py-2 font-medium">Top-1</th>
            <th className="px-2 py-2 font-medium">Top-3</th>
            <th className="px-2 py-2 font-medium">False blame</th>
            <th className="px-2 py-2 font-medium">False alarm</th>
            <th className="px-2 py-2 font-medium">Not scored</th>
          </tr>
        </thead>
        <tbody>
          {report.results.map((row) => (
            <tr key={`${row.approach}-${row.scenario}`} className={`tnum border-b border-line align-top last:border-0 ${isRedHerring(row.scenario) ? "bg-warn-bg" : ""}`}>
              <td className="px-2 py-2 font-medium text-text">{row.approach}</td>
              <td className="px-2 py-2 text-text-2">{row.scenario}</td>
              <td className="px-2 py-2"><Cell metric={row.top1_correct} /></td>
              <td className="px-2 py-2"><Cell metric={row.top3_contains} /></td>
              <td className="px-2 py-2"><Cell metric={row.false_blame} /></td>
              <td className="px-2 py-2"><Cell metric={row.false_alarm} /></td>
              <td className="px-2 py-2 text-text-3">{notScored(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-text-3">Highlighted rows are the red-herring scenarios. Intervals are 95 percent Wilson intervals; small samples give wide ones.</p>
    </div>
  );
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
    <Panel label="Methodology and limitations" className="mx-auto w-full max-w-[1080px] shrink-0 p-4">
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
    <Panel label="Run drill-down" className="mx-auto w-full max-w-[1080px] shrink-0 overflow-hidden">
      <div className="scroll-quiet max-h-[420px] overflow-y-auto px-4 py-2">
        {runs.map((run) => (
          <details key={`${run.approach}-${run.scenario}-${run.seed}-${run.run_index}`} className="border-b border-line py-2 last:border-0">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-[12px] text-text-2">
              <span>
                <span className="font-medium text-text">{run.approach}</span>, {run.scenario}, seed {run.seed}
              </span>
              <span className="flex items-center gap-2">
                <Badge tone={run.status && run.status !== "ok" ? "warn" : "neutral"}>{runLabel(run)}</Badge>
                <span className="num text-text-3">{run.latency_ms ?? "n/a"} ms</span>
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

function isRedHerring(scenario: string) {
  return /(^|_)s[235](_|$)/i.test(scenario);
}
