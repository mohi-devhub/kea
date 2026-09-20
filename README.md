<div align="center">

# kea

**A real-time incident causality engine. A deterministic engine finds the root cause, an LLM explains it, a benchmark checks both.**

![Python 3.13](https://img.shields.io/badge/python-3.13-blue)
![Next.js 16](https://img.shields.io/badge/Next.js-16-black)

</div>

Hackathon track: Next-Gen Productivity & Automation.

## What it does

When production breaks, dashboards show many red services and an on-call engineer has to work out what changed, what failed first, and how it spread. kea automates that first hour. It watches a stream of metric and deployment events, builds a live service dependency graph, and ranks root-cause candidates. Each candidate carries a per-factor score. Candidates it rejected come with a reason code, for example "deployment on `notifications` rejected: no dependency path to the affected services".

The ranking is done by a deterministic engine: pure Python, no LLM, no network. A separate investigation agent uses read-only tools to write an explanation that cites evidence ids. It explains what the engine found and never re-ranks. A benchmark runs the engine and LLM-only baselines on the same events. A human-gated fix flow lets an agent propose a code fix, which a person approves by exact patch hash.

**The 30-second pitch.** Most AI SRE tools ask an LLM to guess the root cause from raw telemetry. kea finds candidates deterministically from a causal graph, lets the LLM explain rather than decide, and measures the result against LLM-only baselines, including on real data where it loses.

## Why not just ask an LLM?

Measured on simulated incidents (tuning seeds 0-4, baseline model `gpt-5.6-terra`, small n, wide intervals):

| Question | kea engine | LLM only |
|---|---|---|
| Root-cause accuracy (S1-S3) | 5/5 per scenario | 5/5 per scenario (tie) |
| False alarms on a healthy deploy (S4) | 0 of 5 | 4 of 5 (raw telemetry) |
| Same answer on repeated runs | 100% | 87% agreement (S4, S2 with topology) |
| Median latency, tokens per analysis | about 9 ms, 0 tokens | about 3.2-3.5 s, about 5.7k tokens |

The engine does not beat the LLM on root-cause accuracy here. Its measured edge is false alarms, determinism, cost, speed and auditable evidence.

**The unflattering result.** On real telemetry from RCAEval RE1-OB (Online Boutique), 25 cases (one per service and fault type, metrics only), the engine got 4/25 top-1 and the LLM baselines got 14/25. The engine was worst on network delay and packet loss (0/5 each). This replay only exercises the service-fault path.

What is being done about it, all on tuning data: new metric types for CPU, network delay and packet loss; robust median/MAD anomaly thresholds; a constrained LLM reranker that may only permute the engine's top three candidates; and a small deterministic learned reranker. A frozen TEST split of 265 further cases is scored without tuning on it. Its interim results (engine 95/265, learned reranker 130/265 top-1, LLM rows unscored) do not support a claim that kea beats LLM accuracy.

**Caveat.** The simulated numbers above are tuning-seed numbers. The final held-out run (seeds 100-109) has not been done, and the LLM baselines' real-data rows are not yet scored on the frozen split. A "LLM degrades at scale" claim was tested (7 to 63 services) and not supported: LLM accuracy held up, but its token cost grew linearly and engine latency grew from 8 ms to 367 ms.

## Architecture

![kea high-level design](assets/architecture.png)

- **Simulator** generates seeded metric and deployment events from scenario YAMLs and a `topology.yaml`, and publishes them to **Redpanda** (Kafka-compatible).
- **Stream worker** consumes events, deduplicates them and feeds the **RCA engine**: anomaly detection, incident lifecycle, causal ranking over the dependency graph, ranked and rejected candidates with reason codes, blast radius and "what changed".
- **Neo4j** holds the service dependency graph (caller to callee, blocking or not). The engine uses an in-memory copy; Neo4j serves blast-radius queries and graph views.
- **REST API and WebSocket hub** (FastAPI) push run state and incident updates to the **Next.js dashboard**. The engine also produces a prediction of what recovery will fix, then verifies it.
- **Investigation agent** takes the top candidate and evidence, calls read-only tools through the **LLM provider layer**, and returns a narrative with evidence citations. Ungrounded output triggers one repair attempt, then a template fallback.
- **Eval harness** runs the engine and LLM-only baselines on the same events, with consistency, cost, scale and real-data (RCAEval) measurements, and feeds the `/eval` page.
- **Fix flow** proposes a patch in a sandbox and waits for human approval. It is described below.

## Key ideas

- **Deterministic engine.** Same events in, same ranking out, with inspectable factor scores and rejected candidates.
- **Predict, then verify.** The engine predicts which services recover after the fix and checks that against the outcome after Recover.
- **Grounded explanations.** Every claim in the agent's narrative cites evidence ids that must exist. Failures fall back to a labelled template (`LIVE`, `REPLAYED` or `TEMPLATE` badge).
- **Secret guard.** The LLM layer refuses to send any request containing a configured key, key-like tokens, private keys or home paths. Requests use `store=False`.
- **Record/replay LLM cache.** `LLM_CACHE_MODE=record|replay` makes LLM runs reproducible and offline.
- **Held-out ledger.** Every evaluation of the held-out seeds is logged in `eval_results/.heldout_log`.
- **Human approval bound to the patch hash.** Approving a proposal approves one exact diff, nothing else.

## Tech stack

| Layer | Technology |
|---|---|
| Engine, API, worker | Python 3.13, FastAPI, Pydantic, uv |
| Streaming | Redpanda (Kafka API), aiokafka |
| Graph | Neo4j 5.26 Community |
| LLM | Provider layer; OpenAI Responses API adapter (Anthropic and Sarvam planned) |
| Frontend | Next.js 16, React 19, TypeScript, types generated from OpenAPI |
| Tooling | Docker Compose, pytest, ruff, strict mypy |

## Quick start

Prerequisites: Docker with about 8 GB of memory, Python 3.13, [uv](https://docs.astral.sh/uv/), Node and pnpm.

```bash
cp .env.example .env     # then set NEO4J_PASSWORD to any local password
make up                  # Redpanda, Neo4j, API, worker, frontend
```

`.env.example` contains placeholders only. The default `LLM_PROVIDER=template` needs no API key and produces template explanations. To use a real provider, set `LLM_PROVIDER`, `LLM_MODEL` and the matching `*_API_KEY` in your local `.env` (git-ignored). With a provider set, each incident triggers one paid call unless `AUTO_INVESTIGATE=false`.

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Neo4j browser | http://localhost:7474 |
| Redpanda console (optional) | http://localhost:8080 via `docker compose --profile tools up -d redpanda-console` |

Open the dashboard, pick a scenario (S1 to S4), press Start, and press Recover when the incident is open.

| Command | What it does |
|---|---|
| `make test` | Fast unit tests, no infrastructure needed |
| `make test-int` | Integration tests (needs Redpanda and Neo4j; stops api, worker, frontend) |
| `make scenarios` | Batch S1-S4 acceptance matrix on tuning seeds |
| `make demo-check` | End-to-end smoke of S1-S4 through the running stack (run `make up` first) |
| `make eval` | Benchmark report; falls back to templates if no LLM key is configured |
| `make types` | Export OpenAPI and regenerate frontend types |
| `make lint` | ruff, mypy, eslint, typecheck |
| `make down` / `make reset` | Stop the stack / wipe volumes and reseed |

## Scenarios

| ID | Name | What happens | Correct answer |
|---|---|---|---|
| S1 | `s1_bad_deploy_payment` | A payment deployment causes a cascading checkout outage | Deployment `dep-182` on `payment` |
| S2 | `s2_postgres_degradation` | A database fault, obscured by an earlier payment deployment | Fault on `postgres` (the deployment is a decoy) |
| S3 | `s3_red_herring_deploy` | An unrelated `notifications` deployment precedes a cache failure | Fault on `redis`; the deployment must be rejected |
| S4 | `s4_benign_deploy` | A harmless change and one metric spike | No incident should open |

## Fix flow

The fix flow is built at the propose-only level. Applying a patch is deliberately disabled in this build.

**Design** (`backend/app/fix/`). It is offered when the top candidate is a deployment whose commit exists in a small generated demo repo.

1. A throwaway sandbox clone of the demo repo is created; nothing is written outside it.
2. Tests run in the sandbox before the change (expected failing).
3. A coding agent edits files in the sandbox only, and may not modify existing tests. The diff is hashed with SHA-256.
4. Tests run again after the change, and a short explanation that cites incident evidence is generated.
5. A human reviews the diff, explanation and test results, and approves by sending the exact diff hash. A mismatched hash is rejected, and only a green, test-preserving proposal can be approved.

Endpoints (from the fix flow spec): `POST /incidents/{id}/fix-proposals`, `GET /fix-proposals/{id}`, `POST /fix-proposals/{id}/approve` (body `{diff_hash, approver}`), `POST /fix-proposals/{id}/reject`, `POST /fix-proposals/{id}/regenerate`. Progress arrives as a WebSocket `fix.state` message.

**Enabled now:** propose, verify and review. **Apply is visibly disabled.** This feature is under active development, so the details may change.

### Future expansion

- Apply the approved diff to a branch, after re-checking the hash.
- Draft PR through the local adapter (a markdown draft, no network), then a GitHub draft PR.
- Automatic re-verification after the fix is applied.
- More incident types beyond code-change root causes.
- Codex CLI as the primary fix backend, with the LLM tool loop as fallback.
- Anthropic and Sarvam provider adapters.

## Evaluation methodology

- Engine weights and thresholds are tuned only on tuning seeds 0-4. Reported final numbers use held-out seeds 100-109.
- Every evaluation of the held-out seeds is recorded in `eval_results/.heldout_log`. If a held-out result ever forces a code change, a fresh held-out set is used.
- Baselines get the same events and no engine output (no anomalies, scores, scenario names or ground truth). Baseline code must not import the simulator.
- Confidence intervals are Wilson intervals. Runs that did not produce an answer (`not_run`, provider error) are excluded from the denominator and shown as not run. Malformed answers count as wrong.
- Baseline prompts are written as a competent SRE would write them and are not tuned to make baselines fail. An earlier version hid part of the metric window from the baselines. That was a fairness bug and was fixed.
- The hybrid's root cause equals the engine's by construction, so its accuracy is not reported as an independent result.

## Repo layout

```
backend/
  app/engine/      deterministic causality engine (no LLM)
  app/simulator/   seeded scenario event generator and publisher
  app/stream/      Kafka consumer and worker
  app/graph/       Neo4j client and topology seeding
  app/api/         run store and API views
  app/agent/       investigation agent, tools, grounding, templates
  app/llm/         provider layer, cache, secret guard, OpenAI adapter
  app/eval/        harness, baselines, grading, metrics
  app/models/      Pydantic contract models
  scripts/         scenarios, demo check, fixtures, OpenAPI export
  tests/           unit and integration tests
frontend/          Next.js dashboard, /eval and /timeline pages
scenarios/         S1-S4 YAMLs and topology.yaml
eval_results/      held-out ledger (generated reports are git-ignored)
assets/            architecture diagram
```

`backend/app/fix/` is the fix flow package, added as part of the fix flow work.

## Limitations

- All incidents are simulated except the RCAEval replay. The engine is a heuristic, and its score is not a probability.
- Real-data accuracy is low (4/25 on the tuning slice, see above). It is not evidence that kea beats LLMs on accuracy.
- Simulated results use 5 tuning seeds and one LLM (`gpt-5.6-terra`); intervals are wide. The final held-out run is pending.
- Only the OpenAI adapter exists; other providers fall back to templates.
- One incident per run; the incident id is fixed. Neo4j is a single node, and it would not be the choice at production scale.
- The fix flow proposes only; the demo repo is a small generated one.

## Roadmap

1. Final held-out evaluation and publication of real-data results.
2. Finish the fix flow, then the expansion list above.
3. More scenarios (concurrent deployments) and real telemetry ingestion via `POST /events`.
4. More provider adapters.

## How this was built

Built with Codex and Claude Code from a written spec, with tests as the acceptance criteria and a human reviewing each milestone. The build record is kept in the project's `docs/BUILD_LOG.md` (not committed).
