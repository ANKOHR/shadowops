from __future__ import annotations

import json
import logging
from pathlib import Path

from shadowops.cli import main
from shadowops.discovery import candidates, discover, estimate_hours, score_ground_truth
from shadowops.fixtures import generate_fixtures
from shadowops.ingest import ingest_activity
from shadowops.model import DATA_LABEL


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_fixtures_are_deterministic_and_labelled(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_fixtures(first)
    generate_fixtures(second)
    assert _tree_bytes(first) == _tree_bytes(second)
    truth = json.loads((first / "ground_truth.json").read_text(encoding="utf-8"))
    assert truth["data_label"] == DATA_LABEL
    assert len(truth["workflows"]) == 5
    assert all(item["expected_steps"] and item["instances"] >= 2 for item in truth["workflows"])
    activity_bytes = b"".join(
        path.read_bytes()
        for path in sorted(first.rglob("*"))
        if path.is_file() and path.name != "ground_truth.json"
    )
    assert all(item["workflow_id"].encode("utf-8") not in activity_bytes for item in truth["workflows"])


def test_ingestion_parses_every_source_and_skips_malformed(tmp_path: Path, caplog) -> None:
    corpus = tmp_path / "corpus"
    generate_fixtures(corpus)
    events, errors = ingest_activity(corpus)
    assert not errors
    assert {event.source for event in events} == {"emails", "calendar", "file_operations", "csv"}
    assert {event.channel for event in events} == {"email", "calendar", "file", "csv"}
    assert all(event.actor and event.action and event.object and event.timestamp for event in events)
    assert all(event.data_label == DATA_LABEL for event in events)

    with (corpus / "emails.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{bad json}\n")
    with (corpus / "exports" / "activity.csv").open("a", encoding="utf-8") as handle:
        handle.write("too,few,cells\n")
    with caplog.at_level(logging.WARNING, logger="shadowops.ingest"):
        recovered, errors = ingest_activity(corpus)
    assert len(recovered) == len(events)
    assert len(errors) == 2
    assert "Skipping malformed synthetic activity record" in caplog.text


def test_sequence_mining_reconstructs_planted_workflows(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    generate_fixtures(corpus)
    result = discover(str(corpus))
    score = score_ground_truth(result, str(corpus / "ground_truth.json"))
    assert score["precision"] == 1.0
    assert score["recall"] == 1.0
    assert score["passes_threshold"] is True
    assert len(result["processes"]) == 5
    assert result["graph"]["edges"]


def test_graph_and_candidate_ranking_are_deterministic(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    generate_fixtures(corpus)
    first = discover(str(corpus))
    second = discover(str(corpus))
    assert json.dumps(first["graph"], sort_keys=True, indent=2) == json.dumps(second["graph"], sort_keys=True, indent=2)
    assert json.dumps(candidates(first), sort_keys=True) == json.dumps(candidates(second), sort_keys=True)


def test_estimation_model_matches_hand_calculation() -> None:
    estimate = estimate_hours({"review_timesheet": 2})
    assert estimate["estimated_hours_wasted"] == 0.186667
    assert estimate["evidence"] == [
        {
            "step": "review_timesheet",
            "events_count": 2,
            "minutes_per_event_assumption": 8,
            "gross_minutes": 16,
            "waste_share_assumption": 0.70,
            "estimated_wasted_minutes": 11.2,
            "estimated_wasted_hours": 0.186667,
        }
    ]
    assert estimate["model"]["estimated_labor_value_gbp"] == 6.07


def test_payment_risk_exceeds_newsletter_risk_with_reasons(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    generate_fixtures(corpus)
    ranked = candidates(discover(str(corpus)))
    payment = next(item for item in ranked if "approve_payment" in item["steps"])
    newsletter = next(item for item in ranked if "publish_newsletter" in item["steps"])
    assert payment["risk"]["score"] > newsletter["risk"]["score"]
    assert payment["risk"]["level"] == "high"
    assert payment["risk"]["dimensions"]["data_sensitivity"]["level"] == "high"
    assert payment["risk"]["dimensions"]["data_sensitivity"]["reason"]
    assert payment["risk"]["dimensions"]["blast_radius"]["reason"]


def test_cli_smoke_for_each_subcommand(tmp_path: Path, capsys) -> None:
    corpus = tmp_path / "cli-corpus"
    assert main(["fixtures", "--out", str(corpus)]) == 0
    fixture_output = json.loads(capsys.readouterr().out)
    assert fixture_output["data_label"] == DATA_LABEL

    assert main(["discover", "--in", str(corpus)]) == 0
    discovery_output = json.loads(capsys.readouterr().out)
    assert len(discovery_output["processes"]) == 5
    assert "not measured" in discovery_output["honesty_note"]

    assert main(["score", "--in", str(corpus), "--ground-truth", str(corpus / "ground_truth.json")]) == 0
    score_output = json.loads(capsys.readouterr().out)
    assert score_output["passes_threshold"] is True

    assert main(["candidates", "--in", str(corpus)]) == 0
    candidate_output = json.loads(capsys.readouterr().out)
    assert candidate_output["candidates"]

    assert main(["spec", "top", "--in", str(corpus)]) == 0
    spec_output = json.loads(capsys.readouterr().out)
    assert spec_output["human_checkpoints"]
