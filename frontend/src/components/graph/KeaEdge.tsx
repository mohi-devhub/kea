"use client";

import { BaseEdge, getBezierPath, type Edge, type EdgeProps } from "@xyflow/react";
import { useReducedMotion } from "@/components/graph/hoverStore";

export type KeaEdgeData = {
  blocking: boolean;
  state: "normal" | "hover" | "path" | "dim";
  order: number;
};
export type KeaEdgeType = Edge<KeaEdgeData, "kea">;

const MARKERS = [
  ["kea-arrow", "var(--text-3)"],
  ["kea-arrow-accent", "var(--accent)"],
] as const;

/** Small arrowheads for both colors. Filled through style so theme variables resolve. */
export function ArrowDefs() {
  return (
    <svg aria-hidden className="pointer-events-none absolute h-0 w-0">
      <defs>
        {MARKERS.map(([id, fill]) => (
          <marker key={id} id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,1.5 L9,5 L0,8.5 z" style={{ fill }} />
          </marker>
        ))}
      </defs>
    </svg>
  );
}

const LOOK = {
  normal: { stroke: "var(--text-3)", width: 1.25, opacity: 0.5 },
  hover: { stroke: "var(--accent)", width: 1.75, opacity: 1 },
  path: { stroke: "var(--accent)", width: 2, opacity: 1 },
  dim: { stroke: "var(--text-3)", width: 1.25, opacity: 0.16 },
} as const;

/** Thin bezier. Blocking calls are solid, non-blocking dashed. Path edges pulse root to symptom. */
export function KeaEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }: EdgeProps<KeaEdgeType>) {
  const reduced = useReducedMotion();
  const [path] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, curvature: 0.3 });
  const state = data?.state ?? "normal";
  const look = LOOK[state];
  const accent = state === "hover" || state === "path";
  return (
    <BaseEdge
      id={id}
      path={path}
      markerEnd={`url(#${accent ? "kea-arrow-accent" : "kea-arrow"})`}
      className={state === "path" && !reduced ? "kea-pulse" : undefined}
      style={{
        stroke: look.stroke,
        strokeWidth: look.width,
        strokeDasharray: data?.blocking === false ? "4 4" : undefined,
        strokeLinecap: "round",
        opacity: look.opacity,
        animationDelay: state === "path" ? `${(data?.order ?? 0) * 220}ms` : undefined,
        transition: "opacity 150ms var(--ease-out), stroke 150ms var(--ease-out), stroke-width 150ms var(--ease-out)",
      }}
    />
  );
}
