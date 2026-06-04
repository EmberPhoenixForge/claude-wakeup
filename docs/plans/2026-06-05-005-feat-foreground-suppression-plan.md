---
title: "feat: Suppress notifications when VS Code is foreground, with foreground opt-in override"
type: feat
status: active
date: 2026-06-05
---

## Summary

Add foreground detection to suppress desktop notifications when VS Code is already the active window (the user is looking at it). Gated behind a `CLAUDE_WAKEUP_FOREGROUND=1` environment variable for users who want notifications regardless. Detection fails open — if the foreground check can't determine the active window, the notification fires anyway.

## Problem Frame

Notifications currently fire regardless of whether VS Code is in the foreground. When working actively in VS Code, a notification for "Claude finished" is distracting noise — the user can already see Claude's output. Notifications should only pull the user's attention when they've switched away.

The user also wants an override for the opposite preference: always fire notifications even when VS Code is in front.

## Requirements

- **R1.** When VS Code is the foreground window, notifications are suppressed (not dispatched to the OS notification system).
- **R2.** When `CLAUDE_WAKEUP_FOREGROUND=1` is set, notifications fire regardless of foreground state.
- **R3.** If foreground detection fails (command missing, timeout, unexpected output), the notification fires anyway — fail open, never suppress.
- **R4.** The foreground check adds negligible overhead (< 1 second total within the existing hook timeout budget).
- **R5.** Foreground detection works on all three platforms: Windows/WSL2, macOS, Linux.

## Key Technical Decisions

- **Gate in `main()`, not in `dispatch()`.** `main()` has access to the `event` variable needed for logging suppression. The foreground check runs after dedup and payload construction but before `dispatch()` — if suppressed, `_log(event, 'suppressed', 'foreground')` is emitted and `dispatch()` is never called.
- **Fail open.** Any exception or unexpected output from the foreground check is treated as "not VS Code foreground" — the notification fires. This matches the fail-open design already specified in R3 and the silent-failure pattern used throughout the codebase.
- **Per-platform detection commands.** Each platform uses its native window query mechanism:

| Platform | Command | Detection logic |
|----------|---------|----------------|
| Windows (incl. WSL2) | `powershell.exe -Command "(Get-Process -Id (Get-ForumWindowProcessId (Get-ForumWindow))).ProcessName"` | output contains `Code` (VS Code process name) |
| macOS | `osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true'` | output equals `Code` or `Visual Studio Code` |
| Linux | `xdotool getactivewindow getwindowname` (X11 only) | output contains `Visual Studio Code` or `Code`; on Wayland or if `xdotool` missing, always fires (fail-open) |
- **`CLAUDE_WAKEUP_FOREGROUND=1` opt-in.** Follows the existing pattern of `CLAUDE_WAKEUP_LOG_DIR` — a single env var with a simple boolean interpretation. Only the exact value `1` enables foreground notifications; any other value (or unset) keeps the default suppress-foreground behavior.

## Implementation Units

### U1. Add `_is_vscode_foreground()` detection function

- **Goal:** Add a platform-specific foreground detection function that returns `True` when VS Code is the active window.
- **Requirements:** R3, R4, R5
- **Dependencies:** None
- **Files:**
  - `plugin/notify.py` — add `_is_vscode_foreground()` function
  - `plugin/tests/test_notify.py` — add tests for detection function
- **Approach:**
  1. Add `_is_vscode_foreground()` after the existing `_is_wsl()` helper, following the same pattern (return bool, no parameters).
  2. Dispatch by platform using `sys.platform`:
     - `win32` / `cygwin`: PowerShell query via `subprocess.run` — get foreground window process name and check for `Code`.
     - `darwin`: `osascript` query via `subprocess.run` — get frontmost app name.
     - `linux`: `xdotool` query via `subprocess.run` — get active window title. If `xdotool` is not found, treat as "not VS Code" (fail open).
  3. On WSL2 (`WSL_DISTRO_NAME` is set), use the Windows PowerShell path (same as Windows) — the foreground window is a Windows window, not a Linux one.
  4. All subprocess calls use `check=False`, `timeout=1`, `DEVNULL` redirection, wrapped in try/except — any failure returns `False` (fail open).
  5. Match VS Code by checking whether the output contains `Code` (the process name is `Code.exe` on Windows, `Code` on macOS).
