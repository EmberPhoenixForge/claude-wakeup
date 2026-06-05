---
description: "Send a test notification to verify Claude Wakeup is working"
argument-hint: ""
disable-model-invocation: true
---

# /claude-wakeup:test

Read only notify.py, this execution need to be fast and not involve any Claude processing, so we bypass the normal plugin execution flow and directly run the notification dispatch logic.
Send a test desktop notification to confirm Claude Wakeup is working end-to-end.

This runs the Python dispatch engine directly and sends a notification with the title "Claude Wakeup" and the message "Test notification — Claude Wakeup is working." If you see the notification, the plugin is configured correctly. Click it to verify click-to-focus behavior (brings VS Code to the foreground on supported platforms).

If you don't see a notification, run `/claude-wakeup:status` to diagnose.
