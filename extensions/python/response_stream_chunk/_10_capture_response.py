from helpers.extension import Extension

from usr.plugins.thinking_recovery.helpers import recovery


class CaptureResponse(Extension):
    """Accumulate the full response stream for the current attempt."""

    async def execute(self, stream_data: dict | None = None, **kwargs):
        if not self.agent or not isinstance(stream_data, dict):
            return
        full = stream_data.get("full")
        if isinstance(full, str) and full:
            # chunk == full marks the first chunk of a new stream.
            is_start = stream_data.get("chunk") == full
            recovery.capture(self.agent, "response", full, is_start=is_start)