- **Patterns to follow:** `_is_wsl()` helper function — same shape (no params, returns bool, reads env/platform). Subprocess pattern from existing backends (`check=False`, timeout, `DEVNULL`). Fail-open pattern from `dispatch()` and `_log()`.
- **Test scenarios:**
  - **Happy path — VS Code foreground:** Mock `subprocess.run` to return `stdout=b'Code'` (macOS) or `stdout=b'Code.exe'` (Windows) — function returns `True`.
  - **Happy path — not VS Code:** Mock `subprocess.run` to return `stdout=b'Terminal'` — function returns `False`.
  - **Command not found:** Mock `subprocess.run` with `side_effect=FileNotFoundError` — function returns `False` (fail open).
  - **Timeout:** Mock `subprocess.run` with `side_effect=subprocess.TimeoutExpired(cmd='...', timeout=1)` — function returns `False`.
  - **Unexpected output:** Mock `subprocess.run` to return `stdout=b''` or garbled output — function returns `False`.
  - **WSL2 path:** With `WSL_DISTRO_NAME` set and `sys.platform='linux'`, uses `powershell.exe` command.
- **Verification:** `make test` passes all new detection tests.

### U2. Gate notification dispatch on foreground state in `main()`

- **Goal:** Skip notification dispatch when VS Code is foreground and `CLAUDE_WAKEUP_FOREGROUND` is not `1`.
- **Requirements:** R1, R2
- **Dependencies:** U1
- **Files:**
  - `plugin/notify.py` — modify `main()` function
  - `plugin/tests/test_notify.py` — add foreground-gating tests
- **Approach:**
  1. In `main()`, after payload construction and dedup logic, but before `dispatch()`: if `os.environ.get('CLAUDE_WAKEUP_FOREGROUND') != '1'` and `_is_vscode_foreground()`, log suppression via `_log(event, 'suppressed', 'foreground')` and return early (skip dispatch).
  2. `main()` already has access to the `event` variable — no signature changes needed. `dispatch()` is unchanged.
  3. Dedup is checked before the foreground check — if dedup already suppressed, don't waste time on foreground detection.
- **Patterns to follow:** The existing `main()` structure — the foreground check is another gate between payload construction and dispatch, similar to the dedup gate.
- **Test scenarios:**
  - **Foreground, no env var:** VS Code is foreground, `CLAUDE_WAKEUP_FOREGROUND` unset — `dispatch()` is NOT called.
  - **Foreground, env var set to 1:** `CLAUDE_WAKEUP_FOREGROUND=1` — `dispatch()` IS called.
  - **Background, no env var:** VS Code is NOT foreground — `dispatch()` is called normally.
  - **Foreground, env var set to 0:** `CLAUDE_WAKEUP_FOREGROUND=0` — still suppresses (only exact `1` enables foreground).
  - **Detection failure:** `_is_vscode_foreground()` returns `False` due to command failure — notification still fires (fail open already tested in U1).
- **Verification:** `make test` passes. Manual test: send notification while VS Code foreground → suppressed. Set `CLAUDE_WAKEUP_FOREGROUND=1` → fires.

### U3. Update documentation

- **Goal:** Document the foreground suppression behavior and the `CLAUDE_WAKEUP_FOREGROUND` override in README.
- **Requirements:** R1, R2
- **Dependencies:** None (can run in parallel with U1-U2)
- **Files:**
  - `README.md` — add section about foreground behavior
- **Approach:**
  1. Add a note in the "How it works" section or a new "Foreground behavior" subsection explaining that notifications are suppressed when VS Code is the active window, and that `CLAUDE_WAKEUP_FOREGROUND=1` overrides this.
- **Patterns to follow:** Existing README prose style and the `CLAUDE_WAKEUP_LOG_DIR` env var documentation pattern.
- **Test scenarios:** None — documentation only. Test expectation: none — pure documentation change.
- **Verification:** Visual review of rendered README.

## Risks & Dependencies

- **`xdotool` on Linux — X11 only.** `xdotool` is X11-specific and returns nothing or errors on Wayland compositors. The fail-open design handles this — on Wayland or if `xdotool` is missing, notifications always fire (current behavior). Foreground suppression on Linux is effectively X11-only for now.
- **PowerShell startup latency on WSL2.** `powershell.exe` has a cold-start overhead of ~200-500ms. With `timeout=1`, the check fits within budget but may add a brief delay to notification delivery. This is acceptable since a human needs ~500ms to context-switch anyway.
