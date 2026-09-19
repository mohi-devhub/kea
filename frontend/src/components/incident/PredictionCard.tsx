"use client";

import { CheckCircle, Warning, XCircle } from "@phosphor-icons/react";
import { Badge, type BadgeTone } from "@/components/ui";
import { useKea } from "@/lib/store";
import { labelFromCandidateId } from "./util";

const OUTCOME = {
  healed_as_predicted: { Icon: CheckCircle, tone: "text-ok", text: "Healed as predicted" },
  unchanged_as_predicted: { Icon: CheckCircle, tone: "text-ok", text: "Unchanged as predicted" },
  missed_heal: { Icon: XCircle, tone: "text-bad", text: "Missed heal" },
  unexpected_heal: { Icon: Warning, tone: "text-warn", text: "Unexpected heal" },
} as const;

const VERDICT: Record<string, BadgeTone> = {
  confirmed: "ok",
  partial: "warn",
  refuted: "bad",
  inconclusive: "neutral",
};

function ServiceList({ label, services }: { label: string; services: string[] }) {
  return (
    <div className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] items-baseline gap-x-2 text-[13px]">
      <span className="text-text-2">{label}</span>
      <span className="num text-text">{services.length > 0 ? services.join(", ") : "none"}</span>
    </div>
  );
}

/** Predict, then verify. The prediction is made before recovery and never edited afterwards. */
export function PredictionCard() {
  const prediction = useKea((s) => s.prediction);
  const verification = useKea((s) => s.verification);
  if (!prediction) return null;

  const verb = prediction.candidate_id.startsWith("deployment:") ? "rolled back" : "remediated";
  const subject = labelFromCandidateId(prediction.candidate_id);
  const heading = prediction.frozen ? "Prediction recorded before recovery" : "Prediction preview";

  return (
    <section aria-labelledby="prediction-heading">
      <div className="flex items-center gap-2">
        <h3 id="prediction-heading" className="text-[12px] font-medium text-text-3">
          {heading}
        </h3>
        {prediction.low_margin && <Badge tone="warn">low margin</Badge>}
        {verification && <Badge tone={VERDICT[verification.verdict] ?? "neutral"}>{verification.verdict}</Badge>}
      </div>
      <p className="mt-1.5 text-[13px] text-text">
        If <span className="font-medium">{subject}</span> is {verb}, these services should heal.
      </p>
      <div className="mt-2 space-y-1">
        <ServiceList label="Should heal:" services={prediction.predicted_healed} />
        <ServiceList label="Should stay unchanged:" services={prediction.predicted_unchanged} />
      </div>

      {verification && (
        <ul className="mt-3 divide-y divide-line rounded-control border border-line" aria-label="Predicted versus actual">
          {verification.outcomes.map((o) => {
            const meta = OUTCOME[o.outcome as keyof typeof OUTCOME];
            const expected = prediction.predicted_healed.includes(o.service) ? "Should heal" : "Should stay";
            return (
              <li key={o.service} className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 px-3 py-1.5 text-[13px]">
                <span className="num text-text">{o.service}</span>
                <span className="text-[12px] text-text-3">{expected}</span>
                {meta ? (
                  <span className={`inline-flex items-center gap-1 text-[12px] font-medium ${meta.tone}`}>
                    <meta.Icon size={14} weight="bold" aria-hidden />
                    {meta.text}
                  </span>
                ) : (
                  <span className="text-[12px] text-text-2">{o.outcome}</span>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-2 text-[12px] text-text-3">
        In simulation, recovery is scripted; this checks consistency, not real-world proof.
      </p>
    </section>
  );
}
