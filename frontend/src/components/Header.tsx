"use client";

import { ArrowCounterClockwise, ArrowUUpLeft, Moon, Play, Sun } from "@phosphor-icons/react";
import { useState, useSyncExternalStore } from "react";
import { Badge, Button } from "@/components/ui";
import { clock } from "@/lib/fmt";
import { errorText, recoverRun, resetAll, startRun } from "@/lib/session";
import { useKea } from "@/lib/store";

const SPEEDS = [1, 5, 10, 25];

function subscribeTheme(cb: () => void) {
  const observer = new MutationObserver(cb);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}
const readTheme = () => (document.documentElement.dataset.theme === "light" ? "light" : "dark");
const field =
  "h-8 rounded-control border border-line-strong bg-transparent px-2 text-[13px] text-text outline-none focus-visible:border-accent";

export function Header() {
  const scenarios = useKea((s) => s.scenarios);
  const run = useKea((s) => s.run);
  const simTs = useKea((s) => s.simTs);
  const conn = useKea((s) => s.conn);
  const mode = useKea((s) => s.mode);

  const [picked, setPicked] = useState("");
  const scenario = picked || scenarios[0]?.id || "";
  const [seed, setSeed] = useState(42);
  const [speed, setSpeed] = useState(10);
  const [busy, setBusy] = useState<"start" | "recover" | "reset" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const theme = useSyncExternalStore(subscribeTheme, readTheme, () => "dark" as const);

  const running = run?.status === "running";
  const act = async (name: "start" | "recover" | "reset", fn: () => Promise<void>) => {
    if (busy) return; // double-click safe
    setBusy(name);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("kea-theme", next);
    } catch {}
  };

  const connLabel = { connecting: "Connecting", connected: "Connected", reconnecting: "Reconnecting", fixture: "Fixture" }[conn];
  const connOk = conn === "connected" || conn === "fixture";

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-4">
      <span className="text-[15px] font-semibold tracking-tight">kea</span>
      <span className="h-4 w-px bg-line" aria-hidden />
      <label className="flex items-center gap-2 text-[12px] text-text-3">
        Scenario
        <select className={`${field} max-w-[220px]`} value={scenario} onChange={(e) => setPicked(e.target.value)} disabled={!scenarios.length || running}>
          {scenarios.map((s) => (
            <option key={s.id} value={s.id}>{s.title}</option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2 text-[12px] text-text-3">
        Seed
        <input className={`${field} num w-16`} type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} disabled={running || mode === "fixture"} />
      </label>
      <label className="flex items-center gap-2 text-[12px] text-text-3">
        Speed
        <select className={`${field} num`} value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
          {SPEEDS.map((x) => (
            <option key={x} value={x}>{x}x</option>
          ))}
        </select>
      </label>
      <span className="h-4 w-px bg-line" aria-hidden />
      <Button variant="primary" busy={busy === "start"} disabled={!scenario || running} onClick={() => act("start", () => startRun(scenario, seed, speed))}>
        <Play size={14} weight="bold" aria-hidden /> Start
      </Button>
      <Button
        busy={busy === "recover"}
        disabled={!running || mode === "fixture"}
        title={mode === "fixture" ? "Fixture replay plays the recovery by itself" : undefined}
        onClick={() => act("recover", recoverRun)}
      >
        <ArrowUUpLeft size={14} weight="bold" aria-hidden /> Recover
      </Button>
      <Button busy={busy === "reset"} onClick={() => act("reset", resetAll)}>
        <ArrowCounterClockwise size={14} weight="bold" aria-hidden /> Reset
      </Button>
      {error && (
        <span role="alert" className="max-w-[260px] truncate text-[12px] text-bad" title={error}>
          {error}
        </span>
      )}
      <div className="ml-auto flex items-center gap-3">
        <span className="text-[12px] text-text-3">
          Sim <span className="num text-text">{simTs ? clock(simTs) : "--:--:--"}</span>
        </span>
        <Badge tone={connOk ? "ok" : "warn"}>{connLabel}</Badge>
        <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          {theme === "dark" ? <Sun size={16} weight="bold" /> : <Moon size={16} weight="bold" />}
        </Button>
      </div>
    </header>
  );
}
