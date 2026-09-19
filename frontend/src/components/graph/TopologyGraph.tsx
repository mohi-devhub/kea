"use client";

import "@xyflow/react/dist/base.css";
import { CheckCircle, Eye, TreeStructure } from "@phosphor-icons/react";
import { Background, BackgroundVariant, ReactFlow, useReactFlow } from "@xyflow/react";
import { useEffect, useMemo, useRef, type RefObject } from "react";
import { NodeDrawer } from "@/components/graph/NodeDrawer";
import { ArrowDefs, KeaEdge, type KeaEdgeType } from "@/components/graph/KeaEdge";
import { ServiceNodeComponent, type ServiceNodeType } from "@/components/graph/ServiceNode";
import { LAYOUT_SCALE, buildPathModel, edgeKey, edgeSides, neighboursOf, nodeSizes } from "@/components/graph/graphModel";
import { useHover } from "@/components/graph/hoverStore";
import { CardHeader, LegendDot, Skeleton } from "@/components/ui";
import { useKea } from "@/lib/store";

const nodeTypes = { service: ServiceNodeComponent };
const edgeTypes = { kea: KeaEdge };
// labels hang below (or above) the dots and are not part of the node bounds, so leave room for them
const FIT = { padding: { top: "26px", right: "48px", bottom: "54px", left: "48px" }, duration: 0, maxZoom: 1.15 } as const;

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

function LineKey({ dashed, children }: { dashed?: boolean; children: React.ReactNode }) {
  return (
    <span className="num inline-flex items-center gap-1.5 text-[12px] text-text-2">
      <svg width="20" height="6" aria-hidden>
        <line x1="1" y1="3" x2="19" y2="3" stroke="var(--text-3)" strokeWidth="1.5" strokeLinecap="round" strokeDasharray={dashed ? "3 3" : undefined} />
      </svg>
      {children}
    </span>
  );
}

/** Legend in the card header: line styles and health colors. */
function Legend() {
  return (
    <ul aria-label="Legend" className="hidden items-center gap-3.5 lg:flex">
      <li>
        <LineKey>Blocking</LineKey>
      </li>
      <li>
        <LineKey dashed>Non-blocking</LineKey>
      </li>
      <li>
        <LegendDot color="var(--ok-fill)">healthy</LegendDot>
      </li>
      <li>
        <LegendDot color="var(--warn-fill)">degraded</LegendDot>
      </li>
      <li>
        <LegendDot color="var(--bad-fill)">failing</LegendDot>
      </li>
    </ul>
  );
}

const HEADER = <CardHeader icon={<TreeStructure size={18} weight="bold" />} title="Topology" right={<Legend />} />;

