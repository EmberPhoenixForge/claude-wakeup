---
title: "fix: Add vscode:// protocol activation to WSL2 toast notifications for click-to-focus"
type: fix
status: active
date: 2026-06-04
origin: docs/brainstorms/2026-06-04-claude-wakeup-notifications-requirements.md
---

## Summary

Replace the WSL2 PowerShell toast backend's `GetTemplateContent(2)` approach with a custom XML toast that includes a `vscode://` protocol activation action. When the user clicks the toast, VS Code comes to the foreground. The current implementation sends toasts that are fire-and-forget — clicking them does nothing.

## Problem Frame

The origin document's R6 and F4 require click-to-focus: clicking a notification should bring VS Code to the foreground. On WSL2, the current `_notify_wsl()` implementation uses `ToastNotificationManager::GetTemplateContent(2)` which produces a generic toast template with no click action support. The user discovered and tested a working alternative — building the toast XML manually via `Windows.Data.Xml.Dom.XmlDocument` and adding an `<actions>` block with `activationType="protocol"` pointing at a `vscode://` URI. This plan adapts that approach into the plugin's production code.

## Requirements

These requirements are carried forward from the origin document. See `docs/brainstorms/2026-06-04-claude-wakeup-notifications-requirements.md` for full rationale.

**Notification Behavior**

- R6. Clicking a notification brings VS Code to the foreground with focus on the Claude Code session.
- R10. The system works cross-platform using each platform's native notification mechanism.
- R11. If the OS notification mechanism is unavailable, the system fails silently without blocking or interrupting Claude Code.

## Key Technical Decisions

- **Custom XML toast over `GetTemplateContent(2)` for WSL2.** `GetTemplateContent` returns a fixed template (ToastText02) that cannot carry `<actions>` elements. Building the XML document manually via `Windows.Data.Xml.Dom.XmlDocument` gives full control over the toast payload, enabling the `<action>` with `activationType="protocol"` that fires a `vscode://` URI on click. This is the approach confirmed working by the user's test snippet.

- **`vscode://vscode-remote/wsl+<distro>` as the activation URI.** VS Code's protocol handler uses remote authorities to identify the target window. The WSL2 distro name (from `WSL_DISTRO_NAME` env var, already available in the codebase) is the key discriminator — VS Code focuses the window connected to that WSL instance. No file path is needed; the remote authority alone is sufficient to route the focus.

- **PowerShell AUMID via runtime discovery with fallback.** Toast actions with protocol activation require the sending app to have a registered AppUserModelID. PowerShell's AUMID (used as the `CreateToastNotifier` argument) includes a machine-specific GUID prefix. The implementation will attempt to discover the correct AUMID at toast time by querying the Start Menu shortcut hash, falling back to the current no-action toast if discovery fails. This preserves R11 (silent failure) while maximizing the chance of click-to-focus working.

## Implementation Units

### U1. Replace WSL2 toast snippet with custom XML including vscode:// activation

- **Goal:** Modify `_notify_wsl()` to build the toast XML manually via `Windows.Data.Xml.Dom.XmlDocument`, including a `<actions>` block with a `vscode://` protocol activation that brings VS Code to the foreground on click.
- **Requirements:** R6, R10, R11
- **Dependencies:** None
- **Files:**
  - `notify.py` (modify)
  - `tests/test_notify.py` (modify)
- **Approach:** Replace the current `GetTemplateContent(2)` + `CreateTextNode` PowerShell snippet with a script that:
  1. Loads the `Windows.Data.Xml.Dom.XmlDocument` and `Windows.UI.Notifications` WinRT types.
  2. Constructs the toast XML string with a `ToastGeneric` binding (title + message text) and an `<actions>` block containing one `<action>` with `activationType="protocol"` and `arguments="vscode://vscode-remote/wsl+<distro>"`.
  3. Creates a `ToastNotification` from the XML and shows it via `CreateToastNotifier` using PowerShell's AUMID.
  4. The AUMID is discovered at toast time by constructing the expected shortcut-path hash (or falling back to the current no-action toast if discovery is unavailable).
  - The `vscode://` URI uses `WSL_DISTRO_NAME` from the environment, which is already detectable in the codebase via `os.environ.get('WSL_DISTRO_NAME')`.
  - Title and message are sanitized for safe embedding in the XML string (single-quote escaping, no XML injection).
  - All subprocess calls continue using `check=False, timeout=10` to uphold R11.
  - The existing `_is_wsl()` guard that routes to `_notify_wsl()` is unchanged.
- **Execution note:** Start by verifying the user's working PowerShell snippet sends in the plugin's test environment, then adapt it into `_notify_wsl()` with the dynamic `WSL_DISTRO_NAME`.
- **Patterns to follow:** Existing `_notify_wsl()` structure — single PowerShell invocation via `subprocess.run(['powershell.exe', '-Command', ps])`. Existing sanitization pattern (single-quote escaping of title/message). Graceful-failure pattern (all subprocess calls use `check=False`).
- **Technical design** (directional guidance):

  The PowerShell script shape (not exact code — implementation will refine the AUMID discovery and escaping):

  ```
  # Load WinRT types
  [Windows.UI.Notifications.ToastNotificationManager, ...] | Out-Null
  [Windows.Data.Xml.Dom.XmlDocument, ...] | Out-Null

  # Build toast XML with protocol activation
  $xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
  $xml.LoadXml(@"
  <toast>
    <visual>
      <binding template="ToastGeneric">
        <text>{title}</text>
        <text>{message}</text>
      </binding>
    </visual>
    <actions>
      <action content="Open VS Code"
              arguments="vscode://vscode-remote/wsl+{distro}"
              activationType="protocol"/>
    </actions>
  </toast>
  "@)

  # Show toast using PowerShell's AUMID (discovered or fallback)
  $notifier = [Windows.UI.Notifications.ToastNotificationManager]::
    CreateToastNotifier($aumid)
  $notifier.Show([Windows.UI.Notifications.ToastNotification]::new($xml))
  ```

