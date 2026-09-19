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
        <ul id="rejected-list" className="mt-2 space-y-2">
          {items.map((item) => (
            <li key={item.candidate_id} className="grid grid-cols-[16px_minmax(0,1fr)] gap-x-2 text-[13px]">
              <Prohibit size={14} weight="bold" aria-hidden className="mt-0.5 text-text-3" />
              <span className="min-w-0 text-text-2">{item.statement}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
