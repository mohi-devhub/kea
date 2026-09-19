"use client";

import { useState, type ReactNode } from "react";
import { BarChart, LineChart, SERIES, type BarGroup } from "@/components/charts";
import { Panel, Segmented } from "@/components/ui";
import type { EvalAggregate, EvalReport } from "@/lib/types";

const APPROACHES = ["engine", "llm_raw", "llm_raw_topology"];
const SCENARIO_LABEL: Record<string, string> = {
  s1_bad_deploy_payment: "S1 bad deploy",
  s2_postgres_degradation: "S2 database fault",
  s3_red_herring_deploy: "S3 decoy deploy",
  s4_benign_deploy: "S4 healthy deploy",
};
const pct = (v: number) => `${Math.round(v * 100)}%`;
const rate = (m: { k: number; n: number }) => (m.n ? m.k / m.n : 0);
const find = (rows: EvalAggregate[], approach: string, scenario: string) => rows.find((r) => r.approach === approach && r.scenario === scenario);

function byScenario(rows: EvalAggregate[], pick: (r: EvalAggregate) => { k: number; n: number }, only?: (s: string) => boolean): BarGroup[] {
  const scenarios = [...new Set(rows.map((r) => r.scenario))].filter((s) => (only ? only(s) : true));
  return scenarios.map((scenario) => ({
    label: SCENARIO_LABEL[scenario] ?? scenario,
    bars: APPROACHES.flatMap((approach) => {
      const row = find(rows, approach, scenario);
      if (!row || !row.n) return [];
      const m = pick(row);
      return [{ series: approach, value: rate(m), text: `${m.k}/${m.n}`, detail: `${SERIES[approach].label}: ${m.k} of ${m.n} (${pct(rate(m))})` }];
    }),
  }));
}

const FAULT_LABEL: Record<string, string> = { cpu: "CPU hog", mem: "Memory leak", disk: "Disk stress", delay: "Network delay", loss: "Packet loss" };

function rcaGroups(rca: NonNullable<EvalReport["rcaeval"]>): BarGroup[] {
  const faults = Object.keys(FAULT_LABEL);
  const bar = (approach: string, fs: string[]) => {
    const cells = fs.map((f) => rca.by_fault[approach]?.[f] ?? [0, 0]);
    const k = cells.reduce((a, c) => a + c[0], 0);
    const n = cells.reduce((a, c) => a + c[1], 0);
    return { series: approach, value: n ? k / n : 0, text: `${k}/${n}`, detail: `${SERIES[approach].label}: ${k} of ${n}` };
  };
  return [{ label: "All faults", fs: faults }, ...faults.map((f) => ({ label: FAULT_LABEL[f], fs: [f] }))].map(({ label, fs }) => ({
    label,
    bars: APPROACHES.filter((a) => rca.by_fault[a]).map((a) => bar(a, fs)),
  }));
}

type Tone = "ok" | "warn" | "neutral";
const TONE_CLASS: Record<Tone, string> = { ok: "text-ok", warn: "text-warn", neutral: "text-text-2" };

function Tile({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: Tone }) {
  return (
    <div className="rounded-card border border-line bg-surface p-4 shadow-card">
      <div className="text-[12px] text-text-3">{label}</div>
      <div className={`mt-1 font-mono text-[22px] font-light tabular-nums tracking-[-0.02em] ${TONE_CLASS[tone]}`}>{value}</div>
      <div className="mt-0.5 text-[12px] leading-snug text-text-2">{sub}</div>
    </div>
  );
}

const sum = (rows: EvalAggregate[], approach: string, pick: (r: EvalAggregate) => { k: number; n: number }, only: (s: string) => boolean) =>
  rows.filter((r) => r.approach === approach && only(r.scenario)).reduce((a, r) => ({ k: a.k + pick(r).k, n: a.n + pick(r).n }), { k: 0, n: 0 });

