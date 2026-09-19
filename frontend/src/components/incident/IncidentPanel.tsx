"use client";

import { type KeyboardEvent, useRef } from "react";
import { EmptyState } from "@/components/ui";
import { type Tab, useKea } from "@/lib/store";
import { OverviewTab } from "./OverviewTab";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "investigate", label: "Investigate" },
  { id: "fix", label: "Fix" },
];

/** Tabbed incident panel. Tab switches are instant on purpose: they are frequent and keyboard driven. */
export function IncidentPanel() {
  const tab = useKea((s) => s.tab);
  const setTab = useKea((s) => s.setTab);
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const index = TABS.findIndex((t) => t.id === tab);
    const next =
      e.key === "ArrowRight" ? (index + 1) % TABS.length : e.key === "ArrowLeft" ? (index - 1 + TABS.length) % TABS.length : e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : -1;
    if (next < 0) return;
    e.preventDefault();
    setTab(TABS[next].id);
    refs.current[TABS[next].id]?.focus();
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div role="tablist" aria-label="Incident views" onKeyDown={onKeyDown} className="flex shrink-0 gap-1 border-b border-line px-3 pt-2">
        {TABS.map((t) => {
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              ref={(el) => {
                refs.current[t.id] = el;
              }}
              id={`tab-${t.id}`}
              role="tab"
              type="button"
              aria-selected={active}
              aria-controls={`panel-${t.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => setTab(t.id)}
              className={`-mb-px rounded-t-control border-b-2 px-3 py-2 text-[13px] font-medium transition-colors duration-150 ${
                active ? "border-accent text-text" : "border-transparent text-text-3 [@media(hover:hover)]:hover:text-text"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <div
        id={`panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`tab-${tab}`}
        tabIndex={0}
        className="scroll-quiet min-h-0 flex-1 overflow-y-auto p-4"
      >
        {tab === "overview" && <OverviewTab />}
        {tab === "investigate" && <EmptyState>The investigation agent is not enabled in this build.</EmptyState>}
        {tab === "fix" && <EmptyState>No fix proposal available yet.</EmptyState>}
      </div>
    </div>
  );
}
