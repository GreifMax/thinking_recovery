"""Core logic for the Thinking Recovery plugin.

Captures partial reasoning/response streams per (context, agent), persists
throttled snapshots to disk so crashes/restarts can still recover, and
re-injects a compact digest into the next attempt via one-shot extras.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from helpers import files, tokens
from helpers.print_style import PrintStyle

PLUGIN_NAME = "thinking_recovery"
_STATE_DIR_REL = os.path.join("tmp", "thinking_recovery")

_MEMORY_STATES: dict[str, dict[str, Any]] = {}
_DISK_WRITE_MIN_INTERVAL = 2.0
_DISK_WRITE_MIN_DELTA = 2000

_PRUNE_INTERVAL_SECONDS = 3600.0
_LAST_PRUNE: dict[str, float] = {"at": 0.0}


def _maybe_prune(settings: dict[str, Any]) -> None:
    """Opportunistically prune expired sidecars, at most once per hour."""
    now = time.time()
    if now - float(_LAST_PRUNE["at"]) < _PRUNE_INTERVAL_SECONDS:
        return
    _LAST_PRUNE["at"] = now
    try:
        prune_old_states(float(settings.get("state_ttl_days", 7)))
    except Exception:
        pass

_FIELDS = (
    "reasoning",
    "response",
    "started_at",
    "updated_at",
    "complete",
    "fragments",
)


def _state_dir() -> str:
    try:
        return files.get_abs_path(_STATE_DIR_REL)
    except Exception:
        return os.path.join("/a0", _STATE_DIR_REL)


def _key(agent: Any) -> str:
    ctx = getattr(agent, "context", None)
    ctx_id = str(getattr(ctx, "id", "unknown") or "unknown")
    number = int(getattr(agent, "number", 0) or 0)
    return f"{ctx_id}:{number}"


def _disk_path(key: str) -> str:
    safe = key.replace(":", "_").replace("/", "_")
    return os.path.join(_state_dir(), f"{safe}.json")


_SETTINGS_CACHE: dict[str, Any] = {"data": None, "at": 0.0}
_SETTINGS_TTL_SECONDS = 5.0


def get_settings(agent: Any = None) -> dict[str, Any]:
    """Resolve plugin settings with a short TTL cache.

    Capture hooks fire on every stream chunk; caching avoids re-reading
    config files dozens of times per second.
    """
    now = time.time()
    cached = _SETTINGS_CACHE["data"]
    if cached is not None and now - float(_SETTINGS_CACHE["at"]) < _SETTINGS_TTL_SECONDS:
        return cached

    from helpers.plugins import get_plugin_config

    settings: dict[str, Any] = {}
    if agent is not None:
        try:
            settings = get_plugin_config(PLUGIN_NAME, agent=agent) or {}
        except Exception:
            settings = {}
    if not settings:
        try:
            settings = get_plugin_config(PLUGIN_NAME) or {}
        except Exception:
            settings = {}

    _SETTINGS_CACHE["data"] = settings
    _SETTINGS_CACHE["at"] = now
    return settings


def _fresh_state() -> dict[str, Any]:
    now = time.time()
    return {
        "reasoning": "",
        "response": "",
        "started_at": now,
        "updated_at": now,
        "complete": False,
        "fragments": [],
        "digest": "",
        "digest_len": -1,
        "last_disk_write": 0.0,
        "last_disk_len": -1,
    }


def _public(state: dict[str, Any]) -> dict[str, Any]:
    return {field: state.get(field) for field in _FIELDS}


def _load_disk(key: str) -> dict[str, Any] | None:
    try:
        path = _disk_path(key)
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_disk(key: str, state: dict[str, Any]) -> None:
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        path = _disk_path(key)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(_public(state), handle)
        os.replace(tmp_path, path)
    except Exception:
        pass


def _delete_disk(key: str) -> None:
    try:
        os.remove(_disk_path(key))
    except OSError:
        pass


def prune_old_states(ttl_days: float) -> int:
    """Delete sidecar files older than ttl_days. Returns removed count."""
    cutoff = time.time() - max(float(ttl_days), 0) * 86400
    removed = 0
    try:
        names = os.listdir(_state_dir())
    except OSError:
        return 0
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(_state_dir(), name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed


def capture(
    agent: Any, kind: str, full_text: str, is_start: bool = False
) -> None:
    """Store the latest accumulated stream text for this agent's attempt."""
    settings = get_settings(agent)
    if not settings.get("enabled", True):
        return
    if not isinstance(full_text, str) or not full_text:
        return

    key = _key(agent)
    state = _MEMORY_STATES.get(key)
    if state is None or state.get("complete"):
        state = _fresh_state()
        _MEMORY_STATES[key] = state

    # A new stream began while an unfinished buffer exists: archive the
    # previous fragment so chained failures keep earlier reasoning.
    if is_start and (state.get("reasoning") or state.get("response")):
        fragments = state.setdefault("fragments", [])
        fragments.append(_combined(state))
        del fragments[:-3]  # keep the last three fragments
        state["reasoning"] = ""
        state["response"] = ""

    slot = "reasoning" if kind == "reasoning" else "response"
    if len(full_text) >= len(state.get(slot, "")):
        state[slot] = full_text
    state["updated_at"] = time.time()

    if settings.get("sidecar_enabled", True):
        total = len(state["reasoning"]) + len(state["response"])
        due = (
            time.time() - float(state["last_disk_write"] or 0)
            >= _DISK_WRITE_MIN_INTERVAL
            or total - int(state["last_disk_len"] or 0) >= _DISK_WRITE_MIN_DELTA
        )
        if due:
            _save_disk(key, state)
            state["last_disk_write"] = time.time()
            state["last_disk_len"] = total


