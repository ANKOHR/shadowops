"""Sequence mining, graph construction, model estimates, and risk scoring."""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import re
from typing import Any, Iterable

from .ingest import ingest_activity
from .model import (
    AUTOMATION_RATE,
    HONESTY_NOTE,
    MIN_SUPPORT,
    TIME_PER_STEP_MINUTES,
    WAGE_PROXY_GBP_PER_HOUR,
    WASTE_SHARE,
    Event,
)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _title(action: str) -> str:
    return action.replace("_", " ").title()


def _process_id(steps: tuple[str, ...]) -> str:
    digest = sha256("|".join(steps).encode("utf-8")).hexdigest()[:10]
    return f"process-{digest}"


def estimate_hours(step_counts: dict[str, int], waste_share: float = WASTE_SHARE) -> dict[str, Any]:
    """Calculate modelled avoidable hours from counts and fixed duration assumptions."""
    evidence = []
    total_minutes = 0
    for action, count in sorted(step_counts.items()):
        minutes_each = TIME_PER_STEP_MINUTES.get(action, 5)
        gross_minutes = minutes_each * count
        wasted_minutes = gross_minutes * waste_share
        total_minutes += gross_minutes
        evidence.append(
            {
                "step": action,
                "events_count": count,
                "minutes_per_event_assumption": minutes_each,
                "gross_minutes": gross_minutes,
                "waste_share_assumption": waste_share,
                "estimated_wasted_minutes": wasted_minutes,
                "estimated_wasted_hours": round(wasted_minutes / 60, 6),
            }
        )
    estimated_hours = round(total_minutes * waste_share / 60, 6)
    return {
        "estimated_hours_wasted": estimated_hours,
        "evidence": evidence,
        "model": {
            "formula": "sum(events_count * assumed_minutes_per_event) * waste_share / 60",
            "waste_share": waste_share,
            "unknown_step_minutes_default": 5,
            "wage_proxy_gbp_per_hour": WAGE_PROXY_GBP_PER_HOUR,
            "estimated_labor_value_gbp": round(estimated_hours * WAGE_PROXY_GBP_PER_HOUR, 2),
            "status": "model-based estimate, not measured savings",
        },
    }


def _risk(events: Iterable[Event], steps: tuple[str, ...]) -> dict[str, Any]:
    event_list = list(events)
    sensitivity_rank = {"low": 1, "medium": 2, "high": 3}
    sensitivity = max((event.sensitivity for event in event_list), key=lambda item: sensitivity_rank[item])
    payment_touch = any("payment" in step or "invoice" in step or "expense" in step for step in steps)
    external_touch = any(step.startswith("send_") or step.startswith("publish_") or step == "email_invoice" for step in steps)
    hard_to_reverse = any(step in {"record_payment", "approve_payment", "publish_newsletter", "close_ticket"} for step in steps)
    blast_radius = "high" if payment_touch else "medium" if external_touch else "low"
    reversibility = "hard" if hard_to_reverse else "moderate" if external_touch else "easy"
    score = (
        sensitivity_rank[sensitivity] * 2
        + {"low": 1, "medium": 2, "high": 3}[blast_radius]
        + {"easy": 1, "moderate": 2, "hard": 3}[reversibility]
    )
    level = "high" if score >= 10 else "medium" if score >= 6 else "low"
    return {
        "level": level,
        "score": score,
        "dimensions": {
            "data_sensitivity": {
                "level": sensitivity,
                "reason": f"Highest sensitivity found on {sum(event.sensitivity == sensitivity for event in event_list)} event(s).",
            },
            "blast_radius": {
                "level": blast_radius,
                "reason": "Payment or invoice actions can affect financial records." if payment_touch else "Outbound communications can reach people outside the process team." if external_touch else "Observed steps are limited to internal work items.",
            },
            "reversibility": {
                "level": reversibility,
                "reason": "A payment, publication, or ticket closure can be difficult to undo." if hard_to_reverse else "Outbound communications may require a follow-up correction." if external_touch else "Observed internal changes are expected to be straightforward to correct.",
            },
        },
        "scoring_rule": "risk score = 2 * sensitivity rank + blast radius rank + reversibility rank; low below 6, medium 6 to 9, high 10 or above",
    }


