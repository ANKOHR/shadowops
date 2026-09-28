"""Deterministic generator for fictional, labelled company activity."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .model import DATA_LABEL, SEED


WORKFLOWS: list[dict[str, Any]] = [
    {
        "workflow_id": "weekly_invoicing",
        "name": "Weekly invoicing cycle",
        "sensitivity": "high",
        "steps": [
            ("review_timesheet", "staff timesheet", "calendar"),
            ("generate_invoice", "customer invoice", "csv"),
            ("email_invoice", "customer invoice", "email"),
            ("record_payment", "invoice payment", "file"),
        ],
    },
    {
        "workflow_id": "employee_onboarding",
        "name": "Employee onboarding sequence",
        "sensitivity": "medium",
        "steps": [
            ("create_account", "employee account", "file"),
            ("schedule_orientation", "orientation meeting", "calendar"),
            ("send_welcome_pack", "welcome pack", "email"),
            ("file_contract", "employment contract", "file"),
        ],
    },
    {
        "workflow_id": "expense_approval",
        "name": "Expense approval chain",
        "sensitivity": "high",
        "steps": [
            ("submit_expense", "expense claim", "csv"),
            ("manager_review", "expense claim", "calendar"),
            ("approve_payment", "expense payment", "email"),
            ("export_ledger", "general ledger", "csv"),
        ],
    },
    {
        "workflow_id": "newsletter_publish",
        "name": "Newsletter publishing cycle",
        "sensitivity": "low",
        "steps": [
            ("draft_newsletter", "newsletter draft", "file"),
            ("review_content", "newsletter content", "calendar"),
            ("schedule_campaign", "email campaign", "csv"),
            ("publish_newsletter", "subscriber newsletter", "email"),
        ],
    },
    {
        "workflow_id": "support_escalation",
        "name": "Support escalation sequence",
        "sensitivity": "medium",
        "steps": [
            ("classify_ticket", "support ticket", "email"),
            ("assign_engineer", "engineering ticket", "calendar"),
            ("send_status_update", "ticket status", "email"),
            ("close_ticket", "support ticket", "file"),
        ],
    },
]

ACTORS = ["alex.synthetic", "blair.synthetic", "casey.synthetic"]


def _timestamp(instance: int, step: int) -> str:
    start = datetime(2026, 1, 5, 9, tzinfo=timezone.utc)
    value = start + timedelta(days=instance * 7, minutes=step * 35)
    return value.isoformat().replace("+00:00", "Z")


def _records() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    emails: list[dict[str, str]] = []
    calendar: list[dict[str, str]] = []
    files: list[dict[str, str]] = []
    exports: list[dict[str, str]] = []
    for workflow in WORKFLOWS:
        for instance in range(3):
            case_id = f"{workflow['workflow_id']}-{instance + 1:02d}"
            for step_index, (action, object_name, channel) in enumerate(workflow["steps"]):
                common = {
                    "event_id": f"{case_id}-e{step_index + 1}",
                    "case_id": case_id,
                    "actor": ACTORS[(instance + step_index) % len(ACTORS)],
                    "action": action,
                    "object": object_name,
                    "timestamp": _timestamp(instance, step_index),
                    "sensitivity": workflow["sensitivity"],
                    "data_label": DATA_LABEL,
                }
                if channel == "email":
                    emails.append(
                        {
                            "message_id": common["event_id"],
                            "thread_id": case_id,
                            "sender": common["actor"],
                            "operation": action,
                            "subject": object_name,
                            "sent_at": common["timestamp"],
                            "case_ref": case_id,
                            "sensitivity": common["sensitivity"],
                            "data_label": DATA_LABEL,
                        }
                    )
                elif channel == "calendar":
                    calendar.append(
                        {
                            "event_id": common["event_id"],
                            "organizer": common["actor"],
                            "event_type": action,
                            "title": object_name,
                            "start": common["timestamp"],
                            "case_ref": case_id,
                            "sensitivity": common["sensitivity"],
                            "data_label": DATA_LABEL,
                        }
                    )
                elif channel == "file":
                    files.append(
                        {
                            "operation_id": common["event_id"],
                            "user": common["actor"],
                            "operation": action,
                            "path": f"/synthetic/{workflow['workflow_id']}/{object_name.replace(' ', '_')}",
                            "timestamp": common["timestamp"],
                            "case_ref": case_id,
                            "sensitivity": common["sensitivity"],
                            "data_label": DATA_LABEL,
                        }
                    )
                else:
                    exports.append(
                        {
                            "event_id": common["event_id"],
                            "case_id": case_id,
                            "actor": common["actor"],
                            "action": action,
                            "object": object_name,
                            "timestamp": common["timestamp"],
                            "sensitivity": common["sensitivity"],
                            "data_label": DATA_LABEL,
                        }
                    )
    return emails, calendar, files, exports


def _write_jsonl(path: Path, records: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def generate_fixtures(out_dir: str | Path) -> dict[str, Any]:
    """Write reproducible synthetic source files and separate ground truth."""
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "exports").mkdir(parents=True, exist_ok=True)
    emails, calendar, files, exports = _records()
    _write_jsonl(root / "emails.jsonl", emails)
    _write_jsonl(root / "calendar.jsonl", calendar)
    _write_jsonl(root / "file_operations.jsonl", files)
    with (root / "exports" / "activity.csv").open("w", encoding="utf-8", newline="") as handle:
        columns = ["event_id", "case_id", "actor", "action", "object", "timestamp", "sensitivity", "data_label"]
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(exports)
    truth = {
        "data_label": DATA_LABEL,
        "seed": SEED,
        "workflows": [
            {
                "workflow_id": workflow["workflow_id"],
                "name": workflow["name"],
                "expected_steps": [step[0] for step in workflow["steps"]],
                "instances": 3,
            }
            for workflow in WORKFLOWS
        ],
    }
    with (root / "ground_truth.json").open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(truth, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    return {
        "data_label": DATA_LABEL,
        "out_dir": str(root),
        "seed": SEED,
        "workflow_count": len(WORKFLOWS),
        "event_count": len(emails) + len(calendar) + len(files) + len(exports),
        "ground_truth": str(root / "ground_truth.json"),
    }

