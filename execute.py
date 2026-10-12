"""Maintenance script for Thinking Recovery.

Prunes expired sidecar snapshots and prints current state inventory.
Safe to run repeatedly.
"""

import os
import sys

if __name__ == "__main__":
    # Standalone execution (framework runs this file directly via
    # [python, execute.py]): make the A0 root importable so plugin-local
    # imports resolve. Also drop this script's own directory from sys.path:
    # its local helpers/ package would otherwise shadow the framework's
    # helpers package. Library consumers are unaffected.
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    _A0_ROOT = os.path.abspath(
        os.path.join(_SCRIPT_DIR, "..", "..", "..")
    )
    sys.path[:] = [
        entry for entry in sys.path
        if os.path.abspath(entry or ".") != _SCRIPT_DIR
    ]
    if _A0_ROOT not in sys.path:
        sys.path.insert(0, _A0_ROOT)

from usr.plugins.thinking_recovery.helpers import recovery


def main() -> int:
    print("Thinking Recovery maintenance")
    print("=============================")

    settings = recovery.get_settings()
    ttl_days = float(settings.get("state_ttl_days", 7))

    removed = recovery.prune_old_states(ttl_days)
    print(f"Pruned {removed} sidecar file(s) older than {ttl_days} day(s).")

    entries = recovery.stats()
    if not entries:
        print("No sidecar snapshots present.")
    else:
        print(f"{len(entries)} sidecar snapshot(s):")
        for entry in entries:
            print(
                f"  {entry['file']}: {entry['bytes']} bytes, "
                f"age {entry['age_hours']}h"
            )

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
