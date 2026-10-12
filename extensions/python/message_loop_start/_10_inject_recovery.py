from helpers.extension import Extension

from usr.plugins.thinking_recovery.helpers import recovery


class InjectRecovery(Extension):
    """Re-inject recovered partial thinking when the previous attempt died."""

    async def execute(self, loop_data=None, **kwargs):
        if not self.agent or loop_data is None:
            return
        try:
            await recovery.maybe_inject(self.agent, loop_data)
        except Exception:
            # Recovery must never break the message loop.
            pass
