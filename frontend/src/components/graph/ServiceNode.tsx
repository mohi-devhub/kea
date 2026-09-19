"use client";

import { CheckCircle, GitCommit, Warning, XCircle } from "@phosphor-icons/react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import { useHover, useReducedMotion } from "@/components/graph/hoverStore";
import { cx } from "@/components/ui";
import { useKea } from "@/lib/store";
import type { Health, ServiceNode as ServiceDef } from "@/lib/types";

export type ServiceNodeData = {
  name: string;
  kind: ServiceDef["kind"];
  customerFacing: boolean;
  health: Health;
  size: number;
  labelAbove: boolean;
  dim: boolean;
  neighbour: boolean;
  pathIndex: number | null;
  blast: boolean;
  highlighted: boolean;
  selected: boolean;
  deployment: { id: string; rolledBack: boolean; root: boolean } | null;
};
export type ServiceNodeType = Node<ServiceNodeData, "service">;

const FILL: Record<Health, string> = {
  healthy: "var(--ok-fill)",
  degraded: "var(--warn-fill)",
  failing: "var(--bad-fill)",
};
const HALO: Record<Health, number> = { healthy: 16, degraded: 24, failing: 30 };
const WORD: Record<Health, string> = { healthy: "text-ok", degraded: "text-warn", failing: "text-bad" };
const ICON = { healthy: CheckCircle, degraded: Warning, failing: XCircle } as const;
const hidden = { opacity: 0, pointerEvents: "none" } as const;
const SIDES = [
  ["left", Position.Left],
  ["right", Position.Right],
  ["top", Position.Top],
  ["bottom", Position.Bottom],
] as const;

/** A ring drawn around the dot (selection, highlight, path, blast radius). */
function Ring({ inset, className, style }: { inset: number; className: string; style?: React.CSSProperties }) {
  return <span aria-hidden className={cx("pointer-events-none absolute rounded-full", className)} style={{ inset: -inset, ...style }} />;
}

/** One service as a halo dot. Health is the fill (color), the icon inside, and the word beneath. */
function ServiceNodeView({ data }: NodeProps<ServiceNodeType>) {
  const reduced = useReducedMotion();
  const selectService = useKea((s) => s.selectService);
  const setHover = useHover((s) => s.set);
  const Icon = ICON[data.health];
  const fill = FILL[data.health];
  const halo = HALO[data.health];
  const label = `${data.name}, ${data.health}${data.customerFacing ? ", customer-facing" : ""}`;

  const text = (
    <span
      className={cx(
        "pointer-events-none absolute left-1/2 flex -translate-x-1/2 flex-col items-center gap-0.5 whitespace-nowrap rounded-lg bg-surface/90 px-1.5 py-0.5 text-center",
        data.labelAbove ? "bottom-full mb-[10px]" : "top-full mt-[10px]",
      )}
    >
      <span className="text-[13px] font-medium leading-tight text-text">{data.name}</span>
      <span className="flex items-center gap-1.5">
        <span className={cx("text-[11px] leading-tight", WORD[data.health])}>{data.health}</span>
        {data.deployment && (
          <span
            className={cx(
              "num inline-flex items-center gap-0.5 rounded-md border px-1 text-[10.5px] leading-[16px]",
              data.deployment.rolledBack ? "border-transparent bg-ok-bg text-ok" : "border-line bg-surface-2 text-text-2",
            )}
          >
            <GitCommit size={11} weight="bold" aria-hidden className={data.deployment.root ? "text-accent" : undefined} />
            <span className={data.deployment.rolledBack ? "line-through" : undefined}>{data.deployment.id}</span>
            {data.deployment.rolledBack && <span className="sr-only">rolled back</span>}
          </span>
        )}
      </span>
    </span>
  );

  return (
    <div
      className="relative transition-opacity duration-150"
      style={{ width: data.size, height: data.size, opacity: data.dim ? 0.3 : 1, transitionTimingFunction: "var(--ease-out)" }}
    >
      {data.customerFacing && <Ring inset={13} className="border border-line-strong" />}
      {data.neighbour && <Ring inset={7} className="border border-accent" />}
      {data.blast && <Ring inset={19} className="border-[1.5px] border-dashed border-accent" />}
      {(data.highlighted || data.selected) && <Ring inset={19} className="border-2 border-accent" />}
      {data.pathIndex !== null && (
        <Ring
          inset={19}
          className={cx("border-2 border-accent", !reduced && "kea-pulse")}
          style={reduced ? undefined : { animationDelay: `${data.pathIndex * 220}ms` }}
        />
      )}
      <button
        type="button"
        aria-label={label}
        aria-pressed={data.selected}
        onClick={() => selectService(data.selected ? null : data.name)}
        onPointerEnter={(e) => e.pointerType === "mouse" && setHover(data.name)}
        onPointerLeave={(e) => e.pointerType === "mouse" && setHover(null)}
        onFocus={() => setHover(data.name)}
        onBlur={() => setHover(null)}
        className="pressable relative grid h-full w-full place-items-center text-white before:absolute before:-inset-2 before:content-['']"
        style={{
          borderRadius: "50%", // inline: the global focus rule would otherwise square the dot
          background: fill,
          boxShadow: `inset 0 0 0 2px rgb(255 255 255 / 0.35), 0 0 0 4px color-mix(in srgb, ${fill} ${halo}%, transparent), 0 0 0 9px color-mix(in srgb, ${fill} ${Math.round(halo / 2)}%, transparent)`,
        }}
      >
        <Icon size={data.size >= 44 ? 20 : 16} weight="bold" aria-hidden />
      </button>
      {text}
      {SIDES.map(([side, position]) => (
        <span key={side}>
          <Handle id={side} type="target" position={position} style={hidden} isConnectable={false} />
          <Handle id={side} type="source" position={position} style={hidden} isConnectable={false} />
        </span>
      ))}
    </div>
  );
}

export const ServiceNodeComponent = memo(ServiceNodeView);
