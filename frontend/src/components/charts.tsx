"use client";

import type { ReactNode } from "react";

export const SERIES: Record<string, { label: string; color: string }> = {
  engine: { label: "kea engine", color: "var(--f1)" },
  llm_raw: { label: "LLM, raw telemetry", color: "var(--f2)" },
  llm_raw_topology: { label: "LLM + topology", color: "var(--f3)" },
  hybrid: { label: "Engine + LLM explainer", color: "var(--f4)" },
};
export const seriesOf = (key: string) => SERIES[key] ?? { label: key, color: "var(--text-2)" };

export type Bar = { series: string; value: number; text: string; detail?: string };
export type BarGroup = { label: string; sub?: string; bars: Bar[] };

const INK = "var(--text)";
const MUTED = "var(--text-2)";
const GRID = "var(--line)";

/** Bordered chart card: title left, legend right, caption below the frame like a figure note. */
export function ChartCard({ title, subtitle, legend, children, caption }: { title: string; subtitle?: string; legend?: string[]; children: ReactNode; caption?: ReactNode }) {
  return (
    <figure>
      <div className="rounded-card border border-line bg-surface p-5 shadow-card">
        <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2">
          <span className="text-[15px] font-medium text-text">{title}</span>
          {subtitle && <span className="text-[13px] text-text-3">{subtitle}</span>}
        </figcaption>
        {legend && legend.length > 1 && <Legend keys={legend} />}
        <div className="mt-4">{children}</div>
      </div>
      {caption && <p className="mt-2 max-w-[90ch] text-[12px] leading-relaxed text-text-3">{caption}</p>}
    </figure>
  );
}

export function Legend({ keys }: { keys: string[] }) {
  return (
    <div className="mt-3 flex flex-wrap justify-end gap-x-5 gap-y-1">
      {keys.map((key) => (
        <span key={key} className="flex items-center gap-2 text-[13px] text-text-2">
          <span aria-hidden className="inline-block size-3 rounded-[3px]" style={{ background: seriesOf(key).color }} />
          {seriesOf(key).label}
        </span>
      ))}
    </div>
  );
}

