"use client";

import { CaretDown, CaretRight, Prohibit } from "@phosphor-icons/react";
import { useState } from "react";
import type { RejectedCandidate } from "@/lib/types";

/** Rejected candidates are a differentiator, so they are shown (expanded when few), never buried. */
export function RejectedList({ items }: { items: RejectedCandidate[] }) {
  const [open, setOpen] = useState(items.length <= 3);
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="rejected-heading">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="rejected-list"
        onClick={() => setOpen((v) => !v)}
        className="pressable flex w-full items-center gap-1.5 rounded-control text-left"
      >
        {open ? <CaretDown size={13} weight="bold" aria-hidden /> : <CaretRight size={13} weight="bold" aria-hidden />}
        <h3 id="rejected-heading" className="text-[12px] font-medium text-text-3">
          Rejected candidates <span className="num">({items.length})</span>
        </h3>
      </button>
      {open && (
        <ul id="rejected-list" className="mt-2.5 space-y-2">
          {items.map((item) => (
            <li key={item.candidate_id} className="grid grid-cols-[28px_minmax(0,1fr)] items-start gap-x-2.5 rounded-lg border border-line px-3 py-2.5">
              <span aria-hidden className="grid h-7 w-7 place-items-center rounded-md bg-surface-2 text-text-3">
                <Prohibit size={14} weight="bold" />
              </span>
              <span className="min-w-0 self-center text-[13px] leading-snug text-text-2">{item.statement}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
