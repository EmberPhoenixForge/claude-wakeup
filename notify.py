#!/usr/bin/env python3
"""Claude Wakeup — OS-native desktop notifications for Claude Code.

Invoked by Claude Code hooks via hooks/notify.sh. Reads event context from
stdin JSON (matching the Hookify plugin pattern). Handles platform detection,
notification dispatch, per-cycle deduplication, and graceful failure.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def detect_platform():
    """Return 'linux', 'macos', or 'windows'."""
    if sys.platform.startswith('linux'):
        return 'linux'
    if sys.platform == 'darwin':
        return 'macos'
    if sys.platform in ('win32', 'cygwin'):
        return 'windows'
    return 'linux'  # fallback


# ---------------------------------------------------------------------------
# Session identification and dedup state
# ---------------------------------------------------------------------------

def get_session_id():
    """Derive a session-scoped identifier for dedup state isolation.

    Tries environment variables Claude Code may set, then falls back to a
    deterministic hash of cwd + parent PID — a heuristic that provides
    per-session uniqueness for the common case.
    """
    for var in ('CLAUDE_SESSION_ID', 'CLAUDE_PROJECT_DIR'):
        val = os.environ.get(var)
        if val:
            return val

    raw = f"{os.getcwd()}:{os.getppid()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def get_state_path():
    """Return path to the dedup state file for this session."""
    session_id = get_session_id()
    # Sanitize for cross-platform filename safety (colons illegal on Windows)
    safe_id = session_id.replace(':', '-').replace('\\', '-').replace('/', '-')
    base = Path('/tmp') if sys.platform != 'win32' else Path(os.environ.get('TEMP', '/tmp'))
    return base / f'claude-wakeup-{safe_id}.json'


def read_state(path):
    """Read dedup state, returning None if file missing or stale (PID gone)."""
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    # Stale check: if the PID that wrote this state is no longer alive,
    # treat as a fresh session (handles crash-before-SessionEnd).
    pid = data.get('pid')
    if pid is not None:
        try:
            os.kill(pid, 0)
        except OSError:
            return None
    return data


def write_state(path, data):
    """Persist dedup state with PID and timestamp for staleness detection."""
    data['pid'] = os.getpid()
    data['ts'] = time.time()
    with open(path, 'w') as fh:
        json.dump(data, fh)


def clear_state(path):
    """Remove dedup state file (SessionEnd cleanup)."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Event context from stdin (Hookify pattern)
# ---------------------------------------------------------------------------

def read_event_context():
    """Read hook event context from stdin JSON.

    Claude Code hooks pipe event context as JSON to stdin (confirmed by the
    Hookify plugin reference implementation). Returns an empty dict on any
    failure so the caller always has a safe default.
    """
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return {}


# ---------------------------------------------------------------------------
# Platform notification backends
# ---------------------------------------------------------------------------

def _notify_linux(payload):
    """Send notification via notify-send (libnotify)."""
    cmd = ['notify-send', '--app-name', 'Claude Code']
    urgency = payload.get('urgency')
    if urgency and urgency in ('low', 'normal', 'critical'):
        cmd += ['--urgency', urgency]
    cmd += [payload['title'], payload['message']]
    subprocess.run(cmd, check=False, timeout=5,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _notify_macos(payload):
    """Send notification, preferring terminal-notifier for click actions.

    terminal-notifier supports -execute for click-to-focus; osascript's
    display notification is fire-and-forget with no click callback.
    """
    if shutil.which('terminal-notifier'):
        cmd = [
            'terminal-notifier',
            '-title', payload['title'],
            '-message', payload['message'],
            '-group', 'claude-wakeup',
        ]
        action = payload.get('action')
        if action:
            cmd += ['-execute', action]
        subprocess.run(cmd, check=False, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Fallback: plain osascript (no click action — documented limitation)
        title = payload['title'].replace('"', '\\"')
        message = payload['message'].replace('"', '\\"')
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(['osascript', '-e', script], check=False, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _notify_windows(payload):
    """Send notification via PowerShell toast (Windows 10+)."""
    title = payload['title'].replace("'", "''")
    message = payload['message'].replace("'", "''")
    ps_script = (
        "[Windows.UI.Notifications.ToastNotificationManager,"
        "Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;"
        "$t=[Windows.UI.Notifications.ToastNotificationManager]"
        "::GetTemplateContent(2);"
        "$t.GetElementsByTagName('text').Item(0).AppendChild("
        "$t.CreateTextNode('%s'))|Out-Null;"
        "$t.GetElementsByTagName('text').Item(1).AppendChild("
        "$t.CreateTextNode('%s'))|Out-Null;"
        "[Windows.UI.Notifications.ToastNotificationManager]"
        "::CreateToastNotifier('Claude Code').Show("
        "[Windows.UI.Notifications.ToastNotification]::new($t))"
    ) % (title, message)
    subprocess.run(['powershell', '-Command', ps_script], check=False, timeout=10,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# Notification dispatch
# ---------------------------------------------------------------------------

BACKENDS = {
    'linux': _notify_linux,
    'macos': _notify_macos,
    'windows': _notify_windows,
}


def dispatch(payload):
    """Route a notification payload to the platform-appropriate backend."""
    backend = BACKENDS.get(detect_platform(), _notify_linux)
    try:
        backend(payload)
    except Exception:
        pass  # R11: never let a notification failure block Claude Code


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------

def build_payload(event, context):
    """Build a structured notification payload from event type and context."""
    project = os.path.basename(os.getcwd())

    if event == 'permission':
        tool = context.get('tool_name', 'a tool')
        return {
            'title': f'Claude needs permission — {project}',
            'message': f'Claude wants to run {tool}. Switch to VS Code to approve or deny.',
            'urgency': 'normal',
        }
    if event == 'stop':
        return {
            'title': f'Claude finished — {project}',
            'message': 'Task complete. Switch to VS Code for next steps.',
            'urgency': 'low',
        }
    if event == 'error':
        error_msg = context.get('error', 'an error occurred')
        return {
            'title': f'Claude hit an error — {project}',
            'message': f'{error_msg}. Switch to VS Code to help resolve it.',
            'urgency': 'critical',
        }
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        sys.exit(0)

    event = sys.argv[1]
    state_path = get_state_path()

    # Internal signals — never produce user-visible notifications
    if event == 'cycle-reset':
        clear_state(state_path)
        sys.exit(0)

    if event == 'cleanup':
        clear_state(state_path)
        sys.exit(0)

    # User-visible events
    if event in ('permission', 'stop', 'error'):
        state = read_state(state_path)

        # Dedup: permission fires at most once per response cycle (R7, AE1)
        if event == 'permission' and state and state.get('permission_fired'):
            sys.exit(0)

        context = read_event_context()
        payload = build_payload(event, context)
        if payload:
            dispatch(payload)

        # Update dedup state
        if state is None:
            state = {}
        if event == 'permission':
            state['permission_fired'] = True
        write_state(state_path, state)

    sys.exit(0)


if __name__ == '__main__':
    main()
