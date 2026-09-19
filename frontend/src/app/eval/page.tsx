import { ChartBar } from "@phosphor-icons/react/dist/ssr";
import { CardHeader, EmptyState, Panel } from "@/components/ui";

export default function EvalPage() {
  return (
    <main className="flex min-h-0 flex-1 flex-col gap-4 px-6 pb-6 pt-5">
      <header className="text-center">
        <h1 className="text-[30px] font-light leading-tight tracking-[-0.02em] text-text">Eval</h1>
        <p className="mt-1 text-[14px] text-text-2">How the causal engine compares with LLM-only baselines on the same incidents.</p>
      </header>
      <Panel label="Eval results" className="mx-auto w-full max-w-[880px]">
        <CardHeader icon={<ChartBar size={18} weight="bold" aria-hidden />} title="Results" />
        <EmptyState>No eval results yet. Run `make eval`.</EmptyState>
      </Panel>
    </main>
  );
}
