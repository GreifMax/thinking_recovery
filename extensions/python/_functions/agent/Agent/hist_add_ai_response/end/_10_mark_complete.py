"""Mark the capture buffer complete once a full AI response enters history."""

from helpers.extension import Extension

from usr.plugins.thinking_recovery.helpers import recovery


class MarkComplete(Extension):
    """Clear recovery state after a successful assistant message."""

    def execute(self, data: dict | None = None, **kwargs):
        if not self.agent:
            return
        try:
            recovery.mark_complete(self.agent)
        except Exception:
            pass
