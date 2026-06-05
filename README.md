# claude-wakeup

OS-native desktop notifications for Claude Code VS Code Extension. Get notified when Claude needs your attention — permission prompts, task completion, and errors. Click a notification to bring VS Code to the foreground.

## Table of contents

- [Platform support](#platform-support)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Install](#install)
- [Update](#update)
- [Configuration](#configuration)
- [Slash commands](#slash-commands)
- [Development & Contributions](#development--contributions)
- [Support](#support-)

## Platform support

| Platform | Notification backend | Click-to-focus | Foreground detection | Status |
|----------|---------------------|----------------|---------------------|--------|
| WSL2 | PowerShell toast | `vscode://` protocol via XmlDocument toast action | PowerShell `GetForegroundWindow` P/Invoke | Release — Ready to use |
| macOS | `osascript` or optional `terminal-notifier`¹ | `code <project-path>` via terminal-notifier `-execute` | `osascript` System Events | Alpha — may be buggy or incomplete |
| Linux | `notify-send` (libnotify) | Not yet supported | `xdotool` (X11 only, Wayland falls back to always-fire) | Alpha — may be buggy or incomplete |
| Windows | PowerShell toast | `vscode://` protocol via XmlDocument toast action | PowerShell `GetForegroundWindow` P/Invoke | Alpha — may be buggy or incomplete |

¹ `terminal-notifier` is optional for basic notifications, but required for click-to-focus on macOS.

**WSL2:** Detected automatically via `WSL_DISTRO_NAME` — uses PowerShell toast notifications. No additional setup required. \
The first time you click a notification to focus VS Code, Windows will show an authorization popup — choose "Always allow" to avoid being prompted on subsequent clicks.

**VS Code required.** Click-to-focus depends on VS Code being installed — the `code` CLI on macOS, and the `vscode://` protocol handler on Windows/WSL2.

## How it works

Claude Wakeup is a Claude Code plugin that hooks into Claude's event system. When Claude is blocked waiting for tool-use permission, finishes a task, or hits an error, the plugin sends a desktop notification via your OS notification system.

- **Permission prompts** — notified once per response cycle (not once per tool call)
- **Task completion** — know the moment Claude finishes
- **Errors** — alerted when Claude can't proceed without you

By default, notifications are suppressed when VS Code is the active foreground window — no need to ping you when you're already looking at Claude.

## Requirements

- Python 3.10+
- Claude Code with plugin support (VS Code extension)
- Platform notification daemon (libnotify on Linux, terminal-notifier on macOS)

## Install

**Via plugin marketplace (recommended):**

```
/plugin marketplace add EmberPhoenixForge/claude-wakeup
/plugin install claude-wakeup
/reload-plugins
```
After installing, run `/claude-wakeup:config` in any Claude Code session to verify setup.

## Update

**Via plugin marketplace (recommended):**

```
/plugin marketplace update claude-wakeup-plugin
/reload-plugins
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CLAUDE_WAKEUP_FOREGROUND` | unset | Set to `1` to fire notifications even when VS Code is the foreground window |
| `CLAUDE_WAKEUP_LOG_DIR` | `~/.claude/claude-wakeup` | Directory for debug logs |

Set these as environment variables in your shell profile or before launching Claude Code.

Debug logs are written to `debug.log` in the log directory. Each line is a JSON entry with timestamp, event type, action, and project name. Use these to troubleshoot notification delivery, suppression, and deduplication behavior.

## Slash commands

| Command | Description |
|---------|-------------|
| `/claude-wakeup:config` | Walk through setup — verify Python, notification daemon, send test |
| `/claude-wakeup:test` | Send a test notification to confirm end-to-end delivery |
| `/claude-wakeup:status` | Check plugin state, hook wiring, and daemon availability |

## Development & Contributions

claude-wakeup is an open-source, community-driven project so contributions are welcome
from everyone. You can file issues to report bugs or request features,
improve documentation, add tests, or submit pull requests with proposed
changes. For larger features please open an issue first to discuss scope;
small fixes and documentation updates can be submitted directly as PRs.
When submitting code, include tests where applicable and keep changes focused so reviews are easy.


```
make test    # Run tests (pytest + shellcheck) — creates a .venv automatically
make lint    # Lint shell scripts and Python
make clean   # Remove build artifacts and venv
make install # Print install instructions
```

First run of `make test` creates a `.venv` with `pytest`. Requires `python3-venv` (on Debian/Ubuntu: `sudo apt install python3-venv`).

## Support 💖

If you don't code but want to support the project, you can sponsor the project on GitHub Sponsors:

[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-GitHub-6f42c1?style=for-the-badge&logo=github)](https://github.com/sponsors/EmberPhoenixForge)
