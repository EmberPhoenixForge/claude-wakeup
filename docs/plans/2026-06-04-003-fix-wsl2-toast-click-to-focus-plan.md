---
title: "fix: Restore WSL2 toast click-to-focus via XmlDocument-based activation"
type: fix
status: active
date: 2026-06-04
---

## Summary

Replace the WSL2 PowerShell toast backend with an `XmlDocument`-based approach that includes a clickable "Open VS Code" action using the `vscode://` protocol. The previous attempt (commit `9c7fadc`) tried attaching `activationType` directly to the `GetTemplateContent` toast node, which Windows ignores for non-packaged apps; this plan uses `<actions>` elements with `activationType="protocol"` on the action and a registered AppUserModelID, which the user has confirmed works in WSL shell testing.

## Problem Frame

Commit `9c7fadc` added click-to-focus to WSL2 toasts by setting `activationType="protocol"` and `launch="vscode://"` on the toast XML node produced by `GetTemplateContent(2)`. That approach did not work — PowerShell command-line toasts ignore `activationType` attributes on non-packaged apps without COM registration. Commit `683b853` reverted it, restoring simple notification-only toasts.

The user has since tested a different approach that does work: building custom toast XML with `[Windows.Data.Xml.Dom.XmlDocument]`, including an `<actions>` element with `<action activationType="protocol" arguments="vscode://..."/>`, and using PowerShell's registered AppUserModelID for `CreateToastNotifier`. Clicking the notification successfully brings VS Code to the foreground.

## Requirements

- **R1.** WSL2 toast notifications include a clickable action that opens VS Code at the relevant project path via the `vscode://` protocol.
- **R2.** The `vscode://` URI is dynamically constructed from the `WSL_DISTRO_NAME` environment variable and the current working directory.
- **R3.** `CreateToastNotifier` uses PowerShell's registered AppUserModelID so Windows honors the protocol activation.
- **R4.** Notification title and message text are properly escaped for XML embedding (PowerShell single-quote escaping is insufficient for XML).
- **R5.** If `WSL_DISTRO_NAME` is not set, the notification still appears (without the click action) — no crash, no missing notification.
- **R6.** Existing notification behavior is preserved: same title, message, and urgency semantics; same `check=False, timeout=10` subprocess contract; same silent-failure guarantee (R11).
- **R11.** If the OS notification mechanism is unavailable or fails, the system fails silently — no crash, no exception propagation, no interruption to Claude Code.

## Key Technical Decisions

