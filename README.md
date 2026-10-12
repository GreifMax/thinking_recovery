# Thinking Recovery

Agent Zero plugin that recovers **partial reasoning** from interrupted LLM attempts.

When an agent crashes, hangs, times out, is stopped mid-generation, or the process
restarts while the model was still thinking, Agent Zero normally discards that
partial work — the next attempt starts reasoning from zero, burning output tokens
and time. This plugin captures the reasoning/response streams live and re-injects
a compact digest into the next attempt so the agent **continues where it left off**.

## Features

- Live capture of accumulated reasoning and response streams per agent attempt.
- Automatic detection of dead attempts at the next message-loop iteration.
- Compact recovery block injected once via one-shot extras (append-only,
  prompt-cache friendly — no history rewriting).
- Two recovery modes:
  - `excerpt` — deterministic head+tail excerpt, zero extra cost.
  - `utility` — Utility Model distills the partial stream into a dense handoff
    brief (with timeout fallback to excerpt).
- Disk sidecars under `tmp/thinking_recovery/` so recovery survives full restarts.
- Staleness window, minimum-size gate, and cross-task recovery toggle.
- Lifecycle hygiene: expired sidecars are pruned automatically (at most once
  per hour when a recovery check runs), on install/update, and on uninstall
  the plugin removes its own `tmp/thinking_recovery/` state directory.
- Maintenance script to prune old sidecars and report stats.

## Install

Copy this folder into your Agent Zero installation:

```bash
cp -r thinking_recovery /a0/usr/plugins/
```

Restart Agent Zero. The plugin appears under Settings → Agent → Thinking Recovery.

## Usage

No manual steps required. The plugin activates automatically:

1. While the model streams, partial text is captured (memory + throttled disk writes).
2. If the attempt completes normally, the buffer is cleared.
3. If the attempt dies, the next loop iteration injects:
   `Your previous attempt ... was interrupted ... Below is your own recovered partial thinking/output.`
4. The agent continues from its own prior reasoning instead of redoing it.

### Settings

| Setting | Default | Meaning |
|---|---|---|
| `enabled` | `true` | Master switch |
| `mode` | `excerpt` | `excerpt` or `utility` |
| `max_inject_tokens` | `400` | Cap for the injected block |
| `min_recover_chars` | `200` | Skip fragments smaller than this |
| `max_staleness_minutes` | `30` | Discard buffers older than this (0 = never) |
| `recover_across_tasks` | `true` | Keep buffers across new user messages |
| `sidecar_enabled` | `true` | Persist snapshots to disk |
| `utility_timeout_seconds` | `20` | Digest call timeout |
| `utility_max_input_chars` | `12000` | Pre-excerpt cap before digest |
| `state_ttl_days` | `7` | Sidecar retention |

## Troubleshooting

- **No recovery happening?** Check that the failure actually happened *during*
  generation (streaming had started). Failures before any tokens arrive have
  nothing to recover.
- **Recovery too aggressive?** Raise `min_recover_chars` or lower
  `max_staleness_minutes`.
- **Sidecar clutter?** Sidecars older than `state_ttl_days` are pruned
  automatically; you can also run the plugin's Execute action (`execute.py`)
  to prune on demand, or set `sidecar_enabled: false`.
- **Utility mode slow?** Lower `utility_timeout_seconds`; it falls back to the
  deterministic excerpt on timeout.

## Screenshots

<!-- TODO: add screenshot of settings panel -->
<!-- TODO: add screenshot of console line "Thinking Recovery: re-injected ..." -->

## License

MIT — see [LICENSE](LICENSE).