/** The five headline claims, each computed from the data, with the losing one shown in amber. */
export function Verdicts({ report }: { report: EvalReport }) {
  const rows = report.results;
  const isS4 = (s: string) => s.startsWith("s4");
  const notS4 = (s: string) => !isS4(s);
  const alarm = (a: string) => sum(rows, a, (r) => r.false_alarm, isS4);
  const acc = (a: string) => sum(rows, a, (r) => r.top1_correct, notS4);
  const cost = report.consistency?.cost ?? report.cost;
  const agreement = Math.min(
    ...(report.consistency?.results ?? []).filter((r) => r.approach !== "engine").map((r) => (r.extra.consistency as { agreement: number } | undefined)?.agreement ?? 1),
  );
  const rca = report.rcaeval;
  const rcaSum = (a: string) => Object.values(rca?.by_fault[a] ?? {}).reduce((t, [k, n]) => [t[0] + k, t[1] + n], [0, 0]);
  const frac = (m: { k: number; n: number }) => `${m.k}/${m.n}`;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <Tile tone="ok" label="False alarms, healthy deploy" value={`${frac(alarm("engine"))} vs ${frac(alarm("llm_raw"))}`} sub="Engine vs LLM. The LLM blamed a harmless deploy." />
      <Tile tone="neutral" label="Accuracy, incidents" value={`${frac(acc("engine"))} vs ${frac(acc("llm_raw"))}`} sub="A tie on simulated incidents. Not a win." />
      {Number.isFinite(agreement) && <Tile tone="ok" label="Same answer twice" value={`100% vs ${Math.round(agreement * 100)}%`} sub="Engine vs the least consistent LLM run." />}
      {cost?.engine && cost.llm_raw && (
        <Tile tone="ok" label="Time and tokens" value={`${fmtMs(cost.engine.median_latency_ms)} vs ${fmtMs(cost.llm_raw.median_latency_ms)}`} sub={`0 vs ${(cost.llm_raw.median_tokens ?? 0).toLocaleString()} tokens per analysis.`} />
      )}
      {rca && <Tile tone="warn" label="Real data (RCAEval)" value={`${rcaSum("engine")[0]}/${rcaSum("engine")[1]} vs ${rcaSum("llm_raw")[0]}/${rcaSum("llm_raw")[1]}`} sub="Where the engine loses: noisy real metrics." />}
    </div>
  );
}

const METRICS = {
  top1: { label: "Top-1 correct", pick: (r: EvalAggregate) => r.top1_correct, good: "high" },
  top3: { label: "Top-3 contains", pick: (r: EvalAggregate) => r.top3_contains, good: "high" },
  alarm: { label: "False alarm", pick: (r: EvalAggregate) => r.false_alarm, good: "low" },
  blame: { label: "False blame", pick: (r: EvalAggregate) => r.false_blame, good: "low" },
} as const;
type MetricKey = keyof typeof METRICS;

