import { Timeline } from "@/components/timeline/Timeline";
import { Panel } from "@/components/ui";

export default function TimelinePage() {
  return (
    <main className="flex min-h-0 flex-1 flex-col gap-4 px-6 pb-6 pt-5">
      <header className="text-center">
        <h1 className="text-[28px] font-light leading-tight tracking-[-0.02em] text-text">Timeline</h1>
        <p className="mt-0.5 text-[14px] text-text-2">Everything that happened, in simulated time, newest at the bottom.</p>
      </header>
      <Panel label="Timeline" className="mx-auto min-h-0 w-full max-w-[1000px] flex-1 overflow-hidden">
        <Timeline />
      </Panel>
    </main>
  );
}