export function DataTable({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr>{head.map((h) => <th key={h} className="pb-2 font-medium text-text-3">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {r.map((c, j) => <td key={j} className="py-2 font-mono tabular-nums text-text">{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const twoLines = (label: string): [string, string] => {
  const i = label.indexOf(" ");
  return i < 0 ? [label, ""] : [label.slice(0, i), label.slice(i + 1)];
};

/** Vertical grouped columns with a gridded y axis, value labels above each column, panel title on top. */
export function ColumnChart({ title, groups, yMax = 1, yTicks = [0, 0.25, 0.5, 0.75, 1], yFormat, yTitle, table }: { title?: string; groups: BarGroup[]; yMax?: number; yTicks?: number[]; yFormat: (v: number) => string; yTitle?: string; table?: boolean }) {
  if (table) return <DataTable head={["Group", "Series", "Value"]} rows={groups.flatMap((g) => g.bars.map((b) => [g.label, seriesOf(b.series).label, b.text]))} />;
  const W = 540, H = 320, L = 64, R = 12, T = title ? 44 : 24, B = 56;
  const plotH = H - T - B, plotW = W - L - R;
  const gw = plotW / Math.max(1, groups.length);
  const y = (v: number) => T + plotH - (Math.min(v, yMax) / yMax) * plotH;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title ?? "chart"} className="h-auto w-full">
      {title && <text x={L + plotW / 2} y={16} textAnchor="middle" fontSize={13} fontWeight={500} fill={INK}>{title}</text>}
      {yTicks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={GRID} />
          <text x={L - 8} y={y(t) + 4} textAnchor="end" fontSize={12} fill={MUTED} className="font-mono">{yFormat(t)}</text>
        </g>
      ))}
      <line x1={L} x2={L} y1={T} y2={T + plotH} stroke={MUTED} />
      <line x1={L} x2={W - R} y1={T + plotH} y2={T + plotH} stroke={MUTED} />
      {yTitle && <text transform={`translate(14 ${T + plotH / 2}) rotate(-90)`} textAnchor="middle" fontSize={12} fill={MUTED}>{yTitle}</text>}
      {groups.map((g, gi) => {
        const m = g.bars.length;
        const bw = Math.min(44, (gw * 0.78) / Math.max(1, m) - 4);
        const start = L + gi * gw + gw / 2 - (m * (bw + 4) - 4) / 2;
        const [l1, l2] = twoLines(g.label);
        return (
          <g key={g.label}>
            {g.bars.map((b, bi) => {
              const x = start + bi * (bw + 4);
              const top = y(b.value);
              return (
                <g key={b.series}>
                  <title>{b.detail ?? `${seriesOf(b.series).label}: ${b.text}`}</title>
                  <rect x={x} y={top} width={bw} height={Math.max(b.value > 0 ? 2 : 0, T + plotH - top)} rx={3} fill={seriesOf(b.series).color} />
                  <text x={x + bw / 2} y={top - 6} textAnchor="middle" fontSize={12} fill={INK} className="font-mono">{b.text}</text>
                </g>
              );
            })}
            <text x={L + gi * gw + gw / 2} y={T + plotH + 20} textAnchor="middle" fontSize={13} fontWeight={500} fill={INK}>{l1}</text>
            {l2 && <text x={L + gi * gw + gw / 2} y={T + plotH + 37} textAnchor="middle" fontSize={12} fill={MUTED}>{l2}</text>}
          </g>
        );
      })}
    </svg>
  );
}

/** Horizontal bars: bold row label with a muted sub-label on the left, value at the bar end, x axis below. */
export function HBarChart({ title, groups, xMax, xTicks, xFormat, xTitle, table }: { title?: string; groups: BarGroup[]; xMax: number; xTicks: number[]; xFormat: (v: number) => string; xTitle?: string; table?: boolean }) {
  if (table) return <DataTable head={["Row", "Series", "Value"]} rows={groups.flatMap((g) => g.bars.map((b) => [g.label, seriesOf(b.series).label, b.text]))} />;
  const W = 540, L = 150, R = 56, T = title ? 34 : 12, BH = 16, GAP = 4, PAD = 18;
  const heights = groups.map((g) => g.bars.length * (BH + GAP) - GAP + PAD);
  const plotH = heights.reduce((a, b) => a + b, 0);
  const H = T + plotH + 52;
  const plotW = W - L - R;
  const x = (v: number) => L + (Math.min(v, xMax) / xMax) * plotW;
  const offsets = heights.map((_, i) => T + heights.slice(0, i).reduce((a, b) => a + b, 0));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title ?? "chart"} className="h-auto w-full">
      {title && <text x={L + plotW / 2} y={16} textAnchor="middle" fontSize={13} fontWeight={500} fill={INK}>{title}</text>}
      {xTicks.filter((t) => t <= xMax).map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={T} y2={T + plotH} stroke={GRID} />
          <text x={x(t)} y={T + plotH + 18} textAnchor="middle" fontSize={12} fill={MUTED} className="font-mono">{xFormat(t)}</text>
        </g>
      ))}
      <line x1={L} x2={L} y1={T} y2={T + plotH} stroke={MUTED} />
      <line x1={L} x2={L + plotW} y1={T + plotH} y2={T + plotH} stroke={MUTED} />
      {xTitle && <text x={L + plotW / 2} y={T + plotH + 42} textAnchor="middle" fontSize={12} fill={MUTED}>{xTitle}</text>}
      {groups.map((g, gi) => {
        const top = offsets[gi] + PAD / 2;
        const mid = top + (g.bars.length * (BH + GAP) - GAP) / 2;
        return (
          <g key={g.label}>
            <text x={L - 12} y={g.sub ? mid - 2 : mid + 4} textAnchor="end" fontSize={13} fontWeight={500} fill={INK}>{g.label}</text>
            {g.sub && <text x={L - 12} y={mid + 14} textAnchor="end" fontSize={12} fill={MUTED}>{g.sub}</text>}
            {g.bars.map((b, bi) => (
              <g key={b.series}>
                <title>{b.detail ?? `${seriesOf(b.series).label}: ${b.text}`}</title>
                <rect x={L} y={top + bi * (BH + GAP)} width={Math.max(b.value > 0 ? 3 : 0, x(b.value) - L)} height={BH} rx={3} fill={seriesOf(b.series).color} />
                <text x={x(b.value) + 6} y={top + bi * (BH + GAP) + BH - 4} fontSize={12} fill={INK} className="font-mono">{b.text}</text>
              </g>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

export type LinePoint = { x: number; y: number };
export type LineSeries = { series: string; points: LinePoint[] };

/** Lines with round markers, gridded y axis with a title, x tick per data point, end-of-line value labels. */
export function LineChart({ title, lines, xTitle, yTitle, yFormat, yMax, table }: { title?: string; lines: LineSeries[]; xTitle: string; yTitle: string; yFormat: (v: number) => string; yMax?: number; table?: boolean }) {
  if (table) return <DataTable head={[xTitle, "Series", "Value"]} rows={lines.flatMap((l) => l.points.map((p) => [String(p.x), seriesOf(l.series).label, yFormat(p.y)]))} />;
  const W = 540, H = 320, L = 64, R = 44, T = title ? 44 : 24, B = 60;
  const xs = [...new Set(lines.flatMap((l) => l.points.map((p) => p.x)))].sort((a, b) => a - b);
  const top = yMax ?? Math.max(1e-9, ...lines.flatMap((l) => l.points.map((p) => p.y))) * 1.15;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => top * f);
  const px = (v: number) => L + (xs.length < 2 ? (W - L - R) / 2 : (xs.indexOf(v) / (xs.length - 1)) * (W - L - R));
  const py = (v: number) => T + (1 - v / top) * (H - T - B);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title ?? "chart"} className="h-auto w-full">
      {title && <text x={L + (W - L - R) / 2} y={16} textAnchor="middle" fontSize={13} fontWeight={500} fill={INK}>{title}</text>}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={L} x2={W - R} y1={py(t)} y2={py(t)} stroke={GRID} />
          <text x={L - 8} y={py(t) + 4} textAnchor="end" fontSize={12} fill={MUTED} className="font-mono">{yFormat(t)}</text>
        </g>
      ))}
      <line x1={L} x2={L} y1={T} y2={H - B} stroke={MUTED} />
      <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke={MUTED} />
      <text transform={`translate(14 ${(T + H - B) / 2}) rotate(-90)`} textAnchor="middle" fontSize={12} fill={MUTED}>{yTitle}</text>
      {xs.map((v) => (
        <text key={v} x={px(v)} y={H - B + 20} textAnchor="middle" fontSize={12} fill={MUTED} className="font-mono">{v}</text>
      ))}
      <text x={(L + W - R) / 2} y={H - 10} textAnchor="middle" fontSize={12} fill={MUTED}>{xTitle}</text>
      {lines.map((l) => (
        <g key={l.series}>
          <polyline fill="none" stroke={seriesOf(l.series).color} strokeWidth={2} strokeLinejoin="round" points={l.points.map((p) => `${px(p.x)},${py(p.y)}`).join(" ")} />
          {l.points.map((p) => (
            <circle key={p.x} cx={px(p.x)} cy={py(p.y)} r={5} fill={seriesOf(l.series).color} stroke="var(--surface)" strokeWidth={2}>
              <title>{`${seriesOf(l.series).label}, ${p.x} ${xTitle}: ${yFormat(p.y)}`}</title>
            </circle>
          ))}
        </g>
      ))}
    </svg>
  );
}
