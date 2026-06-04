---
title: "feat: Add Notification hook with matchers and debug logging"
type: feat
status: active
date: 2026-06-04
origin: docs/brainstorms/2026-06-04-claude-wakeup-notifications-requirements.md
---

## Summary

Add the idiomatic `Notification` hook with `permission_prompt` and `idle_prompt` matchers as the primary event channel, keeping existing `PermissionRequest`/`Stop`/`PostToolUseFailure` entries as a VS Code fallback (due to [known bug #11156](https://github.com/anthropics/claude-code/issues/11156)). Add timestamped debug logging to `~/.claude/claude-wakeup/debug.log` for every event received and notification dispatched.

## Problem Frame

Claude Code's official hook docs recommend the `Notification` event with matcher subtypes as the canonical way to detect attention-needing states. Our current hooks use separate `PermissionRequest`/`Stop`/`PostToolUseFailure` events, which work reliably everywhere but aren't the idiomatic path. Adding `Notification` as primary with existing events as fallback gives users the best of both. Additionally, troubleshooting silent notification failures is currently guesswork — debug logging makes every event traceable.

## Requirements

- R1. `Notification` hook with `permission_prompt` matcher triggers permission notifications.
- R2. `Notification` hook with `idle_prompt` matcher triggers completion notifications.
- R3. Existing `PermissionRequest`/`Stop`/`PostToolUseFailure` hooks remain as fallback for VS Code users.
- R4. Every hook event received by notify.py is logged with timestamp, event type, and context to `~/.claude/claude-wakeup/debug.log`.
- R5. Every notification dispatch (or suppression) is logged with timestamp and outcome.
- R6. The log directory is created automatically on first write.
- R7. notify.sh passes the notification subtype through to notify.py so the engine can distinguish `Notification` from direct events.

## Key Technical Decisions

- **`Notification` with matchers as primary, existing events as fallback.** The `Notification` event is the idiomatic Claude Code approach (used by both `claude-code-notify` and `CCNotify`), but has a [known VS Code bug](https://github.com/anthropics/claude-code/issues/11156). Keeping both means the plugin works in all environments without user configuration changes.
- **JSON-lines debug log format.** One JSON object per line — machine-parseable, append-friendly, human-readable with `jq`. Each line carries `ts` (ISO timestamp), `event` (hook event name), `action` (dispatched/suppressed/cleared), and `context` (available event data).

## Implementation Units

### U1. Update hooks.json with Notification matchers

- **Goal:** Add `Notification` event with `permission_prompt` and `idle_prompt` matchers as the primary channel, keeping existing events.
- **Requirements:** R1, R2, R3
- **Dependencies:** None
- **Files:**
  - `hooks/hooks.json` (modify)
- **Approach:** Add a new top-level `Notification` key with two matcher entries. Each matcher maps to the same `notify.sh` entry point with the appropriate event argument. The existing `PermissionRequest`, `Stop`, `PostToolUseFailure`, `UserPromptSubmit`, and `SessionEnd` entries remain unchanged. The `notify.sh` script already handles the event names — no script changes needed for the hook config itself.
- **Patterns to follow:** Existing hooks.json structure (type, command, timeout fields per hook entry).
- **Test scenarios:**
  - `Notification.permission_prompt` matcher has a hook entry with type=command, timeout=10, and command referencing `${CLAUDE_PLUGIN_ROOT}`
  - `Notification.idle_prompt` matcher has a hook entry with type=command, timeout=10, and command referencing `${CLAUDE_PLUGIN_ROOT}`
  - Existing `PermissionRequest`, `Stop`, `PostToolUseFailure`, `UserPromptSubmit`, `SessionEnd` entries remain present and unchanged
  - All hook entries pass `test_hooks_config.py` validations
- **Verification:** `python3 tests/test_hooks_config.py` passes. All 7 event entries (5 existing + 2 new matchers under Notification) are valid.

### U2. Add debug logging to notify.py

- **Goal:** Write timestamped JSON-lines debug log for every event received, notification dispatched, and notification suppressed.
- **Requirements:** R4, R5, R6
- **Dependencies:** U1
- **Files:**
  - `notify.py` (modify)
  - `tests/test_notify.py` (modify)
- **Approach:** Add a `_log(event, action, context=None)` helper that appends a JSON line to `~/.claude/claude-wakeup/debug.log`. The function creates the directory on first write (`os.makedirs` with `exist_ok=True`). Call `_log` at each decision point: on event entry (with context from stdin), on notification dispatch (with payload summary), on dedup suppression, on state clear, and on state cleanup. The log path is configurable via `CLAUDE_WAKEUP_LOG_DIR` environment variable, defaulting to `~/.claude/claude-wakeup/`. Log format: `{"ts": "2026-06-04T12:34:56.789", "event": "permission", "action": "dispatched", "project": "my-project", "detail": "tool=Bash"}`.
- **Patterns to follow:** Existing notify.py structure — single-file Python, stdlib only, no external dependencies.
- **Test scenarios:**
  - Log directory created on first write when it doesn't exist
  - Event received is logged with timestamp, event type, and context
  - Notification dispatched is logged with payload summary
  - Notification suppressed (dedup) is logged with suppression reason
  - State cleared (cycle-reset) is logged
  - State cleaned up (cleanup) is logged
  - Log entries are valid JSON with required fields (ts, event, action)
  - `CLAUDE_WAKEUP_LOG_DIR` env var overrides default log path
  - Missing log directory is created automatically
- **Verification:** `make test` passes. Manual: run `notify.py --event=permission` and verify `~/.claude/claude-wakeup/debug.log` contains a timestamped entry.

### U3. Pass notification subtype through notify.sh

- **Goal:** Update notify.sh to pass the notification subtype from the `Notification` hook so notify.py can log it distinctly from direct events.
- **Requirements:** R7
- **Dependencies:** U1, U2
- **Files:**
  - `hooks/notify.sh` (modify)
- **Approach:** The `Notification` hook with matchers fires notify.sh with the same argv[1] values (`permission`, `stop`). The subtype is available in the hook's stdin JSON (the `notification_type` field per Claude Code docs). notify.sh doesn't need to change its argument handling — the event names already match. The notify.py engine reads stdin JSON which carries the notification subtype automatically. The only shell change needed: if the event originates from `Notification` hook (detectable via environment or stdin), pass it through. Since hooks.json already passes `permission` and `stop` as argv[1], and notify.py reads stdin for context, the mapping is already correct — no shell changes actually needed beyond verification.
- **Patterns to follow:** Existing notify.sh structure — POSIX sh, minimal logic.
- **Test scenarios:**
  - `Notification` with `permission_prompt` matcher invokes notify.sh with `permission` argument
  - `Notification` with `idle_prompt` matcher invokes notify.sh with `stop` argument
  - Stdin JSON context is passed through to notify.py unchanged
  - `PermissionRequest` direct event still invokes notify.sh with `permission` argument (unchanged)
- **Verification:** The hooks.json command strings already pass the correct event names. Manual verification: `sh hooks/notify.sh permission` invokes `python3 notify.py permission`.

## Scope Boundaries

- Other `Notification` matchers (`auth_success`, `elicitation_dialog`, `elicitation_complete`) are not wired — no user need yet.
- The VS Code Notification hook bug (#11156) is not fixed here — the fallback handles it.
- Log rotation is not implemented — the debug log grows unbounded. Manual cleanup or a future log-rotation task.
