"use client";

import "@xyflow/react/dist/base.css";
import { CheckCircle, Eye } from "@phosphor-icons/react";
import { ReactFlow, useReactFlow } from "@xyflow/react";
import { useEffect, useMemo, useRef, type RefObject } from "react";
import { NodeDrawer } from "@/components/graph/NodeDrawer";
import { ArrowDefs, KeaEdge, type KeaEdgeType } from "@/components/graph/KeaEdge";
import { ServiceNodeComponent, type ServiceNodeType } from "@/components/graph/ServiceNode";
import { buildPathModel, edgeKey } from "@/components/graph/graphModel";
import { Skeleton } from "@/components/ui";
import { useKea } from "@/lib/store";

const nodeTypes = { service: ServiceNodeComponent };
const edgeTypes = { kea: KeaEdge };
const FIT = { padding: 0.1, duration: 0 } as const;

// Dev-only handle for driving the store from a browser console or screenshot script.
if (process.env.NODE_ENV !== "production" && typeof window !== "undefined") {
  (window as unknown as { __kea?: typeof useKea }).__kea = useKea;
}

/** The graph does not track window size by itself, so refit whenever its container resizes. */
function RefitOnResize({ target }: { target: RefObject<HTMLDivElement | null> }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const el = target.current;
    if (!el) return;
    const observer = new ResizeObserver(() => void fitView(FIT));
    observer.observe(el);
    return () => observer.disconnect();
  }, [fitView, target]);
  return null;
}

/**
 * Static-layout topology. Selects only health, incident, overlay and blast state, so metric
 * batches (which live in their own store fields) never re-render it.
 */
