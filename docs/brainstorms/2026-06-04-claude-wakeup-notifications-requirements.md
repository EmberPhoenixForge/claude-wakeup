---
date: 2026-06-04
topic: claude-wakeup-notifications
---

## Summary

A hooks-driven notification system that sends OS-native desktop alerts when Claude Code needs user attention — permission prompts, task completion, or errors. Clicking a notification brings VS Code to the foreground. Installed by dropping hook scripts into a project and adding configuration to `.claude/settings.json`.

---

## Problem Frame

When using Claude Code in VS Code, the user launches an implementation, switches to other work while Claude runs, and has no way to know when Claude needs them back. The current workaround is manual alt-tabbing to check — a productivity tax that burns attention on both sides: checking too often wastes focus, checking too late leaves Claude idle waiting for permission or next steps. GitHub Copilot and other VS Code tools already solve this with notifications, but Claude Code has no equivalent. The cost is real: a multi-step implementation task can involve several round-trips where Claude sits blocked while the user is unaware.

---

## Requirements

**Event Detection**

- R1. When Claude Code is blocked waiting for tool-use permission, the system sends a notification.
- R2. When Claude Code completes a response (the session returns to idle, waiting for the next user message), the system sends a notification.
- R3. When Claude Code encounters an error or cannot proceed without user intervention, the system sends a notification.

**Notification Content**

- R4. Each notification includes a summary of the event: what Claude is waiting for (R1), what completed (R2), or what went wrong (R3).
- R5. Notifications identify the project or session that triggered them so the user can distinguish alerts from multiple concurrent Claude sessions.

**Notification Behavior**

- R6. Clicking a notification brings VS Code to the foreground with focus on the Claude Code session that sent it.
- R7. Multiple tool-use permission waits within a single response cycle produce at most one notification (deduplication per state transition, not per tool call).
- R8. Notifications are delivered within a few seconds of the state transition.

**Installation and Configuration**

- R9. Installation consists of copying hook scripts to a known location and adding hook entries to `.claude/settings.json`.
- R10. The system works cross-platform using each platform's native notification mechanism (Linux: `notify-send`, macOS: `osascript`, Windows: toast notifications).

**Failure Handling**

- R11. If the OS notification mechanism is unavailable (e.g., no notification daemon running), the system fails silently without blocking or interrupting Claude Code.

---

## Key Decisions

- **OS-native notifications over VS Code-native toasts.** VS Code toasts require an extension; OS notifications achieve the same goal — alert the user and pull focus back to VS Code — with a simpler install and no extension dependency. The trade-off is losing inline action buttons (approve/deny from the notification itself); the user acts after returning to VS Code.
- **Hooks-driven detection over extension-level integration.** Claude Code's hook system (`preToolUse`, `stop`, etc.) provides event detection without coupling to the extension's internals or release cycle. The hooks surface is the stable integration point.
- **Per-state-transition deduplication.** A response cycle that triggers multiple tool-use permission waits (e.g., 5 sequential Bash calls) fires one "Claude needs permission" notification, not 5. The user's mental model is "Claude is waiting for me," not "there are N pending approvals."

---

## Key Flows

- F1. Install and configure
  - **Trigger:** User wants to enable notifications for a Claude Code project.
  - **Steps:** Copy hook scripts to the project (or a shared location). Add `preToolUse`, `stop`, and `error` hook entries to `.claude/settings.json` pointing at the scripts. No additional dependencies or daemons.
  - **Outcome:** Notifications fire on the next Claude Code session.

- F2. Notification on permission prompt
  - **Trigger:** Claude Code is about to execute a tool that requires user approval.
  - **Actors:** Claude Code (hook system), notification script, OS notification daemon.
  - **Steps:** The `preToolUse` hook fires the notification script. The script determines whether this is the first permission prompt in the current response cycle. If yes, it sends an OS notification with a summary of the tool and the prompt. If no (a prior notification was already sent this cycle), it is suppressed.
  - **Outcome:** The user sees a desktop notification and can click it to return to VS Code to approve or deny.

- F3. Notification on task completion
  - **Trigger:** Claude Code finishes a response and the session is idle.
  - **Actors:** Claude Code (hook system), notification script, OS notification daemon.
  - **Steps:** The `stop` hook fires the notification script. The script sends an OS notification summarizing the completed task.
  - **Outcome:** The user knows Claude is done and can review results.

- F4. Click-to-focus
  - **Trigger:** User clicks the OS notification.
  - **Steps:** The notification's click action runs a platform-specific command to bring VS Code to the foreground (e.g., `wmctrl` on Linux, `osascript` on macOS, Windows API call). If multiple VS Code windows are open, the one hosting the Claude session is targeted.
  - **Outcome:** VS Code is in the foreground with the Claude session visible.

---

## Acceptance Examples

- AE1. Multiple tool approvals in one response — single notification
  - **Covers R7.**
  - **Given** Claude Code is executing a multi-step task that requires 3 Bash approvals and 2 Write approvals in one response cycle.
  - **When** the first tool-use permission prompt fires.
  - **Then** the user receives one "Claude needs permission" notification. Subsequent prompts in the same cycle do not produce additional notifications.

- AE2. Notification with VS Code in background
  - **Covers R6.**
  - **Given** VS Code is minimized or behind other windows, and Claude Code completes a response.
  - **When** the user clicks the OS notification.
  - **Then** VS Code comes to the foreground with the Claude Code session focused.

- AE3. Notification daemon unavailable
  - **Covers R11.**
  - **Given** The OS notification daemon is not running (e.g., headless environment, minimal window manager).
  - **When** a notification would be sent.
  - **Then** the hook script exits silently with no error surfaced to Claude Code or the user.

- AE4. Two concurrent Claude sessions
  - **Covers R5.**
  - **Given** The user has two VS Code windows open, each running a separate Claude Code session in different projects.
  - **When** one session triggers a notification.
  - **Then** the notification text identifies which project triggered it, and clicking the notification focuses the correct VS Code window.

---

## Scope Boundaries

- **Inline notification actions (approve/deny buttons).** OS notifications do not support rich interactive buttons that feed back into Claude Code. The user clicks the notification to return to VS Code and takes action from there.
- **Mobile or remote notifications.** This system targets desktop notifications only — the user is assumed to be at their machine with VS Code running.
- **Notification history or persistence.** Notifications are real-time; missed notifications are not queued or logged for later review.
- **Per-event-type notification toggles.** All three event types (permission, completion, error) are notified. Individual toggles are deferred — no evidence yet that users want to silence some categories.

---

## Dependencies / Assumptions

- **Claude Code hooks.** The system depends on `preToolUse` (permission prompts), `stop` (completion), and error-adjacent hooks being present and stable in Claude Code. Hook scripts receive sufficient context (project path, tool name, session identifier) to compose meaningful notifications.
- **Platform notification tools.** Linux assumes `notify-send` (libnotify) is available. macOS assumes `osascript` with System Events access. Windows assumes the Toast notification system is reachable.
- **WSL2 notification bridging.** On WSL2, Linux `notify-send` may not natively reach the Windows notification center. The system assumes a bridging tool (such as `wsl-notify-send` or `powershell.exe` toast invocation) is configured, or treats the WSL2 case as an environment-specific setup step.
- **VS Code focus mechanism.** The system assumes a platform-specific command exists to bring a specific VS Code window to the foreground. This is verified for each platform during planning.
