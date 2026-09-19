"use client";

import { CheckCircle, Warning, XCircle } from "@phosphor-icons/react";
import type { ComponentProps, KeyboardEvent, ReactNode } from "react";
import type { Health } from "@/lib/types";

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

type ButtonProps = ComponentProps<"button"> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "md" | "icon";
  busy?: boolean;
};

/** Primary is the reference blue; secondary is a white card-like button; ghost is quiet. */
export function Button({ variant = "secondary", size = "md", busy, className, children, disabled, ...rest }: ButtonProps) {
  const look = {
    primary: "bg-btn text-btn-text border border-transparent [@media(hover:hover)]:hover:bg-btn-hover",
    secondary:
      "bg-surface text-text border border-line-strong shadow-card [@media(hover:hover)]:hover:bg-surface-2",
    ghost:
      "bg-transparent text-text-2 border border-transparent [@media(hover:hover)]:hover:bg-surface-2 [@media(hover:hover)]:hover:text-text",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "pressable inline-flex h-[34px] items-center justify-center gap-1.5 rounded-control text-[13px] font-medium",
        size === "icon" ? "w-[34px]" : "px-3.5",
        "disabled:cursor-not-allowed disabled:opacity-45",
        look,
        className,
      )}
    >
      {children}
    </button>
  );
}

const TONES = {
  neutral: "bg-surface-2 text-text-2 border-line",
  ok: "bg-ok-bg text-ok border-transparent",
  warn: "bg-warn-bg text-warn border-transparent",
  bad: "bg-bad-bg text-bad border-transparent",
  accent: "bg-accent-bg text-accent border-transparent",
} as const;
export type BadgeTone = keyof typeof TONES;

/** Small label for source and state (LIVE / REPLAYED / TEMPLATE, verdicts). */
export function Badge({ tone = "neutral", children, className }: { tone?: BadgeTone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-[0.04em]",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Outlined mono label that names a group ("RUN", "VIEW"), as in the reference sidebar. */
export function SectionPill({ children }: { children: ReactNode }) {
  return (
    <span className="num inline-flex rounded-md border border-line-strong px-2 py-0.5 text-[11px] uppercase tracking-[0.06em] text-text-3">
      {children}
    </span>
  );
}

const HEALTH = {
  healthy: { Icon: CheckCircle, tone: "ok" as const, label: "healthy" },
  degraded: { Icon: Warning, tone: "warn" as const, label: "degraded" },
  failing: { Icon: XCircle, tone: "bad" as const, label: "failing" },
};

/** Health is never color alone: icon + word + color. */
export function HealthChip({ health, compact }: { health: Health; compact?: boolean }) {
  const { Icon, tone, label } = HEALTH[health];
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium", TONES[tone])}>
      <Icon size={13} weight="bold" aria-hidden />
      {!compact && label}
      {compact && <span className="sr-only">{label}</span>}
    </span>
  );
}

/** White card: 1px border, 14px radius, the reference's soft small shadow (none in dark). */
export function Panel({ children, className, label }: { children: ReactNode; className?: string; label?: string }) {
  return (
    <section aria-label={label} className={cx("rounded-card border border-line bg-surface shadow-card", className)}>
      {children}
    </section>
  );
}
export const Card = Panel;

/** A 40px square with four corner brackets around an icon, the reference's card marker. */
export function IconTile({ children }: { children: ReactNode }) {
  const corner = "absolute h-2.5 w-2.5 border-text";
  return (
    <span aria-hidden className="relative grid h-10 w-10 shrink-0 place-items-center text-text">
      <span className={cx(corner, "left-0 top-0 rounded-tl-[6px] border-l-[1.5px] border-t-[1.5px]")} />
      <span className={cx(corner, "right-0 top-0 rounded-tr-[6px] border-r-[1.5px] border-t-[1.5px]")} />
      <span className={cx(corner, "bottom-0 left-0 rounded-bl-[6px] border-b-[1.5px] border-l-[1.5px]")} />
      <span className={cx(corner, "bottom-0 right-0 rounded-br-[6px] border-b-[1.5px] border-r-[1.5px]")} />
      {children}
    </span>
  );
}

/** Card header: icon tile, title, and a right-aligned slot (a metric, filters, a legend). */
export function CardHeader({ icon, title, right, className }: { icon?: ReactNode; title: ReactNode; right?: ReactNode; className?: string }) {
  return (
    <div className={cx("flex items-center gap-3 px-4 pt-4", className)}>
      {icon && <IconTile>{icon}</IconTile>}
      <h2 className="text-[15px] font-medium text-text">{title}</h2>
      {right && <div className="ml-auto flex items-center gap-3 text-[13px] text-text-2">{right}</div>}
    </div>
  );
}

/** Segmented pill tabs (active = light gray pill). Arrow keys move the selection. */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T;
  options: { value: T; label: ReactNode; disabled?: boolean }[];
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  const enabled = options.filter((o) => !o.disabled);
  const onKey = (e: KeyboardEvent) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = enabled.findIndex((o) => o.value === value);
    const next = enabled[(i + (e.key === "ArrowRight" ? 1 : enabled.length - 1)) % enabled.length];
    onChange(next.value);
    e.preventDefault();
  };
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKey} className={cx("inline-flex items-center gap-1", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            disabled={o.disabled}
            onClick={() => onChange(o.value)}
            className={cx(
              "pressable h-8 rounded-lg px-3 text-[13px] font-medium disabled:cursor-not-allowed disabled:opacity-45",
              active ? "bg-surface-2 text-text" : "text-text-3 [@media(hover:hover)]:hover:text-text",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Headline number card: label, big value, small caption, optional progress bar. */
export function StatCard({
  label,
  value,
  caption,
  progress,
  icon,
}: {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  progress?: number; // 0..1
  icon?: ReactNode;
}) {
  return (
    <Panel className="flex min-w-0 flex-col p-4">
      <div className="flex items-center justify-between text-[13px] text-text-2">
        <span>{label}</span>
        {icon && <span className="text-text-3">{icon}</span>}
      </div>
      <div className="tnum mt-1.5 truncate text-[26px] font-medium leading-tight tracking-tight text-text">{value}</div>
      {progress !== undefined ? (
        <div aria-hidden className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
          <div className="h-full rounded-full bg-btn" style={{ width: `${Math.max(2, Math.min(1, progress) * 100)}%` }} />
        </div>
      ) : null}
      {caption && <div className="mt-1.5 truncate text-[12px] text-text-3">{caption}</div>}
    </Panel>
  );
}

/** Legend item: a small colored dot with mono text, as in the reference chart legends. */
export function LegendDot({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span className="num inline-flex items-center gap-1.5 text-[12px] text-text-2">
      <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {children}
    </span>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <h3 className="text-[12px] font-medium text-text-3">{children}</h3>;
}

/** Skeleton in the final shape of the content (no spinners for panels). */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-control bg-surface-2", className)} />;
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="px-4 py-6 text-[13px] text-text-3">{children}</p>;
}
