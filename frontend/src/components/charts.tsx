"use client";

import { useState, type ReactNode } from "react";

export const SERIES: Record<string, { label: string; color: string }> = {
  engine: { label: "kea engine", color: "var(--f1)" },
  llm_raw: { label: "LLM, raw telemetry", color: "var(--f2)" },
  llm_raw_topology: { label: "LLM + topology", color: "var(--f3)" },
};
const seriesOf = (key: string) => SERIES[key] ?? { label: key, color: "var(--text-2)" };

export type Bar = { series: string; value: number; text: string; detail?: string };
export type BarGroup = { label: string; bars: Bar[] };

/** Horizontal grouped bars, values are fractions 0..1 unless `max` is given. */
export function BarChart({ groups, max = 1, title }: { groups: BarGroup[]; max?: number; title: string }) {
  const [table, setTable] = useState(false);
  return (
    <ChartFrame title={title} table={table} setTable={setTable} legend={[...new Set(groups.flatMap((g) => g.bars.map((b) => b.series)))]}>
      {table ? (
        <DataTable rows={groups.flatMap((g) => g.bars.map((b) => [g.label, seriesOf(b.series).label, b.text]))} head={["Group", "Series", "Value"]} />
      ) : (
        <div role="img" aria-label={title} className="space-y-3">
          {groups.map((group) => (
            <div key={group.label} className="grid grid-cols-[minmax(90px,150px)_1fr] items-center gap-3">
              <div className="text-[12px] text-text-2">{group.label}</div>
              <div className="space-y-1">
                {group.bars.map((bar) => (
                  <div key={bar.series} title={bar.detail ?? `${seriesOf(bar.series).label}: ${bar.text}`} className="flex items-center gap-2">
                    <div className="h-3 flex-1 rounded-sm bg-surface-2">
                      <div className="h-3 rounded-r-[4px]" style={{ width: `${Math.max(0, Math.min(1, bar.value / max)) * 100}%`, background: seriesOf(bar.series).color, minWidth: bar.value > 0 ? 3 : 0 }} />
                    </div>
                    <span className="w-[74px] shrink-0 text-right font-mono text-[12px] tabular-nums text-text">{bar.text}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </ChartFrame>
  );
}

export type LinePoint = { x: number; y: number };
export type LineSeries = { series: string; points: LinePoint[] };

export function LineChart({ lines, title, xLabel, yFormat, yMax }: { lines: LineSeries[]; title: string; xLabel: string; yFormat: (v: number) => string; yMax?: number }) {
  const [table, setTable] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const W = 420, H = 190, L = 44, R = 12, T = 12, B = 30;
  const xs = [...new Set(lines.flatMap((l) => l.points.map((p) => p.x)))].sort((a, b) => a - b);
  const top = yMax ?? Math.max(1e-9, ...lines.flatMap((l) => l.points.map((p) => p.y))) * 1.1;
  const px = (x: number) => L + (xs.length < 2 ? (W - L - R) / 2 : ((xs.indexOf(x)) / (xs.length - 1)) * (W - L - R));
  const py = (y: number) => T + (1 - y / top) * (H - T - B);
  return (
    <ChartFrame title={title} table={table} setTable={setTable} legend={lines.map((l) => l.series)}>
      {table ? (
        <DataTable head={[xLabel, "Series", "Value"]} rows={lines.flatMap((l) => l.points.map((p) => [String(p.x), seriesOf(l.series).label, yFormat(p.y)]))} />
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title} className="h-auto w-full">
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line x1={L} x2={W - R} y1={py(top * f)} y2={py(top * f)} stroke="var(--line)" strokeWidth={1} />
              <text x={L - 6} y={py(top * f) + 4} textAnchor="end" fontSize={10} fill="var(--text-2)" className="font-mono">{yFormat(top * f)}</text>
            </g>
          ))}
          {xs.map((x) => (
            <text key={x} x={px(x)} y={H - 10} textAnchor="middle" fontSize={10} fill="var(--text-2)" className="font-mono">{x}</text>
          ))}
          <text x={(L + W - R) / 2} y={H - 0} textAnchor="middle" fontSize={10} fill="var(--text-2)">{xLabel}</text>
          {lines.map((l) => (
            <g key={l.series} opacity={hover && hover !== l.series ? 0.3 : 1} onMouseEnter={() => setHover(l.series)} onMouseLeave={() => setHover(null)}>
              <polyline fill="none" stroke={seriesOf(l.series).color} strokeWidth={2} points={l.points.map((p) => `${px(p.x)},${py(p.y)}`).join(" ")} />
              {l.points.map((p) => (
                <circle key={p.x} cx={px(p.x)} cy={py(p.y)} r={4} fill={seriesOf(l.series).color} stroke="var(--surface)" strokeWidth={2}>
                  <title>{`${seriesOf(l.series).label}, ${p.x} ${xLabel}: ${yFormat(p.y)}`}</title>
                </circle>
              ))}
            </g>
          ))}
        </svg>
      )}
    </ChartFrame>
  );
}

function ChartFrame({ title, table, setTable, legend, children }: { title: string; table: boolean; setTable: (v: boolean) => void; legend: string[]; children: ReactNode }) {
  return (
    <figure className="rounded-card border border-line bg-surface p-4">
      <figcaption className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-text">{title}</span>
        <button type="button" onClick={() => setTable(!table)} className="text-[12px] text-text-2 underline-offset-2 hover:underline">
          {table ? "View as chart" : "View as table"}
        </button>
      </figcaption>
      {children}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        {legend.map((key) => (
          <span key={key} className="flex items-center gap-1.5 text-[12px] text-text-2">
            <span aria-hidden className="inline-block size-2.5 rounded-sm" style={{ background: seriesOf(key).color }} />
            {seriesOf(key).label}
          </span>
        ))}
      </div>
    </figure>
  );
}

function DataTable({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[12px]">
        <thead><tr>{head.map((h) => <th key={h} className="pb-1 font-medium text-text-2">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-line">{r.map((c, j) => <td key={j} className="py-1 font-mono tabular-nums">{c}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}
