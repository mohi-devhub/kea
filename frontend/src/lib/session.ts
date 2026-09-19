import { api, ApiError } from "@/lib/api";
import { FIXTURE_MODE } from "@/lib/config";
import { FixturePlayer } from "@/lib/fixture";
import { connectLive } from "@/lib/live";
import { useKea } from "@/lib/store";

const player = new FixturePlayer();
const state = () => useKea.getState();

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}

/** Boot the data source (live WebSocket or fixture player) and load static data. Returns cleanup. */
export function initSession(): () => void {
  state().setEnv({ mode: FIXTURE_MODE ? "fixture" : "live", conn: FIXTURE_MODE ? "fixture" : "connecting" });
  let alive = true;
  let retry: ReturnType<typeof setTimeout> | undefined;

  const loadStatic = async () => {
    try {
      const [topology, scenarios] = FIXTURE_MODE
        ? await Promise.all([
            fetch("/fixtures/topology.json").then((r) => r.json()),
            fetch("/fixtures/scenarios.json").then((r) => r.json()),
          ])
        : await Promise.all([api.topology(), api.scenarios()]);
      if (alive) state().setEnv({ topology, scenarios, loadError: null });
    } catch (e) {
      if (!alive) return;
      state().setEnv({ loadError: errorText(e) });
      retry = setTimeout(loadStatic, 3000);
    }
  };
  void loadStatic();

  const stopLive = FIXTURE_MODE ? () => {} : connectLive();

  // Before Recover the API serves a live prediction preview; refresh it when the incident changes.
  const unsub = useKea.subscribe((s, prev) => {
    if (s.mode !== "live" || !s.incident || s.prediction?.frozen) return;
    if (s.incident.revision === prev.incident?.revision) return;
    api
      .prediction(s.incident.incident_id)
      .then((p) => state().setPreview(p))
      .catch(() => undefined);
  });

  return () => {
    alive = false;
    clearTimeout(retry);
    stopLive();
    unsub();
    player.stop();
  };
}

export async function startRun(scenario: string, seed: number, speed: number): Promise<void> {
  state().clearRun();
  if (FIXTURE_MODE) return player.start(scenario, speed);
  // one active run at a time: clear the previous run (both runs would call their incident INC-001)
  await api.reset();
  await api.simulate(scenario, { seed, speed });
}

export async function recoverRun(): Promise<void> {
  const run = state().run;
  if (!run || FIXTURE_MODE) return;
  await api.recover(run.run_id);
}

export async function resetAll(): Promise<void> {
  if (FIXTURE_MODE) player.stop();
  else await api.reset();
  state().clearRun();
}

/** Blast radius: a live Neo4j query in live mode; derived from the incident in fixture mode. */
export async function loadBlast(): Promise<void> {
  const incident = state().incident;
  if (!incident) return;
  if (FIXTURE_MODE) {
    state().setBlast({
      ...incident.blast_radius,
      root_service: incident.candidates[0]?.service ?? null,
      callers: [],
      cypher: "Not executed in fixture replay. Live mode runs this against Neo4j.",
      parameters: {},
    });
    return;
  }
  state().setBlast(await api.blastRadius(incident.incident_id));
}