def discover(root: str) -> dict[str, Any]:
    events, errors = ingest_activity(root)
    by_case: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        by_case[event.case_id].append(event)
    sequences: dict[tuple[str, ...], list[list[Event]]] = defaultdict(list)
    for case_id in sorted(by_case):
        case_events = sorted(by_case[case_id], key=lambda event: (event.timestamp, event.event_id, event.source))
        steps = tuple(event.action for event in case_events)
        if steps:
            sequences[steps].append(case_events)

    processes: list[dict[str, Any]] = []
    node_counts: Counter[str] = Counter()
    edge_counts: Counter[tuple[str, str]] = Counter()
    edge_cases: Counter[tuple[str, str]] = Counter()
    for steps, instances in sorted(sequences.items()):
        if len(instances) < MIN_SUPPORT:
            continue
        process_events = [event for instance in instances for event in instance]
        step_counts = Counter(event.action for event in process_events)
        objects_by_step: dict[str, list[str]] = defaultdict(list)
        channels_by_step: dict[str, set[str]] = defaultdict(set)
        for event in process_events:
            objects_by_step[event.action].append(event.object)
            channels_by_step[event.action].add(event.channel)
        model = estimate_hours(dict(step_counts))
        process_id = _process_id(steps)
        node_counts.update(step_counts)
        case_edge_counts: Counter[tuple[str, str]] = Counter()
        for instance in instances:
            for source, target in zip(instance, instance[1:]):
                edge_counts[(source.action, target.action)] += 1
                case_edge_counts[(source.action, target.action)] += 1
        edge_cases.update(case_edge_counts)
        processes.append(
            {
                "process_id": process_id,
                "name": f"{_title(steps[0])} to {_title(steps[-1])}",
                "steps": list(steps),
                "frequency": len(instances),
                "case_ids": sorted(instance[0].case_id for instance in instances),
                "actors": sorted({event.actor for event in process_events}),
                "channels": sorted({event.channel for event in process_events}),
                "channels_by_step": {step: sorted(values) for step, values in sorted(channels_by_step.items())},
                "objects_by_step": {step: sorted(set(values)) for step, values in sorted(objects_by_step.items())},
                "step_counts": dict(sorted(step_counts.items())),
                "estimated_hours": model,
                "risk": _risk(process_events, steps),
                "evidence": {
                    "event_ids": sorted(event.event_id for event in process_events),
                    "source_counts": dict(sorted(Counter(event.source for event in process_events).items())),
                    "frequency_basis": "distinct case_id values with the exact ordered step sequence",
                },
            }
        )

    processes.sort(key=lambda item: (item["steps"], item["process_id"]))
    nodes = [
        {"id": action, "label": _title(action), "frequency_count": node_counts[action]}
        for action in sorted(node_counts)
    ]
    edges = [
        {
            "source": source,
            "target": target,
            "frequency_count": edge_counts[(source, target)],
            "case_frequency": edge_cases[(source, target)],
        }
        for source, target in sorted(edge_counts)
    ]
    return {
        "data_label": "SYNTHETIC GENERATED ACTIVITY ONLY",
        "honesty_note": HONESTY_NOTE,
        "events_parsed": len(events),
        "malformed_records_skipped": len(errors),
        "ingestion_warnings": errors,
        "minimum_sequence_support": MIN_SUPPORT,
        "graph": {"nodes": nodes, "edges": edges},
        "processes": processes,
    }


