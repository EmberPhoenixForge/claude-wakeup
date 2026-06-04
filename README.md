# claude-wakeup

OS-native desktop notifications for Claude Code. Get notified when Claude needs your attention — permission prompts, task completion, and errors. Click a notification to bring VS Code to the foreground.

## How it works

Claude Wakeup is a Claude Code plugin that hooks into Claude's event system. When Claude is blocked waiting for tool-use permission, finishes a task, or hits an error, the plugin sends a desktop notification via your OS notification system.

- **Permission prompts** — notified once per response cycle (not once per tool call)
- **Task completion** — know the moment Claude finishes
- **Errors** — alerted when Claude can't proceed without you

## Install

1. Copy or symlink this directory into `~/.claude/plugins/claude-wakeup/`:
   ```
   make install
   ```
2. Enable the plugin in Claude Code settings.
3. Run `/claude-wakeup:config` in any Claude Code session to verify setup.

## Slash commands

| Command | Description |
|---------|-------------|
| `/claude-wakeup:config` | Walk through setup — verify Python, notification daemon, send test |
| `/claude-wakeup:test` | Send a test notification to confirm end-to-end delivery |
| `/claude-wakeup:status` | Check plugin state, hook wiring, and daemon availability |

## Platform support

| Platform | Notification backend | Click-to-focus |
|----------|---------------------|----------------|
| Linux | `notify-send` (libnotify) | `wmctrl` or `xdotool` |
| macOS | `terminal-notifier` (preferred) or `osascript` | terminal-notifier `-execute` |
| Windows | PowerShell toast notifications | Via toast activation |

**WSL2:** Linux `notify-send` may not reach Windows notifications without a bridge. Install `wsl-notify-send` or configure PowerShell toast fallback.

## Requirements

- Python 3.8+
- Claude Code with plugin support
- Platform notification daemon (libnotify on Linux, terminal-notifier on macOS)

## Development

```
make test    # Run tests (pytest + shellcheck)
make lint    # Lint shell scripts and Python
make clean   # Remove build artifacts
make install # Install plugin to ~/.claude/plugins/
```
