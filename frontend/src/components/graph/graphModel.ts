import type { Candidate, TopologyEdge } from "@/lib/types";

/** Where each node and edge sits on the causal path, in pulse order (root first). */
export type PathModel = {
  nodeOrder: Map<string, number>;
  edgeOrder: Map<string, number>;
};

export const edgeKey = (source: string, target: string) => `${source}->${target}`;

/** Shortest route between two services, ignoring call direction (causal chains jump several hops). */
function route(edges: TopologyEdge[], from: string, to: string): string[] | null {
  const neighbours = new Map<string, string[]>();
  for (const e of edges) {
    neighbours.set(e.source, [...(neighbours.get(e.source) ?? []), e.target]);
    neighbours.set(e.target, [...(neighbours.get(e.target) ?? []), e.source]);
  }
  const prev = new Map<string, string | null>([[from, null]]);
  const queue = [from];
  for (let i = 0; i < queue.length; i++) {
    const at = queue[i];
    if (at === to) break;
    for (const next of neighbours.get(at) ?? []) {
      if (prev.has(next)) continue;
      prev.set(next, at);
      queue.push(next);
    }
  }
  if (!prev.has(to)) return null;
  const out: string[] = [];
  for (let at: string | null = to; at; at = prev.get(at) ?? null) out.unshift(at);
  return out;
}

/** Turns a candidate's chain into ordered nodes and edges of the topology. */
export function buildPathModel(candidate: Candidate | undefined, edges: TopologyEdge[]): PathModel {
  const nodeOrder = new Map<string, number>();
  const edgeOrder = new Map<string, number>();
  if (!candidate) return { nodeOrder, edgeOrder };

  const services = candidate.chain.map((s) => s.service).filter((s, i, all) => i === 0 || s !== all[i - 1]);
  const exists = new Set(edges.map((e) => edgeKey(e.source, e.target)));
  const add = (name: string) => {
    if (!nodeOrder.has(name)) nodeOrder.set(name, nodeOrder.size);
  };
  services.forEach((name, i) => {
    add(name);
    if (i === 0) return;
    const hops = route(edges, services[i - 1], name) ?? [services[i - 1], name];
    for (let h = 1; h < hops.length; h++) {
      add(hops[h]);
      const forward = edgeKey(hops[h - 1], hops[h]);
      const key = exists.has(forward) ? forward : edgeKey(hops[h], hops[h - 1]);
      if (!edgeOrder.has(key)) edgeOrder.set(key, nodeOrder.get(hops[h]) ?? 0);
    }
  });
  return { nodeOrder, edgeOrder };
}

/** Layout coordinates from the topology are scaled uniformly so the dots read at a useful size. */
export const LAYOUT_SCALE = 0.6;
const NODE_MIN = 30;
const NODE_MAX = 52;

/** Dot diameter grows with degree centrality (in plus out edges), as in a graph view. */
export function nodeSizes(names: string[], edges: TopologyEdge[]): Map<string, number> {
  const degree = new Map(names.map((n) => [n, 0]));
  for (const e of edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  const values = [...degree.values()];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  return new Map(
    names.map((n) => [n, Math.round(NODE_MIN + (hi === lo ? 0 : (((degree.get(n) ?? 0) - lo) / (hi - lo)) * (NODE_MAX - NODE_MIN)))]),
  );
}

export type Side = "left" | "right" | "top" | "bottom";

/**
 * Which side of each dot an edge leaves and enters. Straight columns use top and bottom, the rest
 * go left to right, and one long climb enters its target from below so it stays clear of the
 * labels of the nodes it passes.
 */
export function edgeSides(from: { x: number; y: number }, to: { x: number; y: number }): { source: Side; target: Side } {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (Math.abs(dx) < 60) return dy >= 0 ? { source: "bottom", target: "top" } : { source: "top", target: "bottom" };
  if (dx > 0 && dy < -180) return { source: "right", target: "bottom" };
  return dx > 0 ? { source: "right", target: "left" } : { source: "left", target: "right" };
}

/** Services directly connected to `id`, in either direction. */
export function neighboursOf(id: string, edges: TopologyEdge[]): Set<string> {
  const out = new Set<string>();
  for (const e of edges) {
    if (e.source === id) out.add(e.target);
    if (e.target === id) out.add(e.source);
  }
  return out;
}
