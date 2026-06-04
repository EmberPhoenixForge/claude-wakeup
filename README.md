# claude-wakeup

OS-native desktop notifications for Claude Code. Get notified when Claude needs your attention — permission prompts, task completion, and errors. Click a notification to bring VS Code to the foreground.

## How it works

Claude Wakeup is a Claude Code plugin that hooks into Claude's event system. When Claude is blocked waiting for tool-use permission, finishes a task, or hits an error, the plugin sends a desktop notification via your OS notification system.

- **Permission prompts** — notified once per response cycle (not once per tool call)
- **Task completion** — know the moment Claude finishes
- **Errors** — alerted when Claude can't proceed without you

## Install

**Via plugin marketplace (recommended):**

```
/plugin marketplace add EmberPhoenixForge/claude-wakeup
/plugin install claude-wakeup
```

**Manual install:**

```
make install   # prints install instructions
cp -r . ~/.claude/plugins/claude-wakeup
```

After installing, run `/claude-wakeup:config` in any Claude Code session to verify setup.

## Slash commands

| Command | Description |
|---------|-------------|
| `/claude-wakeup:config` | Walk through setup — verify Python, notification daemon, send test |
| `/claude-wakeup:test` | Send a test notification to confirm end-to-end delivery |
| `/claude-wakeup:status` | Check plugin state, hook wiring, and daemon availability |

## Platform support

| Platform | Notification backend | Click-to-focus |
|----------|---------------------|----------------|
| Linux | `notify-send` (libnotify) | Not yet supported |
| macOS | `terminal-notifier` (preferred) or `osascript` | `code <project-path>` via terminal-notifier `-execute` |
| Windows | PowerShell toast notifications | `vscode://` protocol via XmlDocument toast action |

**WSL2:** Detected automatically via `WSL_DISTRO_NAME` — uses PowerShell toast notifications with `vscode://` protocol for click-to-focus. No additional setup required.

**VS Code required.** Click-to-focus depends on VS Code being installed — the `code` CLI on macOS, and the `vscode://` protocol handler on Windows/WSL2. Terminal Claude Code (non-VS Code extension) is not yet supported.

## Requirements

- Python 3.10+
- Claude Code with plugin support (VS Code extension)
- Platform notification daemon (libnotify on Linux, terminal-notifier on macOS)

## Development

```
make test    # Run tests (pytest + shellcheck) — creates a .venv automatically
make lint    # Lint shell scripts and Python
make clean   # Remove build artifacts and venv
make install # Print install instructions
```

First run of `make test` creates a `.venv` with `pytest`. Requires `python3-venv` (on Debian/Ubuntu: `sudo apt install python3-venv`).
