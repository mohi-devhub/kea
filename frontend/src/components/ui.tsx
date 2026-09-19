import { CheckCircle, Warning, XCircle } from "@phosphor-icons/react/dist/ssr";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Health } from "@/lib/types";

const cx = (...parts: (string | false | undefined)[]) => parts.filter(Boolean).join(" ");

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  busy?: boolean;
};

/** Solid primary, bordered secondary, quiet ghost. 6px radius, no shadow, press feedback. */
export function Button({ variant = "secondary", busy, className, children, disabled, ...rest }: ButtonProps) {
  const look = {
    primary: "bg-btn text-btn-text [@media(hover:hover)]:hover:bg-btn-hover border border-transparent",
    secondary: "bg-transparent text-text border border-line-strong [@media(hover:hover)]:hover:bg-surface-2",
    ghost: "bg-transparent text-text-2 border border-transparent [@media(hover:hover)]:hover:bg-surface-2 [@media(hover:hover)]:hover:text-text",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "pressable inline-flex h-8 items-center gap-1.5 rounded-control px-3 text-[13px] font-medium",
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

/** Small uppercase label for source and state (LIVE / REPLAYED / TEMPLATE, verdicts). */
export function Badge({ tone = "neutral", children, className }: { tone?: BadgeTone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-[0.05em]",
        TONES[tone],
        className,
      )}
    >
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
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium",
        TONES[tone],
      )}
    >
      <Icon size={13} weight="bold" aria-hidden />
      {!compact && label}
      {compact && <span className="sr-only">{label}</span>}
    </span>
  );
}

/** Panel surface: 1px border, 8px radius, no shadow. Nested boxes are banned; use dividers. */
export function Panel({ children, className, label }: { children: ReactNode; className?: string; label?: string }) {
  return (
    <section aria-label={label} className={cx("rounded-card border border-line bg-surface", className)}>
      {children}
    </section>
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
