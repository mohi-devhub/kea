"use client";

import { useState } from "react";
import { ChartCard, ColumnChart, HBarChart, LineChart, SERIES, type BarGroup } from "@/components/charts";
import { Panel, Segmented } from "@/components/ui";
import type { EvalAggregate, EvalReport } from "@/lib/types";

const APPROACHES = ["engine", "llm_raw", "llm_raw_topology"];
const SCENARIO_LABEL: Record<string, string> = {
  s1_bad_deploy_payment: "S1 Bad deploy",
  s2_postgres_degradation: "S2 Database fault",
  s3_red_herring_deploy: "S3 Decoy deploy",
  s4_benign_deploy: "S4 Healthy deploy",
};
const FAULT_LABEL: Record<string, string> = { cpu: "CPU hog", mem: "Memory leak", disk: "Disk stress", delay: "Network delay", loss: "Packet loss" };
const pct = (v: number) => `${Math.round(v * 100)}%`;
const fmtMs = (ms: number | null) => (ms == null ? "n/a" : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
const find = (rows: EvalAggregate[], approach: string, scenario: string) => rows.find((r) => r.approach === approach && r.scenario === scenario);
type Frac = { k: number; n: number };
const sum = (rows: EvalAggregate[], approach: string, pick: (r: EvalAggregate) => Frac, only: (s: string) => boolean): Frac =>
  rows.filter((r) => r.approach === approach && only(r.scenario)).reduce((a, r) => ({ k: a.k + pick(r).k, n: a.n + pick(r).n }), { k: 0, n: 0 });
const frac = (m: Frac) => (m.n ? `${m.k}/${m.n}` : "not run");
const barOf = (approach: string, m: Frac) => ({ series: approach, value: m.n ? m.k / m.n : 0, text: frac(m), detail: `${SERIES[approach].label}: ${m.k} of ${m.n} (${m.n ? pct(m.k / m.n) : "n/a"})` });

const SHORT: Record<string, string> = { engine: "kea engine", llm_raw: "LLM raw", llm_raw_topology: "LLM topology" };
const isS4 = (s: string) => s.startsWith("s4");

/** One table, kea highlighted, the headline numbers in a single glance. */
export function CompareTable({ report }: { report: EvalReport }) {
  const rows = report.results;
  const cost = report.consistency?.cost ?? report.cost;
  const agree = (a: string) => {
    if (a === "engine") return report.consistency ? 1 : null;
    const values = (report.consistency?.results ?? []).filter((r) => r.approach === a).map((r) => (r.extra.consistency as { agreement: number } | undefined)?.agreement);
    const nums = values.filter((v): v is number => v != null);
    return nums.length ? nums.reduce((x, y) => x + y, 0) / nums.length : null;
  };
  const rca = (a: string): Frac => Object.values(report.rcaeval?.by_fault[a] ?? {}).reduce((t, [k, n]) => ({ k: t.k + k, n: t.n + n }), { k: 0, n: 0 });
  type Row = { name: string; sub: string; cells: Record<string, string | null>; loses?: boolean };
  const data: Row[] = [
    { name: "Root cause found", sub: "Simulated incidents S1 to S3, top-1", cells: Object.fromEntries(APPROACHES.map((a) => [a, frac(sum(rows, a, (r) => r.top1_correct, (s) => !isS4(s)))])) },
    { name: "False alarms", sub: "Healthy deploy S4, lower is better", cells: Object.fromEntries(APPROACHES.map((a) => [a, frac(sum(rows, a, (r) => r.false_alarm, isS4))])) },
    { name: "Same answer twice", sub: "Same input five times, average over scenarios", cells: Object.fromEntries(APPROACHES.map((a) => [a, agree(a) == null ? null : pct(agree(a) as number)])) },
    { name: "Median latency", sub: "Per analysis", cells: Object.fromEntries(APPROACHES.map((a) => [a, cost?.[a] ? fmtMs(cost[a].median_latency_ms) : null])) },
    { name: "Tokens", sub: "Per analysis", cells: Object.fromEntries(APPROACHES.map((a) => [a, cost?.[a] ? (cost[a].median_tokens ?? 0).toLocaleString() : null])) },
  ];
  if (report.rcaeval) data.push({ name: "Root cause found", sub: "Real data, RCAEval, 25 cases", loses: true, cells: Object.fromEntries(APPROACHES.map((a) => [a, frac(rca(a))])) });
  return (
    <div className="overflow-x-auto rounded-card border border-line bg-surface shadow-card">
      <table className="w-full min-w-[680px] border-collapse text-left">
        <thead>
          <tr>
            <th className="w-[34%] px-5 py-3" />
            {APPROACHES.map((a) => (
              <th key={a} className={`px-4 py-3 text-[14px] font-medium text-text ${a === "engine" ? "bg-accent-bg" : ""}`}>{SERIES[a].label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.name + row.sub} className="border-t border-line align-top">
              <th scope="row" className="px-5 py-3 text-left font-normal">
                <div className="text-[14px] font-medium text-text">{row.name}</div>
                <div className="text-[12px] text-text-3">{row.sub}</div>
              </th>
              {APPROACHES.map((a) => (
                <td key={a} className={`px-4 py-3 ${a === "engine" ? "bg-accent-bg" : ""}`}>
                  <span className={`font-mono text-[15px] tabular-nums ${row.loses && a === "engine" ? "text-warn" : "text-text"} ${a === "engine" ? "font-medium" : ""}`}>{row.cells[a] ?? "-"}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type ChartTab = "accuracy" | "consistency" | "cost" | "scale" | "real";

/** Pill tabs switch which figure is shown, one framed chart at a time with its note underneath. */
export function ResultCharts({ report }: { report: EvalReport }) {
  const [tab, setTab] = useState<ChartTab>("accuracy");
  const [table, setTable] = useState(false);
  const rows = report.results;
  const cost = report.consistency?.cost ?? report.cost;
  const scale = report.scale;
  const rca = report.rcaeval;
  const options: { value: ChartTab; label: string; disabled?: boolean }[] = [
    { value: "accuracy", label: "Accuracy and false alarms" },
    { value: "consistency", label: "Repeatability", disabled: !report.consistency },
    { value: "cost", label: "Cost and speed", disabled: !cost },
    { value: "scale", label: "Scale", disabled: !scale?.points.length },
    { value: "real", label: "Real data", disabled: !rca },
  ];
  const scenarios = [...new Set(rows.map((r) => r.scenario))];
  const accuracyGroups: BarGroup[] = scenarios.map((s) => ({ label: SCENARIO_LABEL[s] ?? s, bars: APPROACHES.flatMap((a) => { const r = find(rows, a, s); return r && r.n ? [barOf(a, r.top1_correct)] : []; }) }));
  const alarmGroups: BarGroup[] = APPROACHES.flatMap((a) => { const m = sum(rows, a, (r) => r.false_alarm, isS4); return m.n ? [{ label: SHORT[a], bars: [barOf(a, m)] }] : []; });
  const consistencyGroups: BarGroup[] = [...new Set((report.consistency?.results ?? []).map((r) => r.scenario))].map((s) => ({
    label: SCENARIO_LABEL[s] ?? s,
    bars: APPROACHES.flatMap((a) => {
      const row = find(report.consistency?.results ?? [], a, s);
      if (a === "engine") return row ? [{ series: a, value: 1, text: "100%", detail: "Deterministic: identical input gives identical output" }] : [];
      const c = row?.extra.consistency as { agreement: number } | undefined;
      return c ? [{ series: a, value: c.agreement, text: pct(c.agreement) }] : [];
    }),
  }));
  const costGroups = (pick: (c: NonNullable<typeof cost>[string]) => number): BarGroup[] =>
    APPROACHES.filter((a) => cost?.[a]).map((a) => ({ label: SERIES[a].label, bars: [{ series: a, value: pick((cost as NonNullable<typeof cost>)[a]), text: "" }] }));
  const latency = costGroups((c) => (c.median_latency_ms ?? 0) / 1000).map((g) => ({ ...g, bars: g.bars.map((b) => ({ ...b, text: fmtMs(b.value * 1000) })) }));
  const tokens = costGroups((c) => c.median_tokens ?? 0).map((g) => ({ ...g, bars: g.bars.map((b) => ({ ...b, text: b.value.toLocaleString() })) }));
  const lines = (pick: (p: NonNullable<typeof scale>["points"][number]) => number | null) =>
    APPROACHES.map((a) => ({ series: a, points: (scale?.points ?? []).filter((p) => p.approach === a && pick(p) != null).map((p) => ({ x: p.services, y: pick(p) as number })) })).filter((l) => l.points.length);
  const faults = Object.keys(FAULT_LABEL);
  const rcaGroups: BarGroup[] = rca
    ? [{ label: "All faults", sub: `${rca.cases} cases`, fs: faults }, ...faults.map((f) => ({ label: FAULT_LABEL[f], sub: "5 cases", fs: [f] }))].map(({ label, sub, fs }) => ({
        label,
        sub,
        bars: APPROACHES.filter((a) => rca.by_fault[a]).map((a) => {
          const cells = fs.map((f) => rca.by_fault[a]?.[f] ?? [0, 0]);
          return barOf(a, { k: cells.reduce((t, c) => t + c[0], 0), n: cells.reduce((t, c) => t + c[1], 0) });
        }),
      }))
    : [];
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segmented<ChartTab> label="Result charts" value={tab} onChange={setTab} options={options} />
        <button type="button" onClick={() => setTable(!table)} className="text-[13px] text-text-2 underline-offset-2 hover:underline">
          {table ? "View as chart" : "View as table"}
        </button>
      </div>
      {tab === "accuracy" && (
        <ChartCard title="Root cause accuracy and false alarms" subtitle="Simulated incidents, tuning seeds" legend={APPROACHES} caption="Top-1 is the share of runs where the first-ranked cause was correct. False alarms count healthy deploys that an approach blamed anyway. Small samples, so intervals are wide.">
          <div className="grid gap-6 lg:grid-cols-2">
            <ColumnChart title="Top-1 correct, by scenario" groups={accuracyGroups} yFormat={pct} table={table} />
            <ColumnChart title="False alarms on a healthy deploy" groups={alarmGroups} yFormat={pct} table={table} />
          </div>
        </ChartCard>
      )}
      {tab === "consistency" && (
        <ChartCard title="Same input, five runs" subtitle="How often the answer repeats" legend={APPROACHES} caption="Agreement is the share of runs that match the most common answer. Repeated runs of one seed are not independent samples, so read this as a property of the approach, not a precise rate. The engine is deterministic by construction.">
          <div className="mx-auto max-w-[760px]"><ColumnChart groups={consistencyGroups} yFormat={pct} yTitle="Runs agreeing" table={table} /></div>
        </ChartCard>
      )}
      {tab === "cost" && (
        <ChartCard title="Cost and speed per analysis" subtitle="Median" legend={APPROACHES} caption="Engine time is the whole event stream processed in one batch on this machine. LLM figures are one call to the same model for every approach, at low reasoning effort.">
          <div className="grid gap-6 lg:grid-cols-2">
            <HBarChart title="Latency" groups={latency} xMax={Math.max(...latency.map((g) => g.bars[0].value), 1) * 1.1} xTicks={[0, 1, 2, 3, 4]} xFormat={(v) => `${v} s`} xTitle="Seconds per analysis" table={table} />
            <HBarChart title="Tokens" groups={tokens} xMax={Math.max(...tokens.map((g) => g.bars[0].value), 1) * 1.1} xTicks={[0, 2000, 4000, 6000]} xFormat={(v) => `${v / 1000}k`} xTitle="Tokens per analysis" table={table} />
          </div>
        </ChartCard>
      )}
      {tab === "scale" && (
        <ChartCard title="Does an LLM degrade as systems grow?" subtitle="7 to 63 services" legend={APPROACHES} caption="Same fault shape at every size: a database fault, half the graph cascading, and a decoy deployment. The LLM held its accuracy, so the honest finding is about cost: tokens grow about ninefold while the engine stays under half a second.">
          <div className="grid gap-6 lg:grid-cols-2">
            <LineChart title="Top-1 accuracy" lines={lines((p) => p.top1_correct)} xTitle="services" yTitle="Top-1 correct" yMax={1} yFormat={pct} table={table} />
            <LineChart title="Tokens" lines={lines((p) => p.median_tokens)} xTitle="services" yTitle="Median tokens" yFormat={(v) => `${Math.round(v / 100) / 10}k`} table={table} />
            <LineChart title="Latency" lines={lines((p) => p.median_latency_ms)} xTitle="services" yTitle="Median latency" yFormat={fmtMs} table={table} />
          </div>
        </ChartCard>
      )}
      {tab === "real" && rca && (
        <ChartCard title="Real fault injections" subtitle="RCAEval RE1-OB, Online Boutique" legend={APPROACHES} caption="Where kea loses. One case per service and fault type, metrics only, with the metric mapping fixed before the first run. CPU, disk and network counters are not in the engine's metric set. This tests the service-fault path only, and 25 cases is a small sample.">
          <div className="mx-auto max-w-[760px]"><HBarChart groups={rcaGroups} xMax={1} xTicks={[0, 0.25, 0.5, 0.75, 1]} xFormat={pct} xTitle="Top-1 correct" table={table} /></div>
        </ChartCard>
      )}
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

