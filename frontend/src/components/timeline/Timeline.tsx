"use client";

import {
  ArrowDown,
  ArrowUUpLeft,
  Crosshair,
  Heartbeat,
  ListBullets,
  Pulse,
  RocketLaunch,
  Siren,
  Terminal,
  type Icon,
} from "@phosphor-icons/react";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { CardHeader, cx, EmptyState } from "@/components/ui";
import { clock } from "@/lib/fmt";
import { TIMELINE_KINDS, useKea, type TimelineItem, type TimelineKind, type Tone } from "@/lib/store";

const KIND: Record<TimelineKind, { label: string; Icon: Icon }> = {
  deployment: { label: "Deployments", Icon: RocketLaunch },
  rollback: { label: "Rollbacks", Icon: ArrowUUpLeft },
  anomaly: { label: "Anomalies", Icon: Pulse },
  health: { label: "Health", Icon: Heartbeat },
  incident: { label: "Incidents", Icon: Siren },
  log: { label: "Logs", Icon: Terminal },
  prediction: { label: "Predictions", Icon: Crosshair },
};
// Tone is icon plus tint plus a screen-reader word, never color alone.
const TONE_CHIP: Record<Tone, string> = {
  neutral: "bg-surface-2 text-text-2",
  ok: "bg-ok-bg text-ok",
  warn: "bg-warn-bg text-warn",
  bad: "bg-bad-bg text-bad",
};
const STICK_PX = 24;

const Row = memo(function Row({ row }: { row: TimelineItem }) {
  const setHighlight = useKea((s) => s.setHighlight);
  const selectService = useKea((s) => s.selectService);
  const { Icon, label } = KIND[row.kind];
  const body = (
    <>
      <span className="num w-[62px] shrink-0 text-[12px] text-text-3">{clock(row.ts)}</span>
      <span aria-hidden className={cx("grid h-6 w-6 shrink-0 place-items-center rounded-full", TONE_CHIP[row.tone])}>
        <Icon size={13} weight="bold" />
      </span>
      <span className="min-w-0 flex-1 truncate text-[13px] text-text" title={row.statement}>
        <span className="sr-only">{label}: </span>
        {row.statement}
      </span>
      {row.service && (
        <span className="num shrink-0 rounded-md border border-line px-1.5 py-0.5 text-[11px] text-text-2">{row.service}</span>
      )}
    </>
  );
  const base = "flex h-[38px] w-full items-center gap-3 px-4 text-left";
  if (!row.service) return <li className={base}>{body}</li>;
  const service = row.service;
  return (
    <li>
      <button
        type="button"
        className={`${base} [@media(hover:hover)]:hover:bg-surface-2`}
        onMouseEnter={() => setHighlight([service])}
        onMouseLeave={() => setHighlight([])}
        onFocus={() => setHighlight([service])}
        onBlur={() => setHighlight([])}
        onClick={() => {
          setHighlight([service]);
          selectService(service);
        }}
      >
        {body}
      </button>
    </li>
  );
});

/** Events in sim-time order, newest at the bottom. Sticks to the newest row unless scrolled up. */
export function Timeline() {
  const timeline = useKea((s) => s.timeline);
  const filters = useKea((s) => s.filters);
  const toggleFilter = useKea((s) => s.toggleFilter);
  const run = useKea((s) => s.run);
  const scroller = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  const rows = useMemo(
    () => timeline.filter((t) => filters[t.kind]).sort((a, b) => a.ts - b.ts || a.id.localeCompare(b.id, "en", { numeric: true })),
    [timeline, filters],
  );

  useEffect(() => {
    const el = scroller.current;
    if (el && pinned) el.scrollTop = el.scrollHeight;
  }, [rows.length, pinned]);

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    setPinned(el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX);
  };

  const jump = () => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
    setPinned(true);
  };

  const empty = !timeline.length
    ? run
      ? "Run started. Events appear here as they happen."
      : "Waiting for a run. Pick a scenario and press Start."
    : rows.length === 0
      ? "No events match the current filters."
      : null;

  return (
    <div className="relative flex h-full flex-col">
      <div className="shrink-0 border-b border-line pb-3">
        <CardHeader
          icon={<ListBullets size={20} weight="bold" />}
          title="Timeline"
          right={
            <div role="group" aria-label="Filter timeline" className="flex items-center gap-0.5">
              {TIMELINE_KINDS.map((k) => {
                const { Icon, label } = KIND[k];
                const on = filters[k];
                return (
                  <button
                    key={k}
                    type="button"
                    aria-pressed={on}
                    aria-label={label}
                    title={label}
                    onClick={() => toggleFilter(k)}
                    className={cx(
                      "pressable grid h-8 w-8 place-items-center rounded-lg",
                      on ? "bg-surface-2 text-text" : "text-text-3 [@media(hover:hover)]:hover:text-text-2",
                    )}
                  >
                    <Icon size={15} weight="bold" aria-hidden />
                  </button>
                );
              })}
            </div>
          }
        />
      </div>

      <div ref={scroller} onScroll={onScroll} className="scroll-quiet min-h-0 flex-1 overflow-y-auto py-1">
        {empty ? <EmptyState>{empty}</EmptyState> : <ol>{rows.map((row) => <Row key={row.id} row={row} />)}</ol>}
      </div>

      {!pinned && rows.length > 0 && (
        <button
          type="button"
          onClick={jump}
          className="pressable absolute bottom-3 right-4 inline-flex h-8 items-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-[12px] font-medium text-text shadow-card [@media(hover:hover)]:hover:bg-surface-2"
        >
          <ArrowDown size={12} weight="bold" aria-hidden />
          Jump to latest
        </button>
      )}
    </div>
  );
}
