"""Reset the working database to the original shop values.

Copies data/campus_customs.db (never modified) over data/campus_customs_new.db.
Run this before every full ticket run. output/audit_trail.json is NOT touched --
the audit trail is append-only across runs.

    python scripts/reset_db.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = ROOT / "data" / "campus_customs.db"
WORKING = ROOT / "data" / "campus_customs_new.db"


def reset() -> None:
    if not ORIGINAL.exists():
        raise SystemExit(f"Original database missing: {ORIGINAL}")
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{WORKING}{suffix}").unlink(missing_ok=True)
    shutil.copyfile(ORIGINAL, WORKING)
    print(f"Reset {WORKING.relative_to(ROOT)} from {ORIGINAL.relative_to(ROOT)}")


if __name__ == "__main__":
    reset()
