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
import xml.sax.saxutils
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Debug logging
# ---------------------------------------------------------------------------

def _log_dir():
    """Return the debug log directory, creating it if needed."""
    path = Path(os.environ.get('CLAUDE_WAKEUP_LOG_DIR',
                               Path.home() / '.claude' / 'claude-wakeup'))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _log(event, action, detail=''):
    """Append a JSON-lines debug entry to the session log."""
    try:
        entry = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'event': event,
            'action': action,
            'project': os.path.basename(os.getcwd()),
        }
        if detail:
            entry['detail'] = detail
        log_path = _log_dir() / 'debug.log'
        with open(log_path, 'a') as fh:
            fh.write(json.dumps(entry, default=str) + '\n')
    except Exception:
        pass  # logging failure must never break notifications


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
    # os.kill(pid, 0) is a Unix-only concept — skip on Windows.
    pid = data.get('pid')
    if pid is not None and sys.platform != 'win32':
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

def _is_wsl():
    """Return True if running under WSL (Windows Subsystem for Linux)."""
    return os.environ.get('WSL_DISTRO_NAME') is not None


def _notify_linux(payload):
    """Send notification via notify-send (libnotify). On WSL2, uses PowerShell."""
    if _is_wsl():
        _notify_wsl(payload)
        return

    cmd = ['notify-send', '--app-name', 'Claude Code']
    urgency = payload.get('urgency')
    if urgency and urgency in ('low', 'normal', 'critical'):
        cmd += ['--urgency', urgency]
    cmd += [payload['title'], payload['message']]
    subprocess.run(cmd, check=False, timeout=5,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _notify_wsl(payload):
    """Send notification via PowerShell toast on WSL2 with click-to-focus.

    Builds custom toast XML with a clickable action using the vscode://
    protocol. When WSL_DISTRO_NAME is unset (non-WSL Linux or degraded
    environment), falls back to a notification without the click action.
    """
    # XML-escape text content, including single quotes that would otherwise
    # terminate the PowerShell single-quoted string wrapping LoadXml.
    def _xml_escape(s):
        return xml.sax.saxutils.escape(s, {'"': '&quot;', "'": '&apos;'})

    title = _xml_escape(payload['title'])
    message = _xml_escape(payload['message'])

    distro = os.environ.get('WSL_DISTRO_NAME')

    if distro:
        vscode_uri = f'vscode://vscode-remote/wsl+{distro}{os.getcwd()}'
        toast_xml = (
            '<toast><visual><binding template="ToastGeneric">'
            f'<text>{title}</text>'
            f'<text>{message}</text>'
            '</binding></visual>'
            '<actions>'
            f'<action content="Open VS Code" arguments="{vscode_uri}" activationType="protocol"/>'
            '</actions></toast>'
        )
    else:
        toast_xml = (
            '<toast><visual><binding template="ToastGeneric">'
            f'<text>{title}</text>'
            f'<text>{message}</text>'
            '</binding></visual></toast>'
        )

    aumid = ('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}'
             '\\WindowsPowerShell\\v1.0\\powershell.exe')

    ps = (
        '[Windows.UI.Notifications.ToastNotificationManager,'
        'Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;'
        '[Windows.Data.Xml.Dom.XmlDocument,'
        'Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null;'
        '$x=[Windows.Data.Xml.Dom.XmlDocument]::new();'
        f"$x.LoadXml('{toast_xml}');"
        '[Windows.UI.Notifications.ToastNotificationManager]'
        f"::CreateToastNotifier('{aumid}').Show("
        '[Windows.UI.Notifications.ToastNotification]::new($x))'
    )

    subprocess.run(['powershell.exe', '-Command', ps], check=False, timeout=10,
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
    """Send notification via PowerShell toast on Windows with click-to-focus.

    Builds custom toast XML with a clickable action using the vscode://
    protocol. Mirrors the WSL2 XmlDocument approach with a vscode://file/
    URI for native Windows paths.
    """
    def _xml_escape(s):
        return xml.sax.saxutils.escape(s, {'"': '&quot;', "'": '&apos;'})

    title = _xml_escape(payload['title'])
    message = _xml_escape(payload['message'])

    # Normalize Windows backslashes to forward slashes for a valid URI
    vscode_uri = 'vscode://file/' + os.getcwd().replace('\\', '/')
    toast_xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f'<text>{title}</text>'
        f'<text>{message}</text>'
        '</binding></visual>'
        '<actions>'
        f'<action content="Open VS Code" arguments="{vscode_uri}" activationType="protocol"/>'
        '</actions></toast>'
    )

    aumid = ('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}'
             '\\WindowsPowerShell\\v1.0\\powershell.exe')

    ps_script = (
        '[Windows.UI.Notifications.ToastNotificationManager,'
        'Windows.UI.Notifications,ContentType=WindowsRuntime]|Out-Null;'
        '[Windows.Data.Xml.Dom.XmlDocument,'
        'Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]|Out-Null;'
        '$x=[Windows.Data.Xml.Dom.XmlDocument]::new();'
        f"$x.LoadXml('{toast_xml}');"
        '[Windows.UI.Notifications.ToastNotificationManager]'
        f"::CreateToastNotifier('{aumid}').Show("
        '[Windows.UI.Notifications.ToastNotification]::new($x))'
    )

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
    project_path = os.getcwd()
    action = f'code {project_path}'

    if event == 'permission':
        tool = context.get('tool_name', 'a tool')
        return {
            'title': f'Claude needs permission — {project}',
            'message': f'Claude wants to run {tool}. Switch to VS Code to approve or deny.',
            'urgency': 'normal',
            'action': action,
        }
    if event == 'stop':
        return {
            'title': f'Claude finished — {project}',
            'message': 'Task complete. Switch to VS Code for next steps.',
            'urgency': 'low',
            'action': action,
        }
    if event == 'error':
        error_msg = context.get('error', 'an error occurred')
        return {
            'title': f'Claude hit an error — {project}',
            'message': f'{error_msg}. Switch to VS Code to help resolve it.',
            'urgency': 'critical',
            'action': action,
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
        _log(event, 'state_cleared')
        clear_state(state_path)
        sys.exit(0)

    if event == 'cleanup':
        _log(event, 'state_removed')
        clear_state(state_path)
        sys.exit(0)

    # User-visible events
    if event in ('permission', 'stop', 'error'):
        context = read_event_context()
        _log(event, 'received', context.get('tool_name', context.get('error', '')))

        state = read_state(state_path)

        # Dedup: permission fires at most once per response cycle (R7, AE1)
        if event == 'permission' and state and state.get('permission_fired'):
            _log(event, 'suppressed', 'dedup: already fired this cycle')
            sys.exit(0)

        payload = build_payload(event, context)
        if payload:
            dispatch(payload)
            _log(event, 'dispatched', payload.get('message', ''))

        # Update dedup state
        if state is None:
            state = {}
        if event == 'permission':
            state['permission_fired'] = True
        write_state(state_path, state)

    sys.exit(0)


if __name__ == '__main__':
    main()
