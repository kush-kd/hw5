"""Append-only audit trail at output/audit_trail.json.

The file is a JSON array. Each append re-reads it, adds one event, and atomically
replaces the file, so a crash never leaves half-written JSON and earlier runs are
never wiped. If the file is ever unreadable it is set aside (renamed), not deleted.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import AUDIT_PATH
from models import AuditEvent

_lock = threading.Lock()


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text() or "[]")
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path.rename(path.with_name(f"{path.stem}.unreadable-{stamp}.json"))
    return []


def log(
    event: str,
    *,
    run_id: str,
    ticket_id: int | None = None,
    agent: str | None = None,
    chain: tuple[str, ...] | list[str] = (),
    depth: int = 0,
    step: int | None = None,
    path: Path = AUDIT_PATH,
    **data: Any,
) -> None:
    record = AuditEvent(
        event_id=uuid.uuid4().hex,
        logged_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        run_id=run_id,
        ticket_id=ticket_id,
        agent=agent,
        chain=list(chain),
        depth=depth,
        step=step,
        event=event,
        data=data,
    ).model_dump(mode="json")
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        events = _load(path)
        events.append(record)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(events, indent=2, default=str) + "\n")
        tmp.replace(path)
