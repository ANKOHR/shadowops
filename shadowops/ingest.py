"""Deterministic parsers for generated email, calendar, CSV, and file events."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Callable

from .model import DATA_LABEL, Event

LOGGER = logging.getLogger("shadowops.ingest")


def _required(record: dict[str, object], key: str) -> str:
    value = record.get(key)
    if value is None or not str(value).strip():
        raise ValueError(f"missing {key}")
    return str(value).strip()


def _make_event(
    record: dict[str, object],
    *,
    event_id: str,
    case_id: str,
    actor: str,
    action: str,
    object_name: str,
    timestamp: str,
    channel: str,
    source: str,
) -> Event:
    data_label = str(record.get("data_label", "")).strip()
    if data_label != DATA_LABEL:
        raise ValueError("record is missing the synthetic data label")
    sensitivity = str(record.get("sensitivity", "low")).strip().lower()
    if sensitivity not in {"low", "medium", "high"}:
        raise ValueError("invalid sensitivity")
    return Event(
        event_id=event_id,
        case_id=case_id,
        actor=actor,
        action=action,
        object=object_name,
        timestamp=timestamp,
        channel=channel,
        source=source,
        sensitivity=sensitivity,
        data_label=data_label,
    )


def _parse_record(source: str, record: dict[str, object]) -> Event:
    if source == "emails":
        return _make_event(
            record,
            event_id=_required(record, "message_id"),
            case_id=_required(record, "case_ref"),
            actor=_required(record, "sender"),
            action=_required(record, "operation"),
            object_name=_required(record, "subject"),
            timestamp=_required(record, "sent_at"),
            channel="email",
            source=source,
        )
    if source == "calendar":
        return _make_event(
            record,
            event_id=_required(record, "event_id"),
            case_id=_required(record, "case_ref"),
            actor=_required(record, "organizer"),
            action=_required(record, "event_type"),
            object_name=_required(record, "title"),
            timestamp=_required(record, "start"),
            channel="calendar",
            source=source,
        )
    if source == "file_operations":
        return _make_event(
            record,
            event_id=_required(record, "operation_id"),
            case_id=_required(record, "case_ref"),
            actor=_required(record, "user"),
            action=_required(record, "operation"),
            object_name=_required(record, "path"),
            timestamp=_required(record, "timestamp"),
            channel="file",
            source=source,
        )
    return _make_event(
        record,
        event_id=_required(record, "event_id"),
        case_id=_required(record, "case_id"),
        actor=_required(record, "actor"),
        action=_required(record, "action"),
        object_name=_required(record, "object"),
        timestamp=_required(record, "timestamp"),
        channel="csv",
        source=source,
    )


def _jsonl(path: Path, source: str) -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    errors: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("record must be a JSON object")
                events.append(_parse_record(source, record))
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                message = f"{path.name}:{line_number}: {error}"
                errors.append(message)
                LOGGER.warning("Skipping malformed synthetic activity record %s", message)
    return events, errors


def _csv(path: Path) -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    errors: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, 2):
            try:
                if None in row:
                    raise ValueError("row has more cells than the header")
                events.append(_parse_record("csv", row))
            except (ValueError, TypeError) as error:
                message = f"{path.name}:{line_number}: {error}"
                errors.append(message)
                LOGGER.warning("Skipping malformed synthetic activity record %s", message)
    return events, errors


def ingest_activity(root: str | Path) -> tuple[list[Event], list[str]]:
    """Parse supported source formats while logging and skipping bad rows."""
    base = Path(root)
    parsers: dict[str, Callable[[Path], tuple[list[Event], list[str]]]] = {
        "emails.jsonl": lambda path: _jsonl(path, "emails"),
        "calendar.jsonl": lambda path: _jsonl(path, "calendar"),
        "file_operations.jsonl": lambda path: _jsonl(path, "file_operations"),
    }
    events: list[Event] = []
    errors: list[str] = []
    for filename, parser in parsers.items():
        for path in sorted(base.rglob(filename)):
            parsed, skipped = parser(path)
            events.extend(parsed)
            errors.extend(skipped)
    for path in sorted(base.rglob("*.csv")):
        parsed, skipped = _csv(path)
        events.extend(parsed)
        errors.extend(skipped)
    events.sort(key=lambda event: (event.timestamp, event.case_id, event.event_id, event.source))
    return events, errors

