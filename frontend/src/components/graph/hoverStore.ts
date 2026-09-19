import { create } from "zustand";
import { useSyncExternalStore } from "react";

/** Which node the pointer or keyboard focus is on. Local to the graph: nothing else reads it. */
export const useHover = create<{ id: string | null; set: (id: string | null) => void }>((set) => ({
  id: null,
  set: (id) => set({ id }),
}));

const query = "(prefers-reduced-motion: reduce)";
const subscribe = (cb: () => void) => {
  const m = window.matchMedia(query);
  m.addEventListener("change", cb);
  return () => m.removeEventListener("change", cb);
};

/** The pulse class is unlayered global CSS, so reduced motion is handled by not applying it. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(query).matches,
    () => false,
  );
}
