"use client";

import { X } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { Button, HealthChip, SectionLabel } from "@/components/ui";
import { clock } from "@/lib/fmt";
import { useKea } from "@/lib/store";

const UNIT: Record<string, string> = { latency_p95_ms: " ms", memory_used_pct: " %" };
const LABEL: Record<string, string> = {
  latency_p95_ms: "latency p95",
  error_rate: "error rate",
  request_rate: "request rate",
  active_connections: "connections",
  memory_used_pct: "memory used",
};
const metricLabel = (metric: string) => LABEL[metric] ?? metric.replace(/_/g, " ");

/**
 * Floating detail card for the selected service. Subscribes to metricsLatest (the graph itself does
 * not), so live numbers update here without re-rendering the topology. Enters and leaves along the
 * same path (right edge), transform and opacity only.
 */
export function NodeDrawer() {
  const name = useKea((s) => s.selectedService);
  const select = useKea((s) => s.selectService);
  const topology = useKea((s) => s.topology);
  const health = useKea((s) => s.health);
  const anomalies = useKea((s) => s.anomalies);
  const deployments = useKea((s) => s.deployments);
  const metrics = useKea((s) => s.metricsLatest);
  const closeRef = useRef<HTMLButtonElement>(null);
  const open = name !== null;

  // keep the last service rendered while the drawer slides out
  const [last, setLast] = useState<string | null>(null);
  if (name && name !== last) setLast(name);
  const shown = name ?? last;

  useEffect(() => {
    if (!open) return;
    const before = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") select(null);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      before?.focus?.();
    };
  }, [open, select]);

  const def = topology?.services.find((s) => s.name === shown);
  const active = Object.values(anomalies).filter((a) => a.service === shown && a.state === "active");
  const recent = deployments.filter((e) => e.service === shown).slice(-3).reverse();
  const values = Object.values(metrics).filter((m) => m.service === shown);

  return (
    <aside
      aria-label="Service details"
      aria-hidden={!open}
      inert={!open}
      className="absolute bottom-3 right-3 top-2 z-10 flex w-[280px] flex-col rounded-card border border-line bg-surface shadow-card"
      style={{
        transform: open ? "translateX(0)" : "translateX(calc(100% + 16px))",
        opacity: open ? 1 : 0,
        transition: "transform 200ms var(--ease-drawer), opacity 200ms var(--ease-drawer)",
      }}
    >
      <div className="flex items-start justify-between gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0 space-y-1">
          <h2 className="truncate text-[15px] font-medium text-text">{shown}</h2>
          <p className="text-[12px] text-text-3">{def ? `${def.kind}, ${def.tier.replace("_", " ")}` : ""}</p>
          <HealthChip health={(shown && health[shown]) || def?.health || "healthy"} />
        </div>
        <Button ref={closeRef} variant="ghost" size="icon" aria-label="Close details" onClick={() => select(null)}>
          <X size={16} weight="bold" />
        </Button>
      </div>

      <div className="scroll-quiet flex min-h-0 flex-1 flex-col divide-y divide-line overflow-y-auto">
        <section className="flex flex-col gap-1.5 px-4 py-3">
          <SectionLabel>Active anomalies</SectionLabel>
          {active.length === 0 ? (
            <p className="text-[13px] text-text-3">No active anomalies.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {active.map((a) => (
                <li key={a.anomaly_id} className="text-[13px] text-text">
                  {metricLabel(a.metric)} <span className="num text-warn">{a.ratio.toFixed(1)}x</span> baseline
                  <span className="block text-[12px] text-text-3">
                    since <span className="num">{clock(a.onset_ts)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="flex flex-col gap-1.5 px-4 py-3">
          <SectionLabel>Recent deployments</SectionLabel>
          {recent.length === 0 ? (
            <p className="text-[13px] text-text-3">No recent deployments.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {recent.map((e) => (
                <li key={e.event_id} className="text-[13px] text-text">
                  <span className="num">{String(e.payload.deployment_id ?? "")}</span>
                  {e.kind === "rollback" ? <span className="text-ok"> rolled back</span> : ` ${String(e.payload.version ?? "")}`}
                  <span className="block text-[12px] text-text-3">
                    <span className="num">{clock(e.ts)}</span>
                    {e.kind === "deployment" && e.payload.summary ? `, ${String(e.payload.summary)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="flex flex-col gap-1.5 px-4 py-3">
          <SectionLabel>Latest metrics</SectionLabel>
          {values.length === 0 ? (
            <p className="text-[13px] text-text-3">No metrics yet.</p>
          ) : (
            <dl className="flex flex-col gap-1.5">
              {values.map((m) => (
                <div key={m.metric} className="flex items-baseline justify-between gap-3 text-[13px]">
                  <dt className="text-text-2">{metricLabel(m.metric)}</dt>
                  <dd className="num text-text">
                    {Number(m.value.toPrecision(3))}
                    {UNIT[m.metric] ?? ""}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      </div>
    </aside>
  );
}