/**
 * Static-layout topology as halo dots. Selects only health, incident, overlay, blast, highlight and
 * hover state, so metric batches (which live in their own store fields) never re-render it.
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
  const hovered = useHover((s) => s.id);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (process.env.NODE_ENV === "production") return;
    const w = window as unknown as { __keaGraphRenders?: number };
    w.__keaGraphRenders = (w.__keaGraphRenders ?? 0) + 1;
  });

  const candidate = incident?.candidates.find((c) => c.candidate_id === overlayId);
  const path = useMemo(() => buildPathModel(candidate, topology?.edges ?? []), [candidate, topology]);
  const overlayOn = candidate !== undefined;
  // hover focus only applies when the causal path overlay is not already telling a story
  const focus = overlayOn ? null : hovered;

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

  // static geometry: dot sizes and which side of each dot every edge uses
  const geometry = useMemo(() => {
    if (!topology) return null;
    const at = new Map(topology.services.map((s) => [s.name, s.layout]));
    const sizes = nodeSizes(topology.services.map((s) => s.name), topology.edges);
    const sides = new Map(
      topology.edges.map((e) => {
        const from = at.get(e.source);
        const to = at.get(e.target);
        return [edgeKey(e.source, e.target), from && to ? edgeSides(from, to) : { source: "right" as const, target: "left" as const }];
      }),
    );
    // a label goes above its dot when an edge leaves or enters the dot from below
    const labelAbove = new Set<string>();
    for (const e of topology.edges) {
      const s = sides.get(edgeKey(e.source, e.target));
      if (s?.source === "bottom") labelAbove.add(e.source);
      if (s?.target === "bottom") labelAbove.add(e.target);
    }
    return { sizes, sides, labelAbove };
  }, [topology]);

  const neighbours = useMemo(() => (focus && topology ? neighboursOf(focus, topology.edges) : null), [focus, topology]);

  const nodes = useMemo<ServiceNodeType[]>(
    () =>
      (topology?.services ?? []).map((svc) => {
        const dep = deployed.get(svc.name);
        const size = geometry?.sizes.get(svc.name) ?? 36;
        const isNeighbour = neighbours?.has(svc.name) ?? false;
        return {
          id: svc.name,
          type: "service",
          // the dot's centre sits on the (scaled) layout coordinate
          position: { x: svc.layout.x * LAYOUT_SCALE - size / 2, y: svc.layout.y * LAYOUT_SCALE - size / 2 },
          draggable: false,
          selectable: false,
          // with drag/select/connect all off React Flow sets pointer-events:none on the wrapper,
          // which lets the pane swallow clicks meant for the node's own button
          style: { pointerEvents: "all" },
          data: {
            name: svc.name,
            kind: svc.kind,
            customerFacing: svc.customer_facing,
            health: health[svc.name] ?? "healthy", // live store only: the topology response can carry a past run's health
            size,
            labelAbove: geometry?.labelAbove.has(svc.name) ?? false,
            dim: overlayOn ? !path.nodeOrder.has(svc.name) : focus !== null && svc.name !== focus && !isNeighbour,
            neighbour: isNeighbour,
            pathIndex: overlayOn ? (path.nodeOrder.get(svc.name) ?? null) : null,
            blast: blastServices.has(svc.name),
            highlighted: highlight.includes(svc.name),
            selected: selected === svc.name,
            deployment: dep ? { ...dep, root: overlayOn && candidate?.deployment_id === dep.id } : null,
          },
        };
      }),
    [topology, geometry, health, deployed, overlayOn, path, focus, neighbours, blastServices, highlight, selected, candidate],
  );

  const edges = useMemo<KeaEdgeType[]>(() => {
    if (!topology) return [];
    return topology.edges.map((e) => {
      const key = edgeKey(e.source, e.target);
      const sides = geometry?.sides.get(key);
      const order = path.edgeOrder.get(key);
      const touches = focus !== null && (e.source === focus || e.target === focus);
      return {
        id: key,
        type: "kea",
        source: e.source,
        target: e.target,
        sourceHandle: sides?.source ?? "right",
        targetHandle: sides?.target ?? "left",
        focusable: false,
        selectable: false,
        data: {
          blocking: e.blocking,
          state: overlayOn ? (order === undefined ? "dim" : "path") : focus === null ? "normal" : touches ? "hover" : "dim",
          order: order ?? 0,
        },
      };
    });
  }, [topology, geometry, path, overlayOn, focus]);

  if (!topology) {
    return (
      <div className="flex h-full flex-col">
        {HEADER}
        <Skeleton className="m-4 min-h-0 flex-1" />
      </div>
    );
  }

  const anyUnhealthy = Object.values(health).some((h) => h !== "healthy");

  return (
    <div className="flex h-full flex-col">
      {HEADER}
      <div ref={box} className="relative min-h-0 flex-1">
        {/* keep React Flow's attribution (license), but quiet and following the theme */}
        <style>{`.kea-graph .react-flow__attribution{background:transparent;color:var(--text-3);font-size:10px;padding:0 6px}.kea-graph .react-flow__attribution a{color:var(--text-3)}`}</style>
        <ArrowDefs />
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={FIT}
          minZoom={0.3}
          maxZoom={1.15}
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
          <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="var(--line-strong)" />
          <RefitOnResize target={box} />
        </ReactFlow>

        <div className="pointer-events-none absolute left-4 top-2 flex flex-col items-start gap-2">
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

        <NodeDrawer />
      </div>
    </div>
  );
}
