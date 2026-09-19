"use client";

import { Cube, Database, GitCommit, Lightning } from "@phosphor-icons/react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import { Badge, HealthChip } from "@/components/ui";
import { useKea } from "@/lib/store";
import type { Health, ServiceNode as ServiceDef } from "@/lib/types";

export type ServiceNodeData = {
  name: string;
  kind: ServiceDef["kind"];
  customerFacing: boolean;
  health: Health;
  dim: boolean;
  pathIndex: number | null;
  blast: boolean;
  highlighted: boolean;
  selected: boolean;
  deployment: { id: string; rolledBack: boolean; root: boolean } | null;
};
export type ServiceNodeType = Node<ServiceNodeData, "service">;

const KIND_ICON = { service: Cube, database: Database, cache: Lightning } as const;
const BORDER: Record<Health, string> = {
  healthy: "border-line-strong",
  degraded: "border-warn",
  failing: "border-bad",
};
const hidden = { opacity: 0, pointerEvents: "none" } as const;

/** One service: name, kind, health (icon + word + color), customer-facing and deployment markers. */
function ServiceNodeView({ data }: NodeProps<ServiceNodeType>) {
  const Icon = KIND_ICON[data.kind];
  const label = `${data.name}, ${data.health}${data.customerFacing ? ", customer-facing" : ""}`;
  const selectService = useKea((s) => s.selectService);
  return (
    <div
      className="relative w-[168px] transition-opacity duration-200"
      style={{ opacity: data.dim ? 0.4 : 1, transitionTimingFunction: "var(--ease-out)" }}
    >
      {data.pathIndex !== null && (
        <span
          aria-hidden
          className="kea-pulse pointer-events-none absolute -inset-1 rounded-[11px] border-2 border-accent"
          style={{ animationDelay: `${data.pathIndex * 220}ms` }}
        />
      )}
      <button
        type="button"
        aria-label={label}
        aria-pressed={data.selected}
        onClick={() => selectService(data.selected ? null : data.name)}
        className={[
          "pressable flex w-full flex-col gap-1.5 rounded-card border bg-surface px-3 py-2 text-left",
          BORDER[data.health],
          data.highlighted || data.selected ? "ring-2 ring-accent" : "",
          data.blast ? "outline-2 outline-offset-2 outline-dashed outline-warn" : "",
        ].join(" ")}
      >
        <span className="flex items-center gap-1.5">
          <Icon size={14} weight="bold" className="shrink-0 text-text-3" aria-hidden />
          <span className="truncate text-[13px] font-medium">{data.name}</span>
        </span>
        <span className="flex flex-wrap items-center gap-1">
          <HealthChip health={data.health} />
          {data.customerFacing && (
            <Badge tone="neutral" className="!px-1.5 !text-[10px]">
              customer-facing
            </Badge>
          )}
        </span>
        {data.deployment && (
          <span className="flex items-center gap-1 text-[11px] text-text-2">
            <GitCommit size={13} weight="bold" aria-hidden className={data.deployment.root ? "text-accent" : "text-text-3"} />
            <span className="num">{data.deployment.id}</span>
            {data.deployment.rolledBack && <span className="text-ok">rolled back</span>}
          </span>
        )}
      </button>
      <Handle id="tl" type="target" position={Position.Left} style={hidden} isConnectable={false} />
      <Handle id="tt" type="target" position={Position.Top} style={hidden} isConnectable={false} />
      <Handle id="tb" type="target" position={Position.Bottom} style={hidden} isConnectable={false} />
      <Handle id="sr" type="source" position={Position.Right} style={hidden} isConnectable={false} />
      <Handle id="sb" type="source" position={Position.Bottom} style={hidden} isConnectable={false} />
      <Handle id="st" type="source" position={Position.Top} style={hidden} isConnectable={false} />
    </div>
  );
}

export const ServiceNodeComponent = memo(ServiceNodeView);
