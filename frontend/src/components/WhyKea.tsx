"use client";

import { BarChart, LineChart, SERIES, type BarGroup } from "@/components/charts";
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

export function WhyKea({ report }: { report: EvalReport }) {
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
    <section aria-label="Why kea" className="mx-auto w-full max-w-[1080px] space-y-3">
      <div>
        <h2 className="text-[18px] font-normal tracking-[-0.01em] text-text">Where kea differs from an LLM</h2>
        <p className="text-[13px] text-text-2">Accuracy is a tie on the cases an LLM can read. The gap is false alarms, repeatability, cost and speed.</p>
      </div>
      <div className="grid items-start gap-3 md:grid-cols-2">
        <BarChart title="False alarms on a healthy deploy (lower is better)" groups={byScenario(rows, (r) => r.false_alarm, (s) => s.startsWith("s4"))} />
        <BarChart title="Top-1 root cause accuracy by scenario" groups={byScenario(rows, (r) => r.top1_correct)} />
        {consistencyGroups.length > 0 && <BarChart title="Run-to-run agreement, same input run 5 times" groups={consistencyGroups} />}
        {cost && <CostTable cost={cost} />}
        {scale && scale.points.length > 0 && (
          <>
            <LineChart title="Accuracy as the topology grows" xLabel="services" yMax={1} yFormat={pct} lines={lines((p) => p.top1_correct)} />
            <LineChart title="Median tokens per analysis as the topology grows" xLabel="services" yFormat={(v) => `${Math.round(v / 100) / 10}k`} lines={lines((p) => p.median_tokens)} />
            <LineChart title="Median latency per analysis as the topology grows" xLabel="services" yFormat={fmtMs} lines={lines((p) => p.median_latency_ms)} />
          </>
        )}
        {rca && <BarChart title={`Real data replay (RCAEval RE1-OB, ${rca.cases} cases): top-1 by fault type`} groups={rcaGroups(rca)} />}
      </div>
    </section>
  );
}

function CostTable({ cost }: { cost: NonNullable<EvalReport["cost"]> }) {
  return (
    <figure className="rounded-card border border-line bg-surface p-4">
      <figcaption className="mb-3 text-[13px] font-medium text-text">Cost and latency per analysis (median)</figcaption>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-[12px]">
          <thead>
            <tr className="text-text-2"><th className="pb-1 font-medium">Approach</th><th className="pb-1 font-medium">Latency</th><th className="pb-1 font-medium">Tokens</th></tr>
          </thead>
          <tbody>
            {APPROACHES.filter((a) => cost[a]).map((a) => (
              <tr key={a} className="border-t border-line">
                <td className="py-1.5"><span aria-hidden className="mr-1.5 inline-block size-2.5 rounded-sm" style={{ background: SERIES[a].color }} />{SERIES[a].label}</td>
                <td className="py-1.5 font-mono tabular-nums">{fmtMs(cost[a].median_latency_ms)}</td>
                <td className="py-1.5 font-mono tabular-nums">{cost[a].median_tokens ? cost[a].median_tokens?.toLocaleString() : "0"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}

const fmtMs = (ms: number | null) => (ms == null ? "n/a" : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${Math.round(ms)} ms`);
