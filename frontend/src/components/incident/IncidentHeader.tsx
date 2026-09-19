"use client";

import { Warning } from "@phosphor-icons/react";
import { clock } from "@/lib/fmt";
import type { Incident } from "@/lib/types";
import { fixed } from "./util";

/** Meta line under the card header (id and state live in the header), plus the ambiguity banner. */
export function IncidentHeader({ incident }: { incident: Incident }) {
  const resolved = incident.state === "resolved";
  const count = incident.blast_radius.services.length;
  return (
    <div>
      <p className="text-[13px] leading-relaxed text-text-2">
        Opened <span className="num text-text">{clock(incident.opened_ts)}</span>
        {resolved && incident.resolved_ts !== null && incident.resolved_ts !== undefined && (
          <>
            , resolved <span className="num text-text">{clock(incident.resolved_ts)}</span>
          </>
        )}
        , <span className="num text-text">{count}</span> {count === 1 ? "service" : "services"} affected, revision{" "}
        <span className="num text-text">{incident.revision}</span>.
      </p>
      {incident.ambiguous && (
        <div role="status" className="mt-3 flex items-start gap-2 rounded-lg bg-warn-bg px-3 py-2.5 text-[13px] text-warn">
          <Warning size={16} weight="bold" aria-hidden className="mt-0.5 shrink-0" />
          <span>
            Multiple plausible hypotheses. The top two scores are only <span className="num">{fixed(incident.margin)}</span> apart.
          </span>
        </div>
      )}
    </div>
  );
}
