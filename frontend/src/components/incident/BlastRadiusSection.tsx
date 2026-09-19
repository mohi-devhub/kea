"use client";

import { Check, Copy } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui";
import { useKea } from "@/lib/store";
import type { Incident } from "@/lib/types";

/** Customer impact summary, plus the live Neo4j result and the exact Cypher once "Blast radius" ran. */
export function BlastRadiusSection({ incident }: { incident: Incident }) {
  const blast = useKea((s) => s.blast);
  const setHighlight = useKea((s) => s.setHighlight);
  const [showCypher, setShowCypher] = useState(false);
  const [copied, setCopied] = useState(false);
  const facing = incident.blast_radius.customer_facing_affected;

  const copy = async () => {
    if (!blast) return;
    try {
      await navigator.clipboard.writeText(blast.cypher);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section aria-labelledby="blast-heading">
      <h3 id="blast-heading" className="text-[12px] font-medium text-text-3">
        Blast radius
      </h3>
      <p className="mt-2 text-[13px] leading-snug text-text">
        {facing.length > 0 ? (
          <>
            Customer-facing services affected: <span className="num font-medium">{facing.join(", ")}</span>
          </>
        ) : (
          "No customer-facing service is affected so far."
        )}
        <span className="mt-0.5 block text-[12px] text-text-2">
          {incident.blast_radius.services.length} services with anomalies in this incident.
        </span>
      </p>

      {blast ? (
        <div className="mt-3 space-y-3">
          {blast.callers.length > 0 ? (
            <ul className="flex flex-wrap gap-1.5" aria-label={`Services that reach ${blast.root_service ?? "the root"} through blocking calls`}>
              {blast.callers.map((c) => (
                <li key={c.service}>
                  <button
                    type="button"
                    onPointerEnter={() => setHighlight([c.service])}
                    onPointerLeave={() => setHighlight([])}
                    onFocus={() => setHighlight([c.service])}
                    onBlur={() => setHighlight([])}
                    className="pressable num rounded-md border border-line bg-surface-2 px-2 py-1 text-[12px] text-text-2 [@media(hover:hover)]:hover:text-text"
                  >
                    {c.service}
                    {c.customer_facing ? " (customer-facing)" : ""}, {c.hops} {c.hops === 1 ? "hop" : "hops"}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12px] text-text-2">No upstream callers were returned for {blast.root_service ?? "the root cause"}.</p>
          )}
          <div>
            <Button variant="ghost" className="-ml-2 h-8 px-2 text-[12px]" aria-expanded={showCypher} onClick={() => setShowCypher((v) => !v)}>
              {showCypher ? "Hide Cypher query" : "Show Cypher query"}
            </Button>
            {showCypher && (
              <div className="mt-2 overflow-hidden rounded-lg border border-line bg-surface-2">
                <div className="flex items-center justify-between border-b border-line px-3 py-1.5">
                  <span className="text-[12px] text-text-3">Cypher</span>
                  <Button variant="ghost" className="h-7 px-2 text-[12px]" onClick={copy} aria-label="Copy Cypher query">
                    {copied ? <Check size={12} weight="bold" aria-hidden /> : <Copy size={12} weight="bold" aria-hidden />}
                    {copied ? "Copied" : "Copy"}
                  </Button>
                </div>
                <pre className="num scroll-quiet overflow-x-auto whitespace-pre-wrap px-3 py-2.5 text-[12px] leading-relaxed text-text">{blast.cypher}</pre>
                {Object.keys(blast.parameters).length > 0 && (
                  <pre className="num border-t border-line px-3 py-2 text-[12px] text-text-2">
                    {`parameters: ${JSON.stringify(blast.parameters)}`}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-2 text-[12px] text-text-3">Run the blast radius query to see which services reach the root cause.</p>
      )}
    </section>
  );
}
