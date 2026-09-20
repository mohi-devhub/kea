"""Pure anomaly detection, incident lifecycle, and deterministic causal ranking."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import exp
from statistics import median

from app.engine.config import EngineConfig
from app.engine.topology import InMemoryTopology
from app.models.engine import (
    Anomaly,
    BlastRadius,
    Candidate,
    ChainStep,
    ChangeItem,
    EngineUpdate,
    Evidence,
    Factor,
    Incident,
    RejectedCandidate,
    WhatChanged,
)
from app.models.events import DeploymentEvent, Event, MetricEvent

REASON_TEXT = {
    "NO_ANOMALY_ON_SERVICE_OR_REACHABLE": "it has no dependency path to the affected services",
    "ANOMALY_EXPLAINED_BY_EARLIER_CAUSE": "the anomalies near it are explained by an earlier cause",
    "OUTSIDE_LOOKBACK_WINDOW": "the nearby anomalies began outside the lookback window",
    "ANOMALY_PRECEDES_DEPLOYMENT": "the nearby anomalies began before it",
}


def _clock(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=UTC).strftime("%H:%M:%S")


@dataclass(frozen=True)
class Deployment:
    id: str
    service: str
    ts: int
    version: str = ""
    summary: str = ""


@dataclass(frozen=True)
class Parent:
    anomaly: Anomaly
    via: str
    weight: float


@dataclass
class EngineResult:
    updates: list[EngineUpdate]
    anomalies: list[Anomaly]
    candidates: list[Candidate]
    rejected_candidates: list[RejectedCandidate]
    incident_open: bool
    incident: Incident | None


@dataclass
class EngineState:
    run_id: str
    topology: InMemoryTopology
    config: EngineConfig = field(default_factory=EngineConfig)
    samples: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    breach_streaks: dict[tuple[str, str], list[tuple[int, float]]] = field(default_factory=dict)
    resolve_streaks: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    anomalies: list[Anomaly] = field(default_factory=list)
    deployments: list[Deployment] = field(default_factory=list)
    updates: list[EngineUpdate] = field(default_factory=list)
    service_health: dict[str, str] = field(default_factory=dict)
    incident: Incident | None = None
    _last_incident_activity_ts: int = 0
    _incident_active_ids: tuple[str, ...] = ()
    _member_ids: set[str] = field(default_factory=set)
    _pending_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.service_health = {service: "healthy" for service in self.topology.topology.services}

    def ingest(self, event: Event) -> list[EngineUpdate]:
        before = len(self.updates)
        if isinstance(event, DeploymentEvent):
            self.deployments.append(
                Deployment(
                    event.payload.deployment_id,
                    event.service,
                    event.ts,
                    event.payload.version,
                    event.payload.summary,
                )
            )
            self.deployments.sort(key=lambda deployment: (deployment.ts, deployment.id))
        elif isinstance(event, MetricEvent):
            self._metric(event)
        return self.updates[before:]

    def _metric(self, event: MetricEvent) -> None:
        metric = event.payload.metric
        if metric == "request_rate":
            return
        key = (event.service, metric)
        history = self.samples.setdefault(key, [])
        active = self._active_anomaly(event.service, metric)
        baseline = (
            float(median(history[-self.config.baseline_window :]))
            if history
            else event.payload.value
        )
        if active is None and len(history) >= self.config.min_baseline_samples:
            self._detect(event, baseline, key)
        elif active is not None:
            self._resolve(event, active, baseline, key)
        if self._active_anomaly(event.service, metric) is None:
            history.append(event.payload.value)
            del history[: -self.config.baseline_window]
        self._refresh_health(event)
        self._refresh_incident(event)

    def _detect(self, event: MetricEvent, baseline: float, key: tuple[str, str]) -> None:
        if not self._breaches(event.payload.metric, event.payload.value, baseline):
            self.breach_streaks[key] = []
            return
        streak = self.breach_streaks.setdefault(key, [])
        streak.append((event.ts, event.payload.value))
        if len(streak) < self.config.consecutive_samples:
            return
        onset, _ = streak[0]
        peak = max(value for _, value in streak)
        anomaly = Anomaly(
            anomaly_id=f"A-{self.run_id}-{len(self.anomalies) + 1:04d}",
            run_id=self.run_id,
            service=event.service,
            metric=event.payload.metric,
            onset_ts=onset,
            detected_ts=event.ts,
            state="active",
            baseline=round(baseline, 4),
            peak_value=round(peak, 4),
            ratio=round(peak / max(baseline, self._floor(event.payload.metric)), 4),
        )
        self.anomalies.append(anomaly)
        self.breach_streaks[key] = []
        self._emit(event, "anomaly_opened", {"anomaly_id": anomaly.anomaly_id})

    def _resolve(
        self, event: MetricEvent, anomaly: Anomaly, baseline: float, key: tuple[str, str]
    ) -> None:
        threshold = self._threshold(event.payload.metric, baseline)
        midpoint = baseline + (threshold - baseline) / 2
        streak = self.resolve_streaks.setdefault(key, [])
        if event.payload.value < midpoint:
            streak.append(event.ts)
        else:
            streak.clear()
        if len(streak) < self.config.consecutive_samples:
            return
        resolved = anomaly.model_copy(update={"state": "resolved", "resolved_ts": streak[0]})
        self.anomalies[self.anomalies.index(anomaly)] = resolved
        self.resolve_streaks[key] = []
        self._emit(event, "anomaly_resolved", {"anomaly_id": anomaly.anomaly_id})

    def _active_anomaly(self, service: str, metric: str) -> Anomaly | None:
        return next(
            (
                anomaly
                for anomaly in self.anomalies
                if anomaly.service == service
                and anomaly.metric == metric
                and anomaly.state == "active"
            ),
            None,
        )

    def _floor(self, metric: str) -> float:
        if metric == "error_rate":
            return self.config.error_rate_ratio_floor
        if metric == "packet_loss_pct":
            return 0.1
        return 1.0

    def _threshold(self, metric: str, baseline: float) -> float:
        c = self.config
        if metric == "latency_p95_ms":
            return c.latency_ratio * max(baseline, c.latency_floor)
        if metric == "error_rate":
            return max(
                c.error_rate_min, c.error_rate_ratio * max(baseline, c.error_rate_baseline_floor)
            )
        if metric == "active_connections":
            return c.connections_ratio * baseline
        if metric == "cpu_pct":
            return max(c.cpu_ratio * baseline, baseline + c.cpu_delta_pts)
        if metric == "network_delay_ms":
            return max(
                c.network_delay_ratio * max(baseline, 1.0),
                baseline + c.network_delay_delta_ms,
            )
        if metric == "packet_loss_pct":
            return max(c.packet_loss_ratio * max(baseline, 0.1), c.packet_loss_min_pct)
        return baseline + c.memory_delta_pts

    def _breaches(self, metric: str, value: float, baseline: float) -> bool:
        return value >= self._threshold(metric, baseline)

    def _refresh_health(self, event: MetricEvent) -> None:
        active = [anomaly for anomaly in self.anomalies if anomaly.state == "active"]
        for service in sorted(self.service_health):
            own = [anomaly for anomaly in active if anomaly.service == service]
            health = "healthy"
            if own:
                health = (
                    "failing"
                    if len(own) >= 2 or any(a.metric == "error_rate" for a in own)
                    else "degraded"
                )
            if self.service_health[service] != health:
                self.service_health[service] = health
                self._emit(event, "service_health_changed", {"service": service, "health": health})

    def _refresh_incident(self, event: MetricEvent) -> None:
        active = sorted(
            (anomaly for anomaly in self.anomalies if anomaly.state == "active"),
            key=lambda anomaly: (anomaly.onset_ts, anomaly.anomaly_id),
        )
        qualifies = len({anomaly.service for anomaly in active}) >= 2 or any(
            self.topology.topology.services[anomaly.service].tier == "customer_facing"
            for anomaly in active
        )
        active_ids = tuple(anomaly.anomaly_id for anomaly in active)
        if self.incident is None and active and not qualifies:
            if active_ids != self._pending_ids:
                self._pending_ids = active_ids
                self._emit(
                    event,
                    "pending_watch",
                    {"anomaly_ids": ",".join(active_ids)},
                )
        elif self.incident is None and qualifies:
            self._member_ids |= set(active_ids)
            self.incident = self._build_incident(self._members(), revision=1, opened_ts=event.ts)
            self._last_incident_activity_ts = event.ts
            self._incident_active_ids = active_ids
            self._pending_ids = ()
            self._emit(event, "incident_opened", {"incident_id": self.incident.incident_id})
        elif (
            self.incident is not None
            and self.incident.state == "open"
            and active
            and active_ids != self._incident_active_ids
        ):
            self._member_ids |= set(active_ids)
            self.incident = self._build_incident(
                self._members(),
                revision=self.incident.revision + 1,
                opened_ts=self.incident.opened_ts,
            )
            self._last_incident_activity_ts = event.ts
            self._incident_active_ids = active_ids
            self._emit(event, "incident_updated", {"incident_id": self.incident.incident_id})
        elif self.incident is not None and self.incident.state == "open" and not active:
            if event.ts - self._last_incident_activity_ts >= self.config.resolve_hold_s * 1000:
                self.incident = self.incident.model_copy(
                    update={
                        "state": "resolved",
                        "resolved_ts": event.ts,
                        "revision": self.incident.revision + 1,
                    }
                )
                self._emit(event, "incident_resolved", {"incident_id": self.incident.incident_id})

    def _members(self) -> list[Anomaly]:
        """All anomalies that joined the incident, active or healed (ranking must not drift as
        the root cause heals first and leaves downstream anomalies looking like roots)."""
        return sorted(
            (a for a in self.anomalies if a.anomaly_id in self._member_ids),
            key=lambda anomaly: (anomaly.onset_ts, anomaly.anomaly_id),
        )

    def _emit(self, event: MetricEvent, update_type: str, payload: dict[str, str]) -> None:
        self.updates.append(
            EngineUpdate(
                run_id=self.run_id,
                seq=event.seq,
                sim_ts=event.ts,
                type=update_type,
                payload=payload,
            )
        )

    def _relations(self, anomalies: list[Anomaly]) -> dict[str, Parent]:
        parents: dict[str, Parent] = {}
        for child in anomalies:
            options: list[Parent] = []
            for parent in anomalies:
                if parent.onset_ts > child.onset_ts - self.config.delta_s * 1000:
                    continue
                relation = self._relation(parent, child)
                if relation is not None:
                    via, weight = relation
                    options.append(Parent(parent, via, weight))
            if options:
                parents[child.anomaly_id] = sorted(
                    options,
                    key=lambda option: (
                        -option.weight,
                        option.anomaly.onset_ts,
                        option.anomaly.anomaly_id,
                    ),
                )[0]
        return parents

    def _relation(self, parent: Anomaly, child: Anomaly) -> tuple[str, float] | None:
        if parent.service == child.service:
            return "self", 1.0
        callers = self.topology.callers(parent.service, 4, True)
        if child.service in callers:
            return "fault", round(0.9 ** (callers[child.service] - 1), 4)
        if child.service in self.topology.callees(parent.service, 1):
            return "load", 0.7
        return None

    def _rank(
        self, anomalies: list[Anomaly]
    ) -> tuple[list[Candidate], list[RejectedCandidate], dict[str, Parent]]:
        parents = self._relations(anomalies)
        roots = [anomaly for anomaly in anomalies if anomaly.anomaly_id not in parents]
        attached: set[str] = set()
        raw: list[tuple[Candidate, int]] = []
        rejected: list[RejectedCandidate] = []
        first_ts = min(anomaly.onset_ts for anomaly in anomalies)
        for deployment in self.deployments:
            reachable = {deployment.service, *self.topology.callers(deployment.service, 4, True)}
            nearby = [anomaly for anomaly in anomalies if anomaly.service in reachable]
            matched = [
                root
                for root in roots
                if root.service in reachable
                and 0 <= root.onset_ts - deployment.ts <= self.config.lookback_s * 1000
            ]
            if matched:
                attached.update(root.anomaly_id for root in matched)
                raw.append(
                    (self._candidate(deployment, matched, anomalies, parents), deployment.ts)
                )
                continue
            reason = self._rejection_reason(deployment, nearby, roots, first_ts)
            rejected.append(
                RejectedCandidate(
                    candidate_id=f"deployment:{deployment.id}",
                    service=deployment.service,
                    reason_code=reason,
                    statement=f"Deployment {deployment.id} on {deployment.service} rejected: "
                    f"{REASON_TEXT[reason]}.",
                )
            )
        for root in roots:
            if root.anomaly_id not in attached:
                raw.append((self._candidate(None, [root], anomalies, parents), root.onset_ts))
        raw.sort(key=lambda item: (-item[0].score, item[1], item[0].candidate_id))
        ranked = [
            candidate.model_copy(update={"rank": index})
            for index, (candidate, _) in enumerate(raw, 1)
        ]
        return ranked, rejected, parents

    def _rejection_reason(
        self, deployment: Deployment, nearby: list[Anomaly], roots: list[Anomaly], first_ts: int
    ) -> str:
        if not nearby:
            return "NO_ANOMALY_ON_SERVICE_OR_REACHABLE"
        root_ids = {root.anomaly_id for root in roots}
        inside = [
            anomaly
            for anomaly in nearby
            if 0 <= anomaly.onset_ts - deployment.ts <= self.config.lookback_s * 1000
        ]
        if inside and not any(anomaly.anomaly_id in root_ids for anomaly in inside):
            return "ANOMALY_EXPLAINED_BY_EARLIER_CAUSE"
        if all(
            anomaly.onset_ts < deployment.ts - self.config.epsilon_s * 1000 for anomaly in nearby
        ):
            return "ANOMALY_PRECEDES_DEPLOYMENT"
        if first_ts - deployment.ts > self.config.lookback_s * 1000:
            return "OUTSIDE_LOOKBACK_WINDOW"
        return "NO_ANOMALY_ON_SERVICE_OR_REACHABLE"

    def _candidate(
        self,
        deployment: Deployment | None,
        roots: list[Anomaly],
        anomalies: list[Anomaly],
        parents: dict[str, Parent],
    ) -> Candidate:
        root_ids = {root.anomaly_id for root in roots}
        covered = [anomaly for anomaly in anomalies if self._root_id(anomaly, parents) in root_ids]
        weights = {
            anomaly.anomaly_id: self._coverage_weight(anomaly, parents) for anomaly in covered
        }
        candidate_ts = deployment.ts if deployment else min(root.onset_ts for root in roots)
        service = deployment.service if deployment else roots[0].service
        cfg = self.config
        first_root = min(root.onset_ts for root in roots)
        t_min = min(a.onset_ts for a in anomalies)
        t_span = max(a.onset_ts for a in anomalies) - t_min
        if deployment:
            lead_s = (first_root - candidate_ts) / 1000
            temporal = exp(-(first_root - candidate_ts) / (cfg.temporal_tau_s * 1000))
            temporal_text = (
                f"Deployment {deployment.id} preceded the first attached anomaly by {lead_s:.0f}s"
            )
        else:
            offset_s = (candidate_ts - t_min) / 1000
            temporal = 1 - offset_s / (t_span / 1000 + 1)
            temporal_text = (
                "Earliest anomaly in the incident"
                if offset_s == 0
                else f"Started {offset_s:.0f}s after the earliest anomaly in the incident"
            )
        dependency = sum(weights.values()) / len(anomalies)
        strongest = max(roots, key=lambda root: (root.ratio, root.anomaly_id))
        strength = 1 - exp(-(strongest.ratio - 1) / cfg.strength_scale)
        affected_services = sorted({anomaly.service for anomaly in covered})
        all_services = self.topology.topology.services
        impact = sum(self.topology.tier_weight(name) for name in affected_services) / sum(
            self.topology.tier_weight(name) for name in all_services
        )
        facing = [n for n in affected_services if all_services[n].tier == "customer_facing"]
        values = {
            "temporal": (temporal, cfg.weights[0], temporal_text),
            "dependency_consistency": (
                dependency,
                cfg.weights[1],
                f"{len(covered)} of {len(anomalies)} incident anomalies are explained by "
                "this candidate's causal chain",
            ),
            "anomaly_strength": (
                strength,
                cfg.weights[2],
                f"Strongest attached anomaly: {strongest.service} {strongest.metric} "
                f"{strongest.ratio:.1f}x baseline",
            ),
            "downstream_impact": (
                impact,
                cfg.weights[3],
                f"Covers {', '.join(facing)} (customer-facing)"
                if facing
                else f"Covers {len(affected_services)} of {len(all_services)} services",
            ),
        }
        factors = {
            name: Factor(
                value=round(value, 4),
                weight=weight,
                contribution=round(value * weight, 4),
                explanation=text,
            )
            for name, (value, weight, text) in values.items()
        }
        score = round(sum(factor.contribution for factor in factors.values()), 4)
        return Candidate(
            candidate_id=f"deployment:{deployment.id}"
            if deployment
            else f"service_fault:{service}",
            kind="deployment" if deployment else "service_fault",
            service=service,
            deployment_id=deployment.id if deployment else None,
            rank=0,
            score=score,
            factors=factors,
            root_anomaly_ids=sorted(root_ids),
            covered_anomaly_ids=[anomaly.anomaly_id for anomaly in covered],
            evidence_ids=[],
            chain=self._chain(deployment, covered, parents),
        )

    @staticmethod
    def _root_id(anomaly: Anomaly, parents: dict[str, Parent]) -> str:
        current = anomaly
        while current.anomaly_id in parents:
            current = parents[current.anomaly_id].anomaly
        return current.anomaly_id

    @staticmethod
    def _coverage_weight(anomaly: Anomaly, parents: dict[str, Parent]) -> float:
        weight = 1.0
        current = anomaly
        while current.anomaly_id in parents:
            parent = parents[current.anomaly_id]
            weight *= parent.weight
            current = parent.anomaly
        return round(weight, 4)

    def _chain(
        self, deployment: Deployment | None, covered: list[Anomaly], parents: dict[str, Parent]
    ) -> list[ChainStep]:
        customer_facing = [
            anomaly
            for anomaly in covered
            if self.topology.topology.services[anomaly.service].tier == "customer_facing"
        ]
        target = min(customer_facing, key=lambda a: (a.onset_ts, a.anomaly_id), default=None)
        if target is None:
            target = max(covered, key=lambda a: (a.onset_ts, a.anomaly_id))
        path = [target]
        while path[-1].anomaly_id in parents:
            path.append(parents[path[-1].anomaly_id].anomaly)
        path.reverse()
        steps: list[ChainStep] = []
        if deployment:
            steps.append(
                ChainStep(
                    step=1,
                    node_type="deployment",
                    ref=deployment.id,
                    service=deployment.service,
                    ts=deployment.ts,
                    via="change",
                    statement=f"Deployment {deployment.id} changed {deployment.service}",
                )
            )
        for anomaly in path:
            parent = parents.get(anomaly.anomaly_id)
            steps.append(
                ChainStep(
                    step=len(steps) + 1,
                    node_type="anomaly",
                    ref=anomaly.anomaly_id,
                    service=anomaly.service,
                    ts=anomaly.onset_ts,
                    via=parent.via if parent else "self",
                    statement=(
                        f"{anomaly.service} {anomaly.metric} reached {anomaly.ratio:.2f}x baseline"
                    ),
                )
            )
        return steps

    def _build_incident(self, active: list[Anomaly], revision: int, opened_ts: int) -> Incident:
        candidates, rejected, _ = self._rank(active)
        first_ts = min(anomaly.onset_ts for anomaly in active)
        evidence, by_candidate = self._evidence(active, candidates, rejected, first_ts)
        candidates = [
            candidate.model_copy(update={"evidence_ids": by_candidate[candidate.candidate_id]})
            for candidate in candidates
        ]
        changes = self._changes(first_ts, candidates, rejected)
        affected = sorted({anomaly.service for anomaly in active})
        customer_facing = sorted(
            service
            for service in affected
            if self.topology.topology.services[service].tier == "customer_facing"
        )
        margin = (
            candidates[0].score - candidates[1].score
            if len(candidates) > 1
            else candidates[0].score
        )
        return Incident(
            incident_id="INC-001",
            run_id=self.run_id,
            state="open",
            revision=revision,
            opened_ts=opened_ts,
            first_anomaly_ts=first_ts,
            anomalies=active,
            service_health={
                service: health
                for service, health in self.service_health.items()
                if health != "healthy"
            },
            candidates=candidates,
            rejected_candidates=rejected,
            ambiguous=len(candidates) > 1 and margin < self.config.ambiguity_margin,
            margin=round(margin, 4),
            what_changed=WhatChanged(
                healthy_until_ts=first_ts - self.topology.topology.sample_interval_s * 1000,
                first_anomaly_ts=first_ts,
                changes=changes,
                statement=self._what_changed_text(
                    first_ts, changes, candidates, rejected, len(active)
                ),
            ),
            blast_radius=BlastRadius(customer_facing_affected=customer_facing, services=affected),
            evidence=evidence,
        )

    def _evidence(
        self,
        anomalies: list[Anomaly],
        candidates: list[Candidate],
        rejected: list[RejectedCandidate],
        first_ts: int,
    ) -> tuple[list[Evidence], dict[str, list[str]]]:
        """Deterministic evidence (ENGINE_SPEC section 9) plus the ids supporting each candidate."""
        items: list[Evidence] = []

        def add(kind: str, ref: str, ts: int, statement: str, data: dict[str, str]) -> str:
            evidence_id = f"E-{len(items) + 1:04d}"
            items.append(
                Evidence(
                    evidence_id=evidence_id,
                    kind=kind,
                    ref=ref,
                    ts=ts,
                    statement=statement,
                    data=data,
                )
            )
            return evidence_id

        dep_ids: dict[str, str] = {}
        for d in self.deployments:
            version = f" ({d.version})" if d.version else ""
            lead = round((first_ts - d.ts) / 1000)
            when = f"{lead}s before the first anomaly" if lead >= 0 else "after the first anomaly"
            dep_ids[d.id] = add(
                "deployment", d.id, d.ts,
                f"Deployment {d.id}{version} changed {d.service} {when}.",
                {"service": d.service},
            )  # fmt: skip
        anomaly_ids = {
            a.anomaly_id: add(
                "anomaly", a.anomaly_id, a.onset_ts,
                f"{a.service} {a.metric} reached {a.ratio:.1f}x baseline.",
                {"service": a.service},
            )
            for a in anomalies
        }  # fmt: skip
        edge_ids: dict[tuple[str, str], str] = {}
        by_candidate: dict[str, list[str]] = {}
        blocking = {(e.from_, e.to): e.blocking for e in self.topology.topology.edges}
        for c in candidates:
            ids = [dep_ids[c.deployment_id]] if c.deployment_id else []
            ids += [anomaly_ids[i] for i in c.covered_anomaly_ids]
            chain = [s for s in c.chain if s.node_type == "anomaly"]
            for prev, step in zip(chain, chain[1:], strict=False):
                pair = (
                    (step.service, prev.service)
                    if step.via == "fault"
                    else (prev.service, step.service)
                )
                if pair not in blocking or pair[0] == pair[1]:
                    continue
                if pair not in edge_ids:
                    kind = "blocking" if blocking[pair] else "non-blocking"
                    edge_ids[pair] = add(
                        "topology", f"{pair[0]}->{pair[1]}", step.ts,
                        f"{pair[0]} calls {pair[1]} ({kind}).", {},
                    )  # fmt: skip
                ids.append(edge_ids[pair])
            by_candidate[c.candidate_id] = ids
        deployments = {f"deployment:{d.id}": d for d in self.deployments}
        for r in rejected:
            add("topology", r.candidate_id, deployments[r.candidate_id].ts, r.statement, {})
        return items, by_candidate

    def _what_changed_text(
        self,
        first_ts: int,
        changes: list[ChangeItem],
        candidates: list[Candidate],
        rejected: list[RejectedCandidate],
        total: int,
    ) -> str:
        healthy = first_ts - self.topology.topology.sample_interval_s * 1000
        parts = [f"All affected services were healthy until {_clock(healthy)}."]
        covered = {c.deployment_id: len(c.covered_anomaly_ids) for c in candidates}
        reasons = {r.candidate_id.removeprefix("deployment:"): r.reason_code for r in rejected}
        for ch in changes:
            head = f"Deployment {ch.deployment_id} on {ch.service}"
            if ch.relevant:
                parts.append(
                    f"{head} preceded the first anomaly by {ch.seconds_before_onset}s and its "
                    f"causal chain explains {covered[ch.deployment_id]} of {total} anomalies."
                )
            else:
                why = (
                    REASON_TEXT[reasons[ch.deployment_id]]
                    if ch.deployment_id in reasons
                    else "it was not attached"
                )
                parts.append(f"{head} also preceded onset but was rejected: {why}.")
        if not changes:
            parts.append("No deployments preceded onset.")
        return " ".join(parts)

    def _changes(
        self,
        first_ts: int,
        candidates: list[Candidate],
        rejected: list[RejectedCandidate],
    ) -> list[ChangeItem]:
        by_deployment = {
            candidate.deployment_id: candidate
            for candidate in candidates
            if candidate.deployment_id
        }
        rejected_by_id = {item.candidate_id.removeprefix("deployment:"): item for item in rejected}
        return [
            ChangeItem(
                kind="deployment",
                deployment_id=deployment.id,
                service=deployment.service,
                ts=deployment.ts,
                seconds_before_onset=int((first_ts - deployment.ts) / 1000),
                relevant=deployment.id in by_deployment,
                candidate_id=by_deployment[deployment.id].candidate_id
                if deployment.id in by_deployment
                else None,
                reason=rejected_by_id[deployment.id].reason_code
                if deployment.id in rejected_by_id
                else None,
            )
            for deployment in self.deployments
            if 0 <= first_ts - deployment.ts <= self.config.lookback_s * 1000
        ]

    def result(self) -> EngineResult:
        candidates = (
            self.incident.candidates if self.incident and self.incident.state == "open" else []
        )
        rejected = self.incident.rejected_candidates if self.incident else []
        return EngineResult(
            self.updates, self.anomalies, candidates, rejected, bool(candidates), self.incident
        )


def run_batch(
    events: Iterable[Event], topology: InMemoryTopology, config: EngineConfig | None = None
) -> EngineResult:
    ordered = list(events)
    if not ordered:
        return EngineResult([], [], [], [], False, None)
    state = EngineState(ordered[0].run_id, topology, config or EngineConfig())
    for event in ordered:
        state.ingest(event)
    return state.result()
