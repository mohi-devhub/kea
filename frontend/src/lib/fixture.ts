import { FIXTURE_SEED } from "@/lib/config";
import { useKea } from "@/lib/store";
import type { WsMessage } from "@/lib/types";

const WARMUP_SPEED = 200;

/** Replays a recorded WebSocket stream (`make fixtures`) with its original timing scaled by speed. */
export class FixturePlayer {
  private timer: ReturnType<typeof setTimeout> | undefined;
  private token = 0;

  async start(scenario: string, speed: number): Promise<void> {
    this.stop();
    const token = this.token;
    const res = await fetch(`/fixtures/${scenario}-${FIXTURE_SEED}.jsonl`);
    if (!res.ok) throw new Error(`No fixture recorded for ${scenario}`);
    const messages = (await res.text())
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as WsMessage);
    if (token !== this.token) return; // stopped or restarted while loading

    const warmupEnd = messages[0]?.type === "run.started" ? (messages[0].payload.warmup_end_ts ?? 0) : 0;
    // wall-clock offset of every message: warm-up is fast-forwarded, the incident runs at `speed`
    const offsets: number[] = [];
    let at = 0;
    let prev = messages[0]?.sim_ts ?? 0;
    for (const m of messages) {
      const rate = m.sim_ts < warmupEnd ? WARMUP_SPEED : speed;
      at += Math.max(0, m.sim_ts - prev) / rate;
      offsets.push(at);
      prev = m.sim_ts;
    }

    const t0 = performance.now();
    let i = 0;
    const tick = () => {
      if (token !== this.token) return;
      const elapsed = performance.now() - t0;
      while (i < messages.length && offsets[i] <= elapsed) useKea.getState().applyMessage(messages[i++]);
      if (i < messages.length) this.timer = setTimeout(tick, Math.max(4, offsets[i] - elapsed));
    };
    tick();
  }

  stop(): void {
    this.token++;
    clearTimeout(this.timer);
  }
}