export function TopologyGraph() {
  const topology = useKea((s) => s.topology);
  const health = useKea((s) => s.health);
  const incident = useKea((s) => s.incident);
  const overlayId = useKea((s) => s.overlayCandidateId);
  const blast = useKea((s) => s.blast);
  const highlight = useKea((s) => s.highlight);
  const deployments = useKea((s) => s.deployments);
  const run = useKea((s) => s.run);
  const watching = useKea((s) => s.watching);
  const selected = useKea((s) => s.selectedService);
  const selectService = useKea((s) => s.selectService);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (process.env.NODE_ENV === "production") return;
    const w = window as unknown as { __keaGraphRenders?: number };
    w.__keaGraphRenders = (w.__keaGraphRenders ?? 0) + 1;
  });

  const candidate = incident?.candidates.find((c) => c.candidate_id === overlayId);
  const path = useMemo(() => buildPathModel(candidate, topology?.edges ?? []), [candidate, topology]);
  const overlayOn = candidate !== undefined;

  // latest deployment per service, and whether a rollback of it has been seen
  const deployed = useMemo(() => {
    const byService = new Map<string, { id: string; rolledBack: boolean }>();
    for (const e of deployments) {
      const id = String(e.payload.deployment_id ?? "");
      if (e.kind === "deployment") byService.set(e.service, { id, rolledBack: false });
      else if (e.kind === "rollback") {
        const known = byService.get(e.service);
        if (known?.id === id) byService.set(e.service, { id, rolledBack: true });
      }
    }
    return byService;
  }, [deployments]);

  const blastServices = useMemo(
    () => new Set([...(blast?.services ?? []), ...(blast?.callers.map((c) => c.service) ?? [])]),
    [blast],
  );

  const nodes = useMemo<ServiceNodeType[]>(
    () =>
      (topology?.services ?? []).map((svc) => {
        const dep = deployed.get(svc.name);
        return {
          id: svc.name,
          type: "service",
          position: { x: svc.layout.x, y: svc.layout.y },
          draggable: false,
          selectable: false,
          // with drag/select/connect all off React Flow sets pointer-events:none on the wrapper,
          // which lets the pane swallow clicks meant for the node's own button
          style: { pointerEvents: "all" },
          data: {
            name: svc.name,
            kind: svc.kind,
            customerFacing: svc.customer_facing,
            health: health[svc.name] ?? svc.health,
            dim: overlayOn && !path.nodeOrder.has(svc.name),
            pathIndex: overlayOn ? (path.nodeOrder.get(svc.name) ?? null) : null,
            blast: blastServices.has(svc.name),
            highlighted: highlight.includes(svc.name),
            selected: selected === svc.name,
            deployment: dep
              ? { ...dep, root: overlayOn && candidate?.deployment_id === dep.id }
              : null,
          },
        };
      }),
    [topology, health, deployed, overlayOn, path, blastServices, highlight, selected, candidate],
  );

  const edges = useMemo<KeaEdgeType[]>(() => {
    if (!topology) return [];
    const at = new Map(topology.services.map((s) => [s.name, s.layout]));
    return topology.edges.map((e) => {
      const from = at.get(e.source);
      const to = at.get(e.target);
      const sameColumn = from && to && Math.abs(from.x - to.x) < 60;
      const down = from && to && from.y < to.y;
      // a long climb (inventory to postgres) enters the target from below so the curve stays
      // clear of the nodes in between instead of reading as if it came from one of them
      const climbs = from && to && to.y < from.y - 150;
      const order = path.edgeOrder.get(edgeKey(e.source, e.target));
      return {
        id: edgeKey(e.source, e.target),
        type: "kea",
        source: e.source,
        target: e.target,
        sourceHandle: sameColumn ? (down ? "sb" : "st") : "sr",
        targetHandle: sameColumn ? (down ? "tt" : "tb") : climbs ? "tb" : "tl",
        focusable: false,
        selectable: false,
        data: {
          blocking: e.blocking,
          state: !overlayOn ? "normal" : order === undefined ? "dim" : "path",
          order: order ?? 0,
        },
      };
    });
  }, [topology, path, overlayOn]);

  if (!topology) return <Skeleton className="m-4 h-[calc(100%-2rem)]" />;

  const anyUnhealthy = Object.values(health).some((h) => h !== "healthy");

  return (
    <div ref={box} className="relative h-full w-full">
      {/* keep React Flow's attribution, but let it follow the theme instead of a fixed gray box */}
      <style>{`.kea-graph .react-flow__attribution{background:transparent;color:var(--text-3)}.kea-graph .react-flow__attribution a{color:var(--text-3)}`}</style>
      <ArrowDefs />
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={FIT}
        minZoom={0.3}
        maxZoom={1.2}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        onPaneClick={() => selectService(null)}
        style={{ background: "transparent" }}
        className="kea-graph"
      >
        <RefitOnResize target={box} />
      </ReactFlow>

      <div className="pointer-events-none absolute left-3 top-3 flex flex-col items-start gap-2">
        {!run && <p className="text-[13px] text-text-3">Pick a scenario and press Start.</p>}
        {run && !incident && watching && (
          <span role="status" className="inline-flex items-center gap-1.5 rounded-full bg-warn-bg px-2.5 py-1 text-[12px] font-medium text-warn">
            <Eye size={13} weight="bold" aria-hidden />
            Watching {watching} (needs corroboration)
          </span>
        )}
        {run && !incident && !watching && !anyUnhealthy && (
          <span role="status" className="inline-flex items-center gap-1.5 rounded-full bg-ok-bg px-2.5 py-1 text-[12px] font-medium text-ok">
            <CheckCircle size={13} weight="bold" aria-hidden />
            All systems healthy
          </span>
        )}
      </div>

      <ul className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-4 text-[11px] text-text-3" aria-label="Legend">
        <li className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden>
            <line x1="0" y1="3" x2="22" y2="3" stroke="var(--text-3)" strokeWidth="1.5" />
          </svg>
          Blocking call
        </li>
        <li className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden>
            <line x1="0" y1="3" x2="22" y2="3" stroke="var(--text-3)" strokeWidth="1.5" strokeDasharray="5 4" />
          </svg>
          Non-blocking call
        </li>
      </ul>

      <NodeDrawer />
    </div>
  );
}