def candidates(discovery_result: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for process in discovery_result["processes"]:
        hours = process["estimated_hours"]["estimated_hours_wasted"]
        estimated_value = round(hours * WAGE_PROXY_GBP_PER_HOUR * AUTOMATION_RATE, 2)
        candidate_id = "candidate-" + _slug(process["steps"][0]) + "-" + process["process_id"].removeprefix("process-")
        ranked.append(
            {
                "candidate_id": candidate_id,
                "process_id": process["process_id"],
                "name": process["name"],
                "steps": process["steps"],
                "frequency": process["frequency"],
                "channels_by_step": process["channels_by_step"],
                "objects_by_step": process["objects_by_step"],
                "estimated_hours_wasted": hours,
                "automation_value_score_gbp": estimated_value,
                "risk": process["risk"],
                "evidence": {
                    "case_ids": process["case_ids"],
                    "step_counts": process["step_counts"],
                    "hours_model_evidence": process["estimated_hours"]["evidence"],
                    "value_formula": "estimated_hours_wasted * wage_proxy_gbp_per_hour * automation_rate",
                    "wage_proxy_gbp_per_hour": WAGE_PROXY_GBP_PER_HOUR,
                    "automation_rate_assumption": AUTOMATION_RATE,
                },
            }
        )
    ranked.sort(key=lambda item: (-item["automation_value_score_gbp"], item["risk"]["score"], item["candidate_id"]))
    for rank, candidate in enumerate(ranked, 1):
        candidate["rank"] = rank
    return ranked


def implementation_spec(candidate: dict[str, Any]) -> dict[str, Any]:
    steps = candidate["steps"]
    checkpoints = []
    if any("payment" in step or "invoice" in step or "expense" in step for step in steps):
        checkpoints.append("A named finance approver reviews every payment amount and destination before submission.")
    if any(step.startswith("send_") or step.startswith("publish_") or step == "email_invoice" for step in steps):
        checkpoints.append("A human reviews recipient, content, and attachment before any external message is sent.")
    if not checkpoints:
        checkpoints.append("A process owner reviews exceptions and approves the first production run.")
    return {
        "data_label": "SYNTHETIC GENERATED ACTIVITY ONLY",
        "honesty_note": HONESTY_NOTE,
        "candidate_id": candidate["candidate_id"],
        "process_name": candidate["name"],
        "purpose": "Automate the repeated handoffs observed in the synthetic activity sample, with model estimates only.",
        "inputs": [
            {
                "step": action,
                "observed_objects": candidate["objects_by_step"][action],
                "source_channels": candidate["channels_by_step"][action],
            }
            for action in steps
        ],
        "outputs": [
            {"artifact": steps[-1].replace("_", " "), "destination": "existing system of record selected during implementation"}
        ],
        "trigger": {"event": steps[0], "rule": "Start when the first step is recorded for a new case."},
        "validation_rules": [
            "Require a stable case identifier and reject duplicate event identifiers.",
            "Check required fields and valid timestamps before moving to the next step.",
            "Stop on missing records, conflicting values, or a step arriving out of sequence.",
            "Record an auditable result for every action and exception.",
        ],
        "human_checkpoints": checkpoints,
        "risk": candidate["risk"],
        "estimated_hours_wasted": candidate["estimated_hours_wasted"],
        "estimate_label": "Model-based estimate, not measured savings.",
    }


def score_ground_truth(discovery_result: dict[str, Any], ground_truth_path: str) -> dict[str, Any]:
    import json
    from pathlib import Path

    truth = json.loads(Path(ground_truth_path).read_text(encoding="utf-8"))
    expected = {tuple(item["expected_steps"]): item for item in truth.get("workflows", [])}
    predicted = {tuple(item["steps"]): item for item in discovery_result["processes"]}
    matched_sequences = sorted(set(expected).intersection(predicted))
    true_positive = len(matched_sequences)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    return {
        "data_label": "SYNTHETIC GENERATED ACTIVITY ONLY",
        "honesty_note": HONESTY_NOTE,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "threshold": 0.80,
        "passes_threshold": precision >= 0.80 and recall >= 0.80,
        "true_positive_processes": true_positive,
        "predicted_process_count": len(predicted),
        "ground_truth_process_count": len(expected),
        "matched_workflows": [expected[sequence]["workflow_id"] for sequence in matched_sequences],
        "unmatched_ground_truth": [
            item["workflow_id"] for sequence, item in sorted(expected.items()) if sequence not in predicted
        ],
        "unmatched_predictions": [
            process["process_id"] for sequence, process in sorted(predicted.items()) if sequence not in expected
        ],
    }
