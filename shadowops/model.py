"""Canonical event model and transparent scoring assumptions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DATA_LABEL = "SYNTHETIC GENERATED ACTIVITY"
HONESTY_NOTE = (
    "Demo on fictional synthetic data only. Hours-wasted estimates are computed "
    "from a transparent model and are not measured from real companies."
)
SEED = 20260928
MIN_SUPPORT = 2
WASTE_SHARE = 0.70
WAGE_PROXY_GBP_PER_HOUR = 32.50
AUTOMATION_RATE = 0.80

TIME_PER_STEP_MINUTES: dict[str, int] = {
    "review_timesheet": 8,
    "generate_invoice": 6,
    "email_invoice": 2,
    "record_payment": 4,
    "create_account": 10,
    "schedule_orientation": 4,
    "send_welcome_pack": 5,
    "file_contract": 3,
    "submit_expense": 4,
    "manager_review": 8,
    "approve_payment": 5,
    "export_ledger": 3,
    "draft_newsletter": 25,
    "review_content": 10,
    "schedule_campaign": 5,
    "publish_newsletter": 2,
    "classify_ticket": 3,
    "assign_engineer": 2,
    "send_status_update": 3,
    "close_ticket": 2,
}


@dataclass(frozen=True)
class Event:
    event_id: str
    case_id: str
    actor: str
    action: str
    object: str
    timestamp: str
    channel: str
    source: str
    sensitivity: str
    data_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "case_id": self.case_id,
            "actor": self.actor,
            "action": self.action,
            "object": self.object,
            "timestamp": self.timestamp,
            "channel": self.channel,
            "source": self.source,
            "sensitivity": self.sensitivity,
            "data_label": self.data_label,
        }

