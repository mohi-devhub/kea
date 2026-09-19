"use client";

import { Warning } from "@phosphor-icons/react";
import { Badge } from "@/components/ui";
import { clock } from "@/lib/fmt";
import type { Incident } from "@/lib/types";
import { fixed } from "./util";

export function IncidentHeader({ incident }: { incident: Incident }) {
  const resolved = incident.state === "resolved";
  const count = incident.blast_radius.services.length;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="num text-[16px] font-medium text-text">{incident.incident_id}</span>
        <Badge tone={resolved ? "ok" : "bad"}>{incident.state}</Badge>
        <span className="num text-[12px] text-text-3">rev {incident.revision}</span>
      </div>
      <p className="mt-1 text-[12px] text-text-2">
        Opened <span className="num text-text">{clock(incident.opened_ts)}</span>
        {resolved && incident.resolved_ts !== null && incident.resolved_ts !== undefined && (
          <>
            , resolved <span className="num text-text">{clock(incident.resolved_ts)}</span>
          </>
        )}
        , <span className="num text-text">{count}</span> {count === 1 ? "service" : "services"} affected
      </p>
      {incident.ambiguous && (
        <div role="status" className="mt-3 flex items-start gap-2 rounded-control border border-transparent bg-warn-bg px-3 py-2 text-[13px] text-warn">
          <Warning size={16} weight="bold" aria-hidden className="mt-0.5 shrink-0" />
          <span>
            Multiple plausible hypotheses. The top two scores are only <span className="num">{fixed(incident.margin)}</span> apart.
          </span>
        </div>
      )}
    </div>
  );
}
