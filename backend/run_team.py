"""Run the Campus Customs agent team on tickets from the command line.

    cd backend
    ../.venv/bin/python run_team.py --reset --all        # fresh DB, every open ticket
    ../.venv/bin/python run_team.py --ticket 102         # one ticket on the current DB

--reset copies data/campus_customs.db over the working copy first (do this before every
full run). The audit trail in output/audit_trail.json is appended to, never wiped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from config import ROOT
from team import Team

sys.path.insert(0, str(ROOT / "scripts"))
from reset_db import reset  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticket", type=int, action="append", help="ticket id (repeatable)")
    parser.add_argument("--all", action="store_true", help="run every open ticket, oldest first")
    parser.add_argument("--reset", action="store_true", help="reset the working DB to the original first")
    args = parser.parse_args()
    if not args.ticket and not args.all:
        parser.error("pass --ticket N or --all")
    if args.reset:
        reset()

    async with Team() as team:
        decisions = await team.run_open_tickets() if args.all else [await team.run_ticket(t) for t in args.ticket]
    for d in decisions:
        print(json.dumps(d.model_dump() if d else None, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
