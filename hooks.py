"""Lifecycle hooks for the Thinking Recovery plugin.

Install/update: prepare the state directory and prune expired sidecars.
Uninstall: remove plugin-owned runtime state only (tmp/thinking_recovery).
All operations are safe to rerun and never touch shared framework data.
"""

import shutil

from usr.plugins.thinking_recovery.helpers import recovery


def install():
    """Prepare state dir and prune expired snapshots. Safe to rerun."""
    try:
        recovery.prune_old_states(
            float(recovery.get_settings().get("state_ttl_days", 7))
        )
    except Exception:
        pass  # install must never fail the plugin setup


def pre_update():
    """Same housekeeping as install before files are replaced."""
    install()


def uninstall():
    """Remove plugin-owned sidecar state; leave everything else intact."""
    try:
        shutil.rmtree(recovery._state_dir(), ignore_errors=True)
    except Exception:
        pass