/** Approach by scenario grid; cell fill says whether the result is good, bad or in between. */
export function ScenarioGrid({ rows }: { rows: EvalAggregate[] }) {
  const [metric, setMetric] = useState<MetricKey>("top1");
  const m = METRICS[metric];
  const approaches = [...new Set(rows.map((r) => r.approach))];
  const scenarios = [...new Set(rows.map((r) => r.scenario))];
  const fill = (rate: number) => {
    const goodness = m.good === "high" ? rate : 1 - rate;
    return goodness >= 0.8 ? "bg-ok-bg text-ok" : goodness >= 0.4 ? "bg-warn-bg text-warn" : "bg-bad-bg text-bad";
  };
  return (
    <Panel label="Scenario grid" className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-3">
        <h3 className="text-[14px] font-medium text-text">Every approach on every scenario</h3>
        <Segmented<MetricKey> label="Metric" value={metric} onChange={setMetric} options={(Object.keys(METRICS) as MetricKey[]).map((k) => ({ value: k, label: METRICS[k].label }))} />
      </div>
      <div className="scroll-quiet overflow-x-auto px-4 pb-4 pt-3">
        <table className="w-full min-w-[640px] border-separate border-spacing-1 text-center text-[12px]">
          <thead>
            <tr className="text-text-3">
              <th className="w-[140px] px-2 py-1 text-left font-medium">Approach</th>
              {scenarios.map((s) => <th key={s} className="px-2 py-1 font-medium">{SCENARIO_LABEL[s] ?? s}</th>)}
            </tr>
          </thead>
          <tbody>
            {approaches.map((a) => (
              <tr key={a}>
                <th scope="row" className="px-2 py-1 text-left font-medium text-text">{SERIES[a]?.label ?? a}</th>
                {scenarios.map((s) => {
                  const row = find(rows, a, s);
                  if (!row) return <td key={s} className="rounded-control bg-surface-2 py-2 text-text-3">-</td>;
                  const c = m.pick(row);
                  if (!c.n) return <td key={s} className="rounded-control bg-surface-2 py-2 text-text-3">not run</td>;
                  return (
                    <td key={s} title={`95% interval ${c.ci_low.toFixed(2)} to ${c.ci_high.toFixed(2)}`} className={`rounded-control py-2 font-mono tabular-nums ${fill(c.k / c.n)}`}>
                      {c.k}/{c.n}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 px-1 text-[11px] text-text-3">
          {m.good === "high" ? "Higher is better." : "Lower is better."} Hover a cell for its 95 percent Wilson interval. Small samples give wide intervals.
        </p>
      </div>
    </Panel>
  );
}

export function Findings({ report }: { report: EvalReport }) {
  const rows = report.results;
  const consistency = report.consistency;
  const cost = consistency?.cost ?? report.cost;
  const consistencyGroups: BarGroup[] = consistency
    ? [...new Set(consistency.results.map((r) => r.scenario))].map((scenario) => ({
        label: SCENARIO_LABEL[scenario] ?? scenario,
        bars: APPROACHES.flatMap((approach) => {
          const row = find(consistency.results, approach, scenario);
          if (approach === "engine") return row ? [{ series: approach, value: 1, text: "100%", detail: "Deterministic: identical input gives identical output" }] : [];
          const c = row?.extra.consistency as { agreement: number } | undefined;
          return c ? [{ series: approach, value: c.agreement, text: pct(c.agreement) }] : [];
        }),
      }))
    : [];
  const scale = report.scale;
  const rca = report.rcaeval;
  const lines = (pick: (p: NonNullable<typeof scale>["points"][number]) => number | null) =>
    APPROACHES.map((a) => ({
      series: a,
      points: (scale?.points ?? []).filter((p) => p.approach === a && pick(p) != null).map((p) => ({ x: p.services, y: pick(p) as number })),
    })).filter((l) => l.points.length);
  return (
    <div className="space-y-6">
      <Group title="Where kea wins" text="Same accuracy as an LLM on simulated incidents, but no false alarms, the same answer every time, and milliseconds instead of seconds.">
        <BarChart title="False alarms on a healthy deploy (lower is better)" groups={byScenario(rows, (r) => r.false_alarm, (s) => s.startsWith("s4"))} />
        {consistencyGroups.length > 0 && <BarChart title="Same input run 5 times: how often the answer repeats" groups={consistencyGroups} />}
        {cost && <CostTable cost={cost} />}
      </Group>
      {scale && scale.points.length > 0 && (
        <Group title="Does an LLM degrade as systems grow?" text="No. Its accuracy held from 7 to 63 services. What grows is its cost: tokens rise about ninefold. The engine stays under half a second.">
          <LineChart title="Top-1 accuracy by topology size" xLabel="services" yMax={1} yFormat={pct} lines={lines((p) => p.top1_correct)} />
          <LineChart title="Median tokens per analysis" xLabel="services" yFormat={(v) => `${Math.round(v / 100) / 10}k`} lines={lines((p) => p.median_tokens)} />
          <LineChart title="Median latency per analysis" xLabel="services" yFormat={fmtMs} lines={lines((p) => p.median_latency_ms)} />
        </Group>
      )}
      {rca && (
        <Group tone="warn" title="Where kea loses: real data" text="Replaying 25 real Online Boutique fault injections (RCAEval), the LLM finds the root cause more often. The engine was built and tuned on clean simulated telemetry, and it only sees latency, error rate, request rate and memory.">
          <BarChart title={`RCAEval RE1-OB, ${rca.cases} cases: top-1 by fault type`} groups={rcaGroups(rca)} />
          <Panel label="Caveats" className="p-4 text-[13px] leading-relaxed text-text-2 xl:col-span-2">
            <h3 className="mb-1 text-[13px] font-medium text-text">How to read this</h3>
            <ul className="list-disc space-y-1 pl-5">
              <li>Real fault injections on Online Boutique, one case per service and fault type, metrics only.</li>
              <li>The metric mapping was fixed before the first run and not tuned afterwards.</li>
              <li>CPU, disk and network counters are not in the engine&apos;s metric set, so it is partly blind to those faults.</li>
              <li>This tests the service-fault path only. The dataset has no deployment events, so it says nothing about deploy attribution.</li>
              <li>25 cases is small. Treat the gap as direction, not a precise number.</li>
            </ul>
          </Panel>
        </Group>
      )}
    </div>
  );
}

function Group({ title, text, tone, children }: { title: string; text: string; tone?: "warn"; children: ReactNode }) {
  return (
    <section aria-label={title}>
      <h2 className={`text-[16px] font-medium tracking-[-0.01em] ${tone === "warn" ? "text-warn" : "text-text"}`}>{title}</h2>
      <p className="mb-3 mt-0.5 max-w-[70ch] text-[13px] leading-relaxed text-text-2">{text}</p>
      <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3">{children}</div>
    </section>
  );
}

function CostTable({ cost }: { cost: NonNullable<EvalReport["cost"]> }) {
  return (
    <figure className="flex flex-col rounded-card border border-line bg-surface p-4 shadow-card">
      <figcaption className="mb-3 text-[13px] font-medium text-text">Cost and latency per analysis (median)</figcaption>
      <div className="flex-1 overflow-x-auto">
        <table className="w-full text-left text-[12px]">
          <thead>
            <tr className="text-text-3"><th className="pb-1.5 font-medium">Approach</th><th className="pb-1.5 text-right font-medium">Latency</th><th className="pb-1.5 text-right font-medium">Tokens</th></tr>
          </thead>
          <tbody>
            {APPROACHES.filter((a) => cost[a]).map((a) => (
              <tr key={a} className="border-t border-line">
                <td className="py-2"><span aria-hidden className="mr-1.5 inline-block size-2.5 rounded-sm" style={{ background: SERIES[a].color }} />{SERIES[a].label}</td>
                <td className="py-2 text-right font-mono tabular-nums">{fmtMs(cost[a].median_latency_ms)}</td>
                <td className="py-2 text-right font-mono tabular-nums">{(cost[a].median_tokens ?? 0).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

const fmtMs = (ms: number | null) => (ms == null ? "n/a" : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
