---
title: "feat: Homogenize click-to-focus across Windows and macOS"
type: feat
status: active
date: 2026-06-05
---

## Summary

Port the WSL2 XmlDocument-based click-to-focus approach to native Windows, fix the broken macOS click-to-focus (replace non-existent `code --focus` with `code <project-path>`), add a VS Code-only notice to documentation, and defer Linux and terminal Claude Code support.

## Problem Frame

WSL2 click-to-focus shipped with the XmlDocument + `vscode://` protocol approach. Two platforms lag behind:

- **Windows native** (`_notify_windows`) still uses the legacy `GetTemplateContent(2)` pattern with an unregistered `'Claude Code'` AUMID — no click action at all.
- **macOS** (`_notify_macos`) reads `payload.get('action')` for `terminal-notifier -execute`, but `build_payload` never sets `action`. The `code --focus` flag referenced in tests and prior configuration doesn't exist. The click-to-focus path has never worked in production.

The plugin also needs a VS Code-only notice: click-to-focus depends on VS Code being installed (the `code` CLI on macOS, `vscode://` protocol handler on Windows). Terminal Claude Code (non-VS Code extension) is out of scope for now.

## Requirements

- **R1.** Native Windows toast notifications include a clickable action that opens VS Code via `vscode://file/<absolute-path>`.
- **R2.** Native Windows uses the same XmlDocument + registered AUMID pattern as WSL2.
- **R3.** macOS `build_payload` returns an `action` key with `code <project-path>`, consumed by `terminal-notifier -execute`.
- **R4.** The `action` key is present in all three event-type payloads (permission, stop, error) so macOS click-to-focus works for every notification.
- **R5.** README documents that click-to-focus requires VS Code; terminal Claude Code is noted as not yet supported.
- **R6.** Existing notification behavior is preserved: same subprocess contract (`check=False`, timeouts, `DEVNULL`), same silent-failure guarantee (R11), same title/message/urgency semantics.
- **R11.** If the OS notification mechanism is unavailable or fails, the system fails silently — no crash, no exception propagation, no interruption to Claude Code.

## Key Technical Decisions

- **Extend `build_payload` with `action`, not each backend.** Adding `action` at payload construction time means all three backends receive it without changing their signatures. macOS consumes it for `terminal-notifier -execute`; Windows and Linux ignore it. This matches the existing pattern of platform-agnostic payload construction.
- **`vscode://file/<path>` for native Windows.** The `vscode://file/` protocol scheme opens a local file or folder in VS Code. On native Windows, `os.getcwd()` returns backslash-separated paths — these must be normalized to forward slashes via `Path(os.getcwd()).as_posix()` to produce a valid URI (`Path` is already imported from `pathlib`). Unlike WSL2 which needs the `vscode-remote/wsl+<distro>` indirection, native Windows has no intermediate layer.
- **`code <path>` for macOS.** `code` is the VS Code CLI installed in PATH during VS Code setup. Passing a directory path opens that folder and brings VS Code to the foreground. This replaces `code --focus` which is not a valid flag. No additional escaping is needed since `terminal-notifier` passes the argument to the shell.
- **Reuse the XmlDocument pattern from `_notify_wsl` verbatim for `_notify_windows`.** The only difference is the URI construction (no distro prefix) and the command name (`powershell` vs `powershell.exe`). The XML escaping, AUMID, and toast XML structure are identical.

## Implementation Units

### U1. Add `action` to `build_payload` for macOS click-to-focus

- **Goal:** Set the `action` key on every payload returned by `build_payload` so `_notify_macos` can pass it to `terminal-notifier -execute`.
- **Requirements:** R3, R4
- **Dependencies:** None
- **Files:**
  - `plugin/notify.py` — modify `build_payload` function (three return statements)
  - `plugin/tests/test_notify.py` — update `test_build_payload_permission`, `test_build_payload_stop`, `test_build_payload_error`
- **Approach:**
  1. Resolve `project_path = os.getcwd()` once at the top of `build_payload` (already has `project = os.path.basename(os.getcwd())`).
  2. Add `'action': f'code {project_path}'` to each of the three return dicts.
  3. The `action` value is `code <absolute-path>` — on macOS this opens the folder in VS Code and brings it to the foreground.
- **Patterns to follow:** Existing `build_payload` return dict structure. The `project` variable is already derived from `os.getcwd()` — add `project_path` alongside it.
- **Test scenarios:**
  - **Happy path — permission:** `build_payload('permission', {'tool_name': 'Bash'})` returns `action` key containing `code` and the mocked cwd path.
  - **Happy path — stop:** `build_payload('stop', {})` returns `action` key.
  - **Happy path — error:** `build_payload('error', {'error': 'test failure'})` returns `action` key.
  - **Edge case:** cwd contains spaces — `action` value preserves them (shell handles quoting via `terminal-notifier` argument list).
- **Verification:** `make test` passes. Existing macOS test `test_terminal_notifier_includes_action` still passes (it injects its own `action`, not affected).

### U2. Rewrite `_notify_windows` with XmlDocument-based click-to-focus

- **Goal:** Replace the `GetTemplateContent(2)`-based `_notify_windows` with the XmlDocument-based approach, matching the `_notify_wsl` pattern with a `vscode://file/<path>` URI.
- **Requirements:** R1, R2, R6
- **Dependencies:** None (can proceed in parallel with U1)
- **Files:**
  - `plugin/notify.py` — rewrite `_notify_windows` function