def mark_complete(agent: Any) -> None:
    """A full assistant message was added to history; recovery no longer needed."""
    key = _key(agent)
    state = _MEMORY_STATES.pop(key, None)
    if state is not None:
        state["complete"] = True
    _delete_disk(key)


def _combined(state: dict[str, Any]) -> str:
    parts = [str(item) for item in state.get("fragments", []) if item]
    if state.get("reasoning"):
        parts.append(str(state["reasoning"]))
    if state.get("response"):
        parts.append(str(state["response"]))
    return "\n\n---\n\n".join(parts)


def build_excerpt(text: str, max_tokens: int) -> str:
    """Deterministic head+tail excerpt capped near max_tokens."""
    budget = max(int(max_tokens), 50) * 4  # ~4 chars per token
    text = (text or "").strip()
    if len(text) <= budget:
        return text
    head_budget = int(budget * 0.6)
    tail_budget = max(budget - head_budget, 1)
    head = text[:head_budget].strip()
    tail = text[-tail_budget:].strip()
    return f"{head}\n[...]\n{tail}"


def clip_tokens(text: str, max_tokens: int) -> str:
    if not text:
        return text
    while text and tokens.approximate_tokens(text) > max_tokens:
        text = text[: int(len(text) * 0.9)]
    return text


_UTILITY_SYSTEM = (
    "You distill an AI agent's interrupted private reasoning into a dense "
    "handoff brief so the agent can resume without redoing the work. "
    "Preserve: inferred current goal, key facts and decisions made so far, "
    "candidate next actions, and anything half-finished. Output only the "
    "brief, under 150 words, no commentary."
)


async def _utility_digest(agent: Any, raw: str, settings: dict[str, Any]) -> str:
    limit = int(settings.get("utility_max_input_chars", 12000))
    timeout = float(settings.get("utility_timeout_seconds", 20))
    payload = raw if len(raw) <= limit else build_excerpt(raw, max(limit // 4, 200))
    message = (
        "The following is a partial reasoning/output stream that was "
        "interrupted before completion. Summarize it for continuation.\n\n"
        f"{payload}"
    )
    coro = agent.call_utility_model(system=_UTILITY_SYSTEM, message=message)
    result = await asyncio.wait_for(coro, timeout=timeout)
    return str(result or "").strip()


async def _build_digest(
    agent: Any, raw: str, settings: dict[str, Any]
) -> str:
    max_tokens = int(settings.get("max_inject_tokens", 400))
    if settings.get("mode", "excerpt") == "utility":
        try:
            digest = await _utility_digest(agent, raw, settings)
            if digest:
                return clip_tokens(digest, max_tokens)
        except Exception:
            pass  # fall back to deterministic excerpt
    return build_excerpt(raw, max_tokens)


async def maybe_inject(agent: Any, loop_data: Any) -> bool:
    """Inject a recovery digest into extras when the previous attempt died.

    Returns True when a digest was injected.
    """
    settings = get_settings(agent)
    if not settings.get("enabled", True):
        return False

    _maybe_prune(settings)

    key = _key(agent)
    state = _MEMORY_STATES.get(key)
    if state is None and settings.get("sidecar_enabled", True):
        disk = _load_disk(key)
        if disk and not disk.get("complete"):
            state = _fresh_state()
            state["reasoning"] = str(disk.get("reasoning", "") or "")
            state["response"] = str(disk.get("response", "") or "")
            state["started_at"] = float(disk.get("started_at") or time.time())
            state["updated_at"] = float(disk.get("updated_at") or time.time())
            state["fragments"] = [
                str(item) for item in (disk.get("fragments") or []) if item
            ]
            _MEMORY_STATES[key] = state

    if state is None or state.get("complete"):
        return False

    # Discard buffers that went stale (agent moved on long ago).
    staleness_seconds = float(settings.get("max_staleness_minutes", 30)) * 60
    if (
        staleness_seconds > 0
        and time.time() - float(state.get("updated_at") or 0) > staleness_seconds
    ):
        _MEMORY_STATES.pop(key, None)
        _delete_disk(key)
        return False

    raw = _combined(state)
    if len(raw) < int(settings.get("min_recover_chars", 200)):
        return False

    digest = str(state.get("digest", "") or "")
    if not digest or int(state.get("digest_len", -1)) != len(raw):
        digest = await _build_digest(agent, raw, settings)
        state["digest"] = digest
        state["digest_len"] = len(raw)
    if not digest:
        return False

    loop_data.extras_temporary["thinking_recovery"] = (
        "Your previous attempt at this task was interrupted (error, timeout, "
        "or restart) mid-generation. Below is your own recovered partial "
        "thinking/output. Continue from it instead of starting over; do not "
        "repeat work it already covers:\n\n"
        f"{digest}"
    )
    try:
        PrintStyle(font_color="cyan", padding=True).print(
            f"Thinking Recovery: re-injected ~{len(digest)} chars of partial "
            "reasoning from the interrupted attempt."
        )
    except Exception:
        pass
    return True


def stats() -> list[dict[str, Any]]:
    """Sidecar inventory for maintenance/reporting."""
    result = []
    try:
        names = sorted(os.listdir(_state_dir()))
    except OSError:
        return result
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(_state_dir(), name)
        try:
            stat = os.stat(path)
            result.append(
                {
                    "file": name,
                    "bytes": stat.st_size,
                    "age_hours": round((time.time() - stat.st_mtime) / 3600, 2),
                }
            )
        except OSError:
            continue
    return result
