---
description: "Configure Claude Wakeup — set up notifications and verify everything works"
argument-hint: ""
---

# /claude-wakeup:config

Configure Claude Wakeup for this project. This command walks you through setup:

1. Verifies Python 3 is available
2. Checks that the platform notification daemon is reachable
3. Sends a test notification so you can confirm delivery
4. Confirms the plugin hooks are active

Run this once after enabling the plugin. To change settings later, run it again.

## Setup Steps

Check your environment first and report status, then offer to send a test notification and confirm the hooks configuration in `hooks/hooks.json` is wired correctly.

If anything is wrong — Python missing, notification daemon unreachable — explain the issue and what the user should do (install Python, install libnotify / terminal-notifier, etc.).
