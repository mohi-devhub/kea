"use client";

import { Badge } from "@/components/ui";
import { REASON_TEXT } from "@/lib/fmt";
import type { WhatChanged as WhatChangedData } from "@/lib/types";

/** The headline question of an incident: a soft callout, the most prominent block on the panel. */
export function WhatChanged({ data }: { data: WhatChangedData }) {
  return (
    <section aria-labelledby="what-changed" className="rounded-lg bg-surface-2 p-3.5">
      <h3 id="what-changed" className="text-[13px] font-medium text-text-2">
        What changed?
      </h3>
      <p className="mt-1.5 text-[14px] leading-relaxed text-text">{data.statement}</p>
      {data.changes.length > 0 && (
        <ul className="mt-3 space-y-2.5 border-t border-line pt-3">
          {data.changes.map((change) => (
            <li key={`${change.deployment_id}-${change.ts}`} className="grid grid-cols-[112px_minmax(0,1fr)] items-baseline gap-x-2.5">
              <Badge tone={change.relevant ? "accent" : "neutral"} className="justify-self-start whitespace-nowrap">
                {change.relevant ? "relevant" : "not relevant"}
              </Badge>
              <span className="min-w-0 text-[13px] leading-snug text-text">
                Deployment <span className="num">{change.deployment_id}</span> on {change.service},{" "}
                <span className="num">{change.seconds_before_onset}s</span> before onset
                {!change.relevant && change.reason && (
                  <span className="mt-0.5 block text-[12px] text-text-2">
                    Ruled out because {REASON_TEXT[change.reason] ?? change.reason.toLowerCase().replace(/_/g, " ")}.
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
