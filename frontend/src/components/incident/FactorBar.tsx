"use client";

import { useState } from "react";
import { FACTOR_LABEL } from "@/lib/fmt";
import type { Candidate, Factor } from "@/lib/types";
import { FACTOR_COLOR, FACTOR_ORDER, type FactorKey, fixed } from "./util";

type Row = { key: FactorKey; factor: Factor };

/**
 * Factor breakdown: one thin stacked bar, segment width = that factor's contribution, so the bar
 * length is the score on a 0 to 1 scale. Fixed factor order and colors (validated in DESIGN.md),
 * 2px surface gaps, rounded outer ends. Every segment also has a labeled row underneath because the
 * light-theme aqua and yellow are under 3:1 contrast: identity never depends on color alone.
 */
export function FactorBar({ candidate }: { candidate: Candidate }) {
  const [active, setActive] = useState<number | null>(null);
  const rows: Row[] = [];
  for (const key of FACTOR_ORDER) {
    const factor = candidate.factors[key];
    if (factor) rows.push({ key, factor });
  }
  const total = rows.reduce((sum, r) => sum + r.factor.contribution, 0);
  const tip = active === null ? null : rows[active];

  return (
    <div>
      <div className="relative">
        <div
          role="group"
          aria-label={`Score ${fixed(candidate.score)} from four factors`}
          className="h-2 rounded-[4px] bg-surface-2"
          onPointerLeave={() => setActive(null)}
        >
          <div className="flex h-full gap-[2px]" style={{ width: `${Math.min(100, candidate.score * 100)}%` }}>
            {rows.map((r, i) => (
              <span
                key={r.key}
                tabIndex={0}
                role="img"
                aria-label={`${FACTOR_LABEL[r.key]}: ${fixed(r.factor.contribution, 4)}`}
                className={`min-w-[2px] transition-opacity duration-150 ${i === 0 ? "rounded-l-[4px]" : ""} ${i === rows.length - 1 ? "rounded-r-[4px]" : ""}`}
                style={{
                  flex: `${r.factor.contribution} 0 0`,
                  background: FACTOR_COLOR[r.key],
                  opacity: active === null || active === i ? 1 : 0.35,
                }}
                onPointerEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
              />
            ))}
          </div>
        </div>
        <div
          role="tooltip"
          aria-hidden={!tip}
          className={`num pointer-events-none absolute -top-8 left-0 z-10 rounded-control border border-line-strong bg-surface-2 px-2 py-1 text-[11px] whitespace-nowrap text-text transition-opacity duration-150 ${tip ? "opacity-100" : "opacity-0"}`}
        >
          {tip && `${FACTOR_LABEL[tip.key]}: ${fixed(tip.factor.value)} x ${fixed(tip.factor.weight)} = ${fixed(tip.factor.contribution, 4)}`}
        </div>
      </div>

      <ul className="mt-3 space-y-2">
        {rows.map((r, i) => (
          <li
            key={r.key}
            className={`grid grid-cols-[8px_minmax(0,1fr)_auto] items-baseline gap-x-2 transition-opacity duration-150 ${active === null || active === i ? "opacity-100" : "opacity-50"}`}
            onPointerEnter={() => setActive(i)}
            onPointerLeave={() => setActive(null)}
          >
            <span aria-hidden className="h-2 w-2 self-start rounded-[2px]" style={{ background: FACTOR_COLOR[r.key], marginTop: 4 }} />
            <span className="min-w-0">
              <span className="text-[13px] font-medium text-text">{FACTOR_LABEL[r.key]}</span>
              <span className="block text-[12px] leading-snug text-text-2">{r.factor.explanation}</span>
            </span>
            <span className="num text-[12px] whitespace-nowrap text-text-2">
              {fixed(r.factor.value)} x {fixed(r.factor.weight)} = <span className="text-text">{fixed(r.factor.contribution, 4)}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 flex justify-between border-t border-line pt-2 text-[12px] text-text-2">
        <span>Sum of contributions</span>
        <span className="num text-text">{fixed(total, 4)}</span>
      </p>
    </div>
  );
}