- **Approach:**
  1. Mirror the `_notify_wsl` structure: define `_xml_escape` helper, escape title/message, build toast XML with `<actions>`, use PowerShell's registered AUMID.
  2. Construct URI as `f'vscode://file/{Path(os.getcwd()).as_posix()}'` — normalizes Windows backslashes to forward slashes for a valid URI.
  3. Keep `powershell` as the command name (existing convention for native Windows, distinct from `powershell.exe` used in WSL2).
  4. Remove the old `.replace("'", "''")` single-quote escaping — replaced by XML escaping.
  5. Update the docstring to document click-to-focus behavior.
- **Patterns to follow:** `_notify_wsl` function verbatim — same XML structure, same AUMID, same subprocess invocation pattern. The only differences are the URI format and the command name.
- **Test scenarios:**
  - **Happy path:** PowerShell command includes `XmlDocument` type load, `LoadXml`, `<actions>` with `activationType="protocol"`, `vscode://file/` URI with cwd, and the registered PowerShell AUMID.
  - **XML escaping:** Title contains `&`, `<`, `>`, `'`, `"` — escaped to `&amp;`, `&lt;`, `&gt;`, `&apos;`, `&quot;` in the XML string.
  - **Subprocess contract:** `check=False`, `timeout=10`, `DEVNULL` redirection on both stdout and stderr.
- **Verification:** `make test` passes. Manual test on native Windows: notification appears and clicking it brings VS Code to the foreground.

### U3. Expand test coverage for homogenized backends

- **Goal:** Bring `_notify_windows` and `_notify_macos` test coverage to parity with the WSL2 test suite.
- **Requirements:** R1, R3, R6
- **Dependencies:** U1, U2
- **Files:**
  - `plugin/tests/test_notify.py` — add new tests, update existing ones
- **Approach:**
  1. **`_notify_windows` tests** — follow the WSL test pattern: happy path (XmlDocument, vscode://file/ URI, AUMID), XML escaping, subprocess contract. Replace the minimal existing `test_notify_windows_powershell` with thorough assertions.
  2. **`_notify_macos` tests** — add test for action absent from payload (no `-execute` flag), subprocess contract test.
  3. **`build_payload` tests** — add assertion for `action` key presence and content in existing payload tests.
- **Patterns to follow:** Existing test patterns in `test_notify_wsl_*` functions. Mock `subprocess.run`, assert on `call_args[0][0]` for command structure and `call_args[1]` for kwargs.
- **Test scenarios:**
  - **`_notify_windows` happy path:** `mock.patch('os.getcwd', return_value='C:\\Users\\test\\project')` — PowerShell command includes `vscode://file/C:/Users/test/project` (forward slashes), `XmlDocument` type load, `<actions>`, registered AUMID.
  - **`_notify_windows` XML escaping:** Special characters in title/message are escaped in the XML string passed to `LoadXml`.
  - **`_notify_windows` subprocess contract:** `check=False`, `timeout=10`, `DEVNULL` redirection.
  - **`_notify_macos` without action:** When payload has no `action` key, `terminal-notifier` command does not include `-execute`.
  - **`_notify_macos` subprocess contract:** `check=False`, `timeout=5`, `DEVNULL` redirection.
  - **`build_payload` action presence:** All three event types include `action` key with `code` and cwd.
- **Verification:** `make test` passes. Test count reflects new coverage.

### U4. Update documentation with VS Code-only notice

- **Goal:** Document that click-to-focus requires VS Code, note terminal Claude Code as not yet supported, update platform table.
- **Requirements:** R5
- **Dependencies:** None (can proceed in parallel with U1-U3)
- **Files:**
  - `README.md` — update platform table and add VS Code-only notice
- **Approach:**
  1. Update platform table: macOS click-to-focus now uses `code <project-path>` via terminal-notifier; Windows uses `vscode://` protocol via XmlDocument toast action.
  2. Add a note below the table: this plugin requires VS Code for click-to-focus; terminal Claude Code (non-VS Code extension) is not yet supported.
- **Patterns to follow:** Existing README table format and prose style.
- **Test scenarios:** None — documentation only. Test expectation: none — pure documentation change.
- **Verification:** Visual review of rendered README.

## Scope Boundaries

### Deferred to Follow-Up Work

- **Linux click-to-focus.** No reliable cross-desktop click-action mechanism exists in libnotify. `wmctrl`/`xdotool` are mentioned in the current docs but not wired into the plugin.
- **Terminal Claude Code (non-VS Code extension).** Click-to-focus depends on VS Code being the host; terminal Claude Code has no window to focus. Could be addressed later with a different mechanism (e.g., terminal bell + OS-specific window raise).

## Risks & Dependencies

- **Windows native testing.** The `_notify_windows` rewrite follows the exact pattern proven in `_notify_wsl`, but manual testing requires a native Windows machine (not WSL). The code change is structurally identical to the already-working WSL2 path — the only difference is the URI format.
- **`code` CLI on macOS.** Assumes `code` is in PATH (VS Code installs it via Shell Command: Install 'code' command in PATH). If missing, `terminal-notifier -execute` will fail silently (R11 — notification still appears, just no click action).