- **Test scenarios:**
  - Toast XML string contains a valid `<toast>` root with `<visual>` and `<actions>` children
  - Toast XML `<action>` element has `activationType="protocol"` and `arguments` starting with `vscode://vscode-remote/wsl+`
  - The `vscode://` URI includes the value of `WSL_DISTRO_NAME` from the environment
  - Title text appears inside the first `<text>` element of the `ToastGeneric` binding
  - Message text appears inside the second `<text>` element of the `ToastGeneric` binding
  - Title containing a single-quote character is properly escaped in the XML
  - PowerShell subprocess uses `check=False` so failure does not raise an exception
  - PowerShell subprocess timeout is set (10s) so a hung PowerShell does not block Claude Code
  - When `WSL_DISTRO_NAME` is not set, the function still constructs a valid toast XML (the distro name defaults or is omitted gracefully)
  - The overall `_notify_wsl()` function does not change its signature — it still accepts a `payload` dict and returns `None`
- **Verification:** Running `notify.py stop` on WSL2 sends a toast notification. Clicking the toast brings VS Code to the foreground. Running on a system without `WSL_DISTRO_NAME` set (native Linux) does not break — the `_is_wsl()` guard prevents the WSL path from executing.

### U2. Update existing tests for the WSL2 toast backend changes

- **Goal:** Update `tests/test_notify.py` to cover the new toast XML construction and ensure the WSL2 backend is tested for the click-to-focus behavior.
- **Requirements:** R6, R11
- **Dependencies:** U1
- **Files:**
  - `tests/test_notify.py` (modify)
- **Approach:** The current test suite likely mocks `subprocess.run` or checks command construction. Update existing WSL2 backend tests to verify:
  1. The PowerShell command string includes toast XML with `<actions>` and `activationType="protocol"`.
  2. The `vscode://vscode-remote/wsl+` prefix appears in the `arguments` attribute of the action.
  3. The command is invoked via `powershell.exe` (not `powershell`).
  4. Title and message content appear in the XML text elements.
  - If the test suite does not already have WSL2-specific tests, add a new test that patches `_is_wsl()` to return `True` and verifies the PowerShell command construction.
- **Patterns to follow:** Existing test structure in `tests/test_notify.py` — pytest-style tests, mock-based assertions on `subprocess.run` arguments.
- **Test scenarios:**
  - `_is_wsl()` returns `True` → notification routes through `_notify_wsl()` instead of native `_notify_linux()`
  - The `powershell.exe` command string contains `ToastGeneric` binding template reference
  - The `powershell.exe` command string contains `activationType="protocol"`
  - The `powershell.exe` command string contains `vscode://vscode-remote/wsl+`
  - Title text from the payload appears in the XML
  - Message text from the payload appears in the XML
  - `subprocess.run` is called with `check=False`
  - `subprocess.run` is called with a timeout value
- **Verification:** `make test` passes. New and updated tests exercise the WSL2 toast path including XML construction and `vscode://` URI embedding.

## Scope Boundaries

### Deferred to Follow-Up Work

- Native Windows (`_notify_windows`) click-to-focus via `vscode://` protocol activation. The native Windows path also uses `GetTemplateContent(2)` without click actions, but the user's immediate need is WSL2. The same pattern (custom XML + protocol activation) likely applies and can be addressed in a follow-up.
- AUMID caching or persistence across toast calls. The current approach discovers the AUMID on each invocation; caching could reduce subprocess overhead but is premature optimization for v1.

## Risks & Dependencies

- **Machine-specific PowerShell AUMID.** The `CreateToastNotifier` AUMID includes a GUID that varies by machine. If the discovery approach fails to find the correct AUMID, the toast falls back to the current no-action behavior. Mitigation: the fallback is built into the implementation; the notification still fires, just without click-to-focus.
- **vscode:// protocol handler registration.** Click-to-focus depends on VS Code having registered the `vscode://` protocol handler on Windows, which is done during VS Code installation. If the handler is not registered (e.g., portable VS Code), clicking the toast has no effect. This is an environmental prerequisite, not something the plugin controls.
- **WSL2 distro name matching.** The `vscode://vscode-remote/wsl+<distro>` URI relies on the distro name matching what VS Code expects. Renamed WSL2 distros or multiple distros connected to the same VS Code window could cause focus to land on the wrong window. The distro name from `WSL_DISTRO_NAME` should match VS Code's remote authority since both derive from the same WSL environment.

## Sources / Research

- User-provided working PowerShell snippet — confirms the custom XML + `vscode://` protocol activation approach works on their WSL2/Windows environment. The snippet uses `Windows.Data.Xml.Dom.XmlDocument` for XML construction, `ToastGeneric` binding, and `activationType="protocol"` with a `vscode://vscode-remote/wsl+<distro>` URI.
- Existing `_notify_wsl()` implementation in `notify.py` — the baseline being replaced, which confirms the `powershell.exe` subprocess invocation pattern, single-quote escaping, and `_is_wsl()` gating.
- Origin requirements doc — `docs/brainstorms/2026-06-04-claude-wakeup-notifications-requirements.md`. R6, F4, and AE2 define the click-to-focus behavior this plan implements for the WSL2 platform.
