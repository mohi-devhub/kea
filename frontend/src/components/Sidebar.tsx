"use client";

import { ArrowCounterClockwise, ArrowUUpLeft, ChartBar, Graph, Moon, Play, SquaresFour, Sun } from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Button, cx, Panel, SectionPill } from "@/components/ui";
import { clock } from "@/lib/fmt";
import { errorText, recoverRun, resetAll, startRun } from "@/lib/session";
import { selectCanRecover, useKea } from "@/lib/store";
import { useTheme } from "@/lib/theme";

const SPEEDS = [1, 5, 10, 25];
const field =
  "h-[34px] w-full rounded-control border border-line-strong bg-surface px-2.5 text-[13px] text-text outline-none focus-visible:border-accent disabled:opacity-50";

function NavItem({ href, icon, children, active }: { href: string; icon: React.ReactNode; children: React.ReactNode; active: boolean }) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cx(
        "pressable flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-[14px]",
        active ? "bg-surface-2 font-medium text-text" : "text-text-2 [@media(hover:hover)]:hover:bg-surface-2 [@media(hover:hover)]:hover:text-text",
      )}
    >
      {icon}
      {children}
    </Link>
  );
}

function RunControls() {
  const scenarios = useKea((s) => s.scenarios);
  const run = useKea((s) => s.run);
  const mode = useKea((s) => s.mode);
  const canRecover = useKea(selectCanRecover);
  const [picked, setPicked] = useState("");
  const scenario = picked || scenarios[0]?.id || "";
  const [seed, setSeed] = useState(42);
  const [speed, setSpeed] = useState(10);
  const [busy, setBusy] = useState<"start" | "recover" | "reset" | null>(null);
  const [error, setError] = useState<string | null>(null);
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

  return (
    <div className="space-y-3">
      <SectionPill>Run</SectionPill>
      <label className="block space-y-1 text-[12px] text-text-3">
        Scenario
        <select className={field} value={scenario} onChange={(e) => setPicked(e.target.value)} disabled={!scenarios.length || running}>
          {scenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block space-y-1 text-[12px] text-text-3">
          Seed
          <input className={cx(field, "num")} type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} disabled={running || mode === "fixture"} />
        </label>
        <label className="block space-y-1 text-[12px] text-text-3">
          Speed
          <select className={cx(field, "num")} value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((x) => (
              <option key={x} value={x}>
                {x}x
              </option>
            ))}
          </select>
        </label>
      </div>
      <Button variant="primary" className="w-full" busy={busy === "start"} disabled={!scenario || running} onClick={() => act("start", () => startRun(scenario, seed, speed))}>
        <Play size={14} weight="fill" aria-hidden /> Start
      </Button>
      <div className="grid grid-cols-2 gap-2">
        <Button
          busy={busy === "recover"}
          disabled={!canRecover}
          title={mode === "fixture" ? "Fixture replay plays the recovery by itself" : canRecover ? undefined : "Recover needs an open incident"}
          onClick={() => act("recover", recoverRun)}
        >
          <ArrowUUpLeft size={14} weight="bold" aria-hidden /> Recover
        </Button>
        <Button busy={busy === "reset"} onClick={() => act("reset", resetAll)}>
          <ArrowCounterClockwise size={14} weight="bold" aria-hidden /> Reset
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-[12px] text-bad">
          {error}
        </p>
      )}
    </div>
  );
}

/** Two-state theme switch: a recessed track with a raised white thumb on the active side. */
function ThemeSwitch() {
  const [theme, setTheme] = useTheme();
  const items = [
    { value: "light" as const, label: "Light", Icon: Sun },
    { value: "dark" as const, label: "Dark", Icon: Moon },
  ];
  return (
    <div role="radiogroup" aria-label="Theme" className="grid grid-cols-2 gap-1 rounded-lg bg-surface-2 p-1">
      {items.map(({ value, label, Icon }) => (
        <button
          key={value}
          role="radio"
          aria-checked={theme === value}
          onClick={() => setTheme(value)}
          className={cx(
            "pressable flex h-8 items-center justify-center gap-1.5 rounded-md text-[13px] font-medium",
            theme === value ? "bg-surface text-text shadow-card" : "text-text-3 [@media(hover:hover)]:hover:text-text",
          )}
        >
          <Icon size={14} weight="bold" aria-hidden />
          {label}
        </button>
      ))}
    </div>
  );
}

function StatusCard() {
  const conn = useKea((s) => s.conn);
  const mode = useKea((s) => s.mode);
  const simTs = useKea((s) => s.simTs);
  const ok = conn === "connected" || conn === "fixture";
  const label = { connecting: "Connecting", connected: "Connected", reconnecting: "Reconnecting", fixture: "Fixture replay" }[conn];
  return (
    <div className="space-y-3">
      <Panel className={cx("space-y-2 p-3", !ok && "border-warn/40 bg-warn-bg")}>
        <div className="flex items-center justify-between text-[13px]">
          <span className="flex items-center gap-2 font-medium text-text">
            <span aria-hidden className={cx("h-2 w-2 rounded-full", ok ? "bg-ok-fill" : "bg-warn-fill")} />
            {label}
          </span>
          <span className="text-text-3">{mode === "fixture" ? "Recorded" : "Live"}</span>
        </div>
        <div className="flex items-center justify-between text-[12px] text-text-3">
          Sim clock
          <span className="num text-text">{simTs ? clock(simTs) : "--:--:--"}</span>
        </div>
      </Panel>
      <ThemeSwitch />
    </div>
  );
}

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="flex w-[248px] shrink-0 flex-col gap-6 border-r border-line bg-bg px-4 py-5">
      <Link href="/" className="flex items-center gap-2.5 px-1">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-btn text-btn-text">
          <Graph size={18} weight="bold" aria-hidden />
        </span>
        <span className="text-[19px] font-semibold tracking-tight text-text">kea</span>
      </Link>
      {path === "/" && <RunControls />}
      <nav aria-label="Views" className="space-y-1.5">
        <SectionPill>View</SectionPill>
        <div className="space-y-0.5 pt-1.5">
          <NavItem href="/" active={path === "/"} icon={<SquaresFour size={17} weight="bold" aria-hidden />}>
            Overview
          </NavItem>
          <NavItem href="/eval" active={path === "/eval"} icon={<ChartBar size={17} weight="bold" aria-hidden />}>
            Eval
          </NavItem>
        </div>
      </nav>
      <div className="mt-auto">
        <StatusCard />
      </div>
    </aside>
  );
}
