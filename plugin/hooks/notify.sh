#!/bin/sh
# Claude Wakeup — hook entry point
# Invoked by Claude Code hooks (hooks/hooks.json) on hook events.
# Delegates to notify.py with the correct --event argument.
# Exits silently if Python is unavailable (never blocks Claude Code).

set -e

# Resolve the plugin root from the environment variable set by Claude Code.
# Fall back to the script's own directory structure for local testing.
if [ -n "${CLAUDE_PLUGIN_ROOT}" ]; then
    PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
else
    PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi

NOTIFY_PY="${PLUGIN_ROOT}/notify.py"

# Python not available → exit silently (R11: never block Claude Code)
if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi

# Map hook event name (first argument) to notify.py --event value
EVENT_ARG="${1:-}"
case "$EVENT_ARG" in
    permission)    EVENT="permission" ;;
    stop)          EVENT="stop" ;;
    error)         EVENT="error" ;;
    cycle-reset)   EVENT="cycle-reset" ;;
    cleanup)       EVENT="cleanup" ;;
    *)
        # Unknown event — try to derive from the hook event name
        # hooks.json passes 'permission', 'stop', etc. as argv[1]
        exit 0
        ;;
esac

# Invoke the Python dispatch engine.
# Event context (tool name, error message, etc.) is passed via stdin
# by the Claude Code hook runner — notify.py reads from stdin.
exec python3 "$NOTIFY_PY" "$EVENT"
