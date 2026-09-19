"use client";

import { Badge } from "@/components/ui";
import { REASON_TEXT } from "@/lib/fmt";
import type { WhatChanged as WhatChangedData } from "@/lib/types";

/** The headline question of an incident. Deliberately the most prominent block on the panel. */
export function WhatChanged({ data }: { data: WhatChangedData }) {
  return (
    <section aria-labelledby="what-changed" className="rounded-card border border-line-strong bg-surface-2 p-4">
      <h3 id="what-changed" className="text-[12px] font-medium text-text-3">
        What changed?
      </h3>
      <p className="mt-1.5 text-[14px] leading-relaxed text-text">{data.statement}</p>
      {data.changes.length > 0 && (
        <ul className="mt-3 space-y-2 border-t border-line pt-3">
          {data.changes.map((change) => (
            <li key={`${change.deployment_id}-${change.ts}`} className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-2">
              <Badge tone={change.relevant ? "accent" : "neutral"}>{change.relevant ? "relevant" : "not relevant"}</Badge>
              <span className="min-w-0 text-[13px] text-text">
                Deployment <span className="num">{change.deployment_id}</span> on {change.service},{" "}
                <span className="num">{change.seconds_before_onset}s</span> before onset
                {!change.relevant && change.reason && (
                  <span className="block text-[12px] text-text-2">
                    Ruled out: {REASON_TEXT[change.reason] ?? change.reason.toLowerCase().replace(/_/g, " ")}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
