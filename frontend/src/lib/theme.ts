import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

function subscribe(cb: () => void) {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}
const read = (): Theme => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");

/** Light is the default; dark is `<html data-theme="dark">`, remembered in localStorage. */
export function useTheme(): [Theme, (t: Theme) => void] {
  const theme = useSyncExternalStore(subscribe, read, () => "light" as const);
  const set = (t: Theme) => {
    if (t === "dark") document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
    try {
      localStorage.setItem("kea-theme", t);
    } catch {}
  };
  return [theme, set];
}
