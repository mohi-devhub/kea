"use client";

import { BaseEdge, getBezierPath, type Edge, type EdgeProps } from "@xyflow/react";

export type KeaEdgeData = {
  blocking: boolean;
  state: "normal" | "path" | "dim";
  order: number;
};
export type KeaEdgeType = Edge<KeaEdgeData, "kea">;

/** Arrowheads for both edge states. Filled through style so theme variables resolve. */
export function ArrowDefs() {
  return (
    <svg aria-hidden className="pointer-events-none absolute h-0 w-0">
      <defs>
        {[
          ["kea-arrow", "var(--text-3)"],
          ["kea-arrow-path", "var(--accent)"],
        ].map(([id, fill]) => (
          <marker key={id} id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,1 L9,5 L0,9 z" style={{ fill }} />
          </marker>
        ))}
      </defs>
    </svg>
  );
}

/** Blocking calls are solid, non-blocking calls are dashed. Path edges pulse root to symptom. */
export function KeaEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps<KeaEdgeType>) {
  const [path] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });
  const state = data?.state ?? "normal";
  const onPath = state === "path";
  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={`url(#${onPath ? "kea-arrow-path" : "kea-arrow"})`}
      className={onPath ? "kea-pulse" : undefined}
      style={{
        stroke: onPath ? "var(--accent)" : "var(--text-3)",
        strokeWidth: onPath ? 2.5 : 1.5,
        strokeDasharray: data?.blocking === false ? "5 4" : undefined,
        opacity: state === "dim" ? 0.22 : onPath ? 1 : 0.75,
        animationDelay: onPath ? `${(data?.order ?? 0) * 220}ms` : undefined,
        transition: "opacity 200ms var(--ease-out), stroke 200ms var(--ease-out)",
      }}
    />
  );
}
