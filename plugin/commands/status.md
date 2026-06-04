---
description: "Check Claude Wakeup plugin status — hooks, daemon availability, last notification"
argument-hint: ""
disable-model-invocation: true
---

# /claude-wakeup:status

Report the current state of the Claude Wakeup plugin:

- Whether the plugin is enabled and hooks are active
- Which events are wired (PermissionRequest, Stop, PostToolUseFailure)
- Whether the platform notification daemon is reachable (notify-send on Linux, terminal-notifier or osascript on macOS, PowerShell on Windows)
- When the last notification fired (from the dedup state file, if present)
- Python version and availability

Use this to diagnose issues when notifications aren't appearing.
