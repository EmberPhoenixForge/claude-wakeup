---
title: 'feat: Use VS Code AUMID for toast notification header with PowerShell fallback'
type: feat
status: completed
date: 2026-06-05
---

## Summary

Use VS Code's registered AUMID (`Microsoft.VisualStudioCode`) for Windows toast notifications when available, falling back to the current PowerShell AUMID when VS Code is not installed. When VS Code is present, the toast header changes from "Windows PowerShell" to "Visual Studio Code" — accurately identifying the tool the user needs to switch back to.

## Problem Frame

Windows toast notifications dispatched from `notify.py` use PowerShell's Application User Model ID (AUMID) `{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe`. This causes every notification to display "Windows PowerShell" as the header, regardless of content. Users may dismiss these as system noise rather than recognizing them as Claude Code alerts.

VS Code registers the AUMID `Microsoft.VisualStudioCode` on every standard Windows installation. Since every Claude Wakeup notification is designed to bring the user back to VS Code, using its identity is both accurate and requires zero setup. However, VS Code is not guaranteed to be installed (portable ZIP, minimal environments), so the PowerShell AUMID must remain as a fallback to ensure notifications always fire.

---

## Requirements

- R1. Toast notifications on WSL2 display "Visual Studio Code" as the app header when VS Code is installed.
- R2. Toast notifications on native Windows display "Visual Studio Code" as the app header when VS Code is installed.
- R3. Notification content (title, message, click-to-focus action) is unchanged.
- R4. When VS Code is not installed, notifications fall back to the current PowerShell AUMID — no notification is ever silently dropped due to a missing VS Code registration.

---

## Key Technical Decisions

- **Use VS Code's AUMID (`Microsoft.VisualStudioCode`) with PowerShell fallback:** Query `Get-StartApps` once at module load to detect whether VS Code's AUMID is registered. Cache the result as a module-level string. When VS Code is present, use its AUMID; otherwise fall back to the PowerShell GUID AUMID. This preserves the zero-setup property for the common case while guaranteeing notifications always fire. The alternative — always using VS Code's AUMID without fallback — would silently break on portable or minimal VS Code installations.

- **Detect via `Get-StartApps` rather than checking for the `.lnk` file or `vscode://` protocol:** `Get-StartApps` directly returns the AppID string we need to match, and its output is structured (PowerShell objects). Checking for `vscode://` protocol registration is indirect and checking `.lnk` files requires filesystem probing. The detection call is idempotent and runs once per session.

---

## Implementation Units

### U1. Add AUMID detection and selection helper

- **Goal:** Provide a module-level helper that returns the best available AUMID, caching the result so the detection query runs at most once per session.
- **Requirements:** R4
- **Dependencies:** None
- **Files:** `plugin/notify.py`
- **Approach:** Add a `_resolve_aumid()` function that runs `powershell.exe -Command "Get-StartApps | Where-Object { $_.AppID -eq 'Microsoft.VisualStudioCode' }"` and checks for non-empty stdout. Cache the result in a module-level `_AUMID` variable. On any failure (timeout, non-zero exit, empty output), fall back to the PowerShell GUID AUMID. The function is called once at the top of `_notify_wsl` / `_notify_windows` dispatch, not at import time, so test mocking and import ordering are unaffected.
- **Patterns to follow:** The existing subprocess call pattern in `_notify_wsl` — `subprocess.run` with `check=False`, `timeout`, and `capture_output=True`. The `_foreground_linux` function's `shutil.which` guard pattern for optional dependencies.
- **Test scenarios:**
  - Happy path: `_resolve_aumid()` returns `'Microsoft.VisualStudioCode'` when `Get-StartApps` output contains it.
  - Fallback path: `_resolve_aumid()` returns the PowerShell GUID AUMID when `Get-StartApps` returns empty output.
  - Error path: `_resolve_aumid()` returns the PowerShell GUID AUMID when the subprocess call times out or fails.
- **Verification:** Unit test exercises both branches by mocking `subprocess.run` return values.

### U2. Wire resolved AUMID into WSL2 and Windows backends

- **Goal:** Replace the hardcoded PowerShell AUMID in `_notify_wsl` and `_notify_windows` with the resolved AUMID from U1.
- **Requirements:** R1, R2, R3
- **Dependencies:** U1
- **Files:** `plugin/notify.py`, `plugin/tests/test_notify.py`
- **Approach:** In both `_notify_wsl` and `_notify_windows`, replace the hardcoded PowerShell GUID-based AUMID assignment with a call to `_resolve_aumid()`. Update the two test assertions that check the AUMID in the generated PowerShell script: assert for `'Microsoft.VisualStudioCode'` when the mock returns VS Code's AUMID, and add a second test case asserting the PowerShell GUID when the mock returns the fallback.
- **Patterns to follow:** Same dispatch pattern — `CreateToastNotifier(appId)` call is unchanged, only the value of `appId` changes.
- **Test scenarios:**
  - Happy path: Test with mocked `_resolve_aumid` returning `'Microsoft.VisualStudioCode'` — generated PowerShell script contains `Microsoft.VisualStudioCode`.
  - Fallback path: Test with mocked `_resolve_aumid` returning the PowerShell GUID — generated PowerShell script contains the GUID.
  - Integration: Sending a test notification on WSL2 produces a toast with the correct header for the installed VS Code state.
- **Verification:** Run the existing test suite — all tests pass. Run `/claude-wakeup:test` — toast header reflects the installed VS Code state.

---

## Scope Boundaries

- **In scope:** Adding `_resolve_aumid()` helper, wiring it into `_notify_wsl` and `_notify_windows`, updating tests.
- **Out of scope:** Creating a custom shortcut or AUMID registration, changing notification content, modifying Linux or macOS backends, adding configuration options for the AUMID, supporting VS Code Insiders AUMID.