- **XmlDocument over GetTemplateContent.** `GetTemplateContent(2)` returns a `ToastText02` template that does not support `<actions>` elements. Building the XML document from scratch with `[Windows.Data.Xml.Dom.XmlDocument]::new()` and `LoadXml()` gives full control over the toast structure, including the `<actions>` element required for protocol activation.
- **PowerShell AppUserModelID.** Using `{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe` (PowerShell's registered AUMID) instead of `'Claude Code'` (an unregistered string). Windows requires a registered AUMID to honor `activationType="protocol"` on toast actions; the previous custom string was silently ignored.
- **vscode:// URI format.** `vscode://vscode-remote/wsl+{WSL_DISTRO_NAME}{cwd}` follows the standard VS Code Remote URI convention for WSL. Both `WSL_DISTRO_NAME` and `cwd` are available at runtime with no additional configuration.
- **XML escaping replaces single-quote escaping.** The current PowerShell string interpolation escapes single quotes via `.replace("'", "''")`. With custom XML, title and message text must be XML-escaped (`&`, `<`, `>`, `"`, `'`) to avoid breaking the XML document structure. Python's `xml.sax.saxutils.escape` handles this.

## Implementation Units

### U1. Replace `_notify_wsl` with XmlDocument-based toast with click-to-focus

- **Goal:** Rewrite `_notify_wsl` to build custom toast XML with a clickable `vscode://` action, replacing the `GetTemplateContent`-based approach.
- **Requirements:** R1, R2, R3, R4, R5, R6
- **Dependencies:** None
- **Files:**
  - `plugin/notify.py` — modify `_notify_wsl` function (lines 171–195)
  - `plugin/tests/test_notify.py` — update `test_notify_linux_wsl` and add new test cases
- **Approach:**
  1. Read `WSL_DISTRO_NAME` from environment; if unset, fall back to the current simple toast (no click action).
  2. Build the `vscode://` URI: `f"vscode://vscode-remote/wsl+{distro}{os.getcwd()}"`.
  3. XML-escape the title and message text using `xml.sax.saxutils.escape`.
  4. Construct the toast XML with `<actions>` containing `<action content="Open VS Code" arguments="<vscode_uri>" activationType="protocol"/>`.
  5. Use `[Windows.Data.Xml.Dom.XmlDocument]::new()` and `LoadXml()` to parse the XML.
  6. Call `CreateToastNotifier` with PowerShell's AUMID.
  7. Update the docstring to remove the "click-to-focus is not available" note and document the new behavior.
  8. Add `import xml.sax.saxutils` at the top of the file.
- **Patterns to follow:**
  - Existing `_notify_wsl` subprocess invocation pattern: `['powershell.exe', '-Command', ps]`, `check=False, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL`.
  - PowerShell script construction via C-style `%` formatting with `%s` placeholders for dynamic values.
  - No defensive try/except inside the function — `dispatch()` already catches and silences all exceptions (R11).
  - Test mocking pattern: `mock.patch('subprocess.run')`, assert on `call_args[0][0]` for command structure.
- **Test scenarios:**
  - **Happy path:** WSL_DISTRO_NAME is set, title and message are plain text — PowerShell command includes `powershell.exe`, `-Command`, the `XmlDocument` type load, `LoadXml` with a `<toast>` containing `<actions>`, the `vscode://` URI with the distro name and cwd, and the PowerShell AUMID.
  - **XML escaping:** Title contains `&`, `<`, `>`, `'`, `"` characters — the XML passed to `LoadXml` escapes them to `&amp;`, `&lt;`, `&gt;`, `&apos;`, `&quot;`. The unescaped characters do not appear in the XML string.
  - **Missing WSL_DISTRO_NAME:** Environment variable is absent — the PowerShell command falls back to a simple toast without `<actions>` (the current behavior), and the notification still fires.
  - **Subprocess contract preserved:** `check=False`, `timeout=10`, and `DEVNULL` redirection are all present in the `subprocess.run` call.
- **Verification:** `make test` passes all tests. Manual test on WSL2: a notification appears and clicking it brings VS Code to the foreground at the correct project path.

### U2. Bump version to 0.1.5

- **Goal:** Update plugin metadata to reflect the click-to-focus fix.
- **Requirements:** None (bookkeeping)
- **Dependencies:** U1
- **Files:**
  - `plugin/.claude-plugin/plugin.json` — bump `version` from `0.1.4` to `0.1.5`
- **Approach:** Mechanical version bump in the plugin manifest JSON.
- **Patterns to follow:** Existing `plugin.json` structure.
- **Test scenarios:** None — pure metadata change. Test expectation: none — mechanical version bump.
- **Verification:** `grep '"version"' plugin/.claude-plugin/plugin.json` returns `"version": "0.1.5"`.

## Risks & Dependencies

- **AppUserModelID stability.** The PowerShell AUMID `{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe` uses PowerShell's CLSID, which is stable across Windows versions. If Microsoft changes this GUID in a future Windows release, toast activation would silently stop working (the notification would still appear, just without click-to-focus — consistent with R11 graceful degradation).
- **vscode:// protocol registration.** The plan assumes the `vscode://` protocol handler is already registered (VS Code handles this during installation). If VS Code is not installed or the protocol handler is broken, clicking the toast will show a Windows "no app registered" dialog, which is outside the plugin's control.
