"""Optionally drop unfinished-attempt buffers when a brand-new task starts."""

from helpers.extension import Extension

from usr.plugins.thinking_recovery.helpers import recovery


class ClearOnNewTask(Extension):
    """Honor recover_across_tasks=false by clearing state on new user input."""

    def execute(self, data: dict | None = None, **kwargs):
        if not self.agent:
            return
        try:
            settings = recovery.get_settings(self.agent)
            if not settings.get("enabled", True):
                return
            if not settings.get("recover_across_tasks", True):
                recovery.mark_complete(self.agent)
        except Exception:
            pass
