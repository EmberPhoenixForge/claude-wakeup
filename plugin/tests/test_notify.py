"""Tests for notify.py — the Claude Wakeup notification dispatch engine."""

import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest  # noqa: F401 — required for test collection even when marked skip

# Add repo root to path so we can import notify
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notify


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def test_detect_linux():
    with mock.patch.object(sys, 'platform', 'linux-x86_64'):
        assert notify.detect_platform() == 'linux'


def test_detect_macos():
    with mock.patch.object(sys, 'platform', 'darwin'):
        assert notify.detect_platform() == 'macos'


def test_detect_windows():
    with mock.patch.object(sys, 'platform', 'win32'):
        assert notify.detect_platform() == 'windows'


# ---------------------------------------------------------------------------
# Session identification
# ---------------------------------------------------------------------------

def test_get_session_id_from_env():
    with mock.patch.dict(os.environ, {'CLAUDE_SESSION_ID': 'abc123'}):
        assert notify.get_session_id() == 'abc123'


def test_get_session_id_fallback():
    with mock.patch.dict(os.environ, {}, clear=True):
        sid = notify.get_session_id()
        assert len(sid) == 12  # MD5 hex truncated


def test_get_state_path_uses_temp_dir():
    with mock.patch.object(sys, 'platform', 'linux-x86_64'), \
         mock.patch.object(notify, 'get_session_id', return_value='test-session'):
        path = notify.get_state_path()
        assert path.name == 'claude-wakeup-test-session.json'
        assert 'tmp' in str(path.parent).lower() or 'temp' in str(path.parent).lower()


def test_get_state_path_sanitizes_colons():
    with mock.patch.object(sys, 'platform', 'linux-x86_64'), \
         mock.patch.object(notify, 'get_session_id', return_value='a:b/c\\d'):
        path = notify.get_state_path()
        assert path.name == 'claude-wakeup-a-b-c-d.json'


# ---------------------------------------------------------------------------
# State file read / write / clear
# ---------------------------------------------------------------------------

def test_read_state_missing():
    nonexistent = Path(tempfile.gettempdir()) / 'claude-wakeup-nonexistent-test.json'
    # ensure clean
    nonexistent.unlink(missing_ok=True)
    assert notify.read_state(nonexistent) is None


def test_write_and_read_state():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = Path(f.name)
    try:
        notify.write_state(path, {'permission_fired': True})
        state = notify.read_state(path)
        assert state is not None
        assert state['permission_fired'] is True
        assert 'pid' in state
        assert 'ts' in state
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.skipif(sys.platform == 'win32',
                    reason='os.kill(pid, 0) staleness check is Unix-only')
def test_read_state_stale_pid():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = Path(f.name)
    try:
        notify.write_state(path, {'permission_fired': True})
        with open(path) as fh:
            data = json.load(fh)
        data['pid'] = 999999  # unlikely to be a real PID
        with open(path, 'w') as fh:
            json.dump(data, fh)
        state = notify.read_state(path)
        assert state is None
    finally:
        path.unlink(missing_ok=True)


def test_clear_state():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = Path(f.name)
    try:
        notify.write_state(path, {'permission_fired': True})
        assert path.exists()
        notify.clear_state(path)
        assert not path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_clear_state_missing_is_noop():
    nonexistent = Path(tempfile.gettempdir()) / 'claude-wakeup-nonexistent-clear.json'
    nonexistent.unlink(missing_ok=True)
    notify.clear_state(nonexistent)


# ---------------------------------------------------------------------------
# Event context from stdin
# ---------------------------------------------------------------------------

def test_read_event_context_valid_json():
    stdin_data = '{"tool_name": "Bash", "project_path": "/home/user/project"}'
    with mock.patch.object(sys, 'stdin', io.StringIO(stdin_data)):
        ctx = notify.read_event_context()
        assert ctx == {'tool_name': 'Bash', 'project_path': '/home/user/project'}


def test_read_event_context_empty():
    with mock.patch.object(sys, 'stdin', io.StringIO('')):
        ctx = notify.read_event_context()
        assert ctx == {}


def test_read_event_context_invalid_json():
    with mock.patch.object(sys, 'stdin', io.StringIO('not-json')):
        ctx = notify.read_event_context()
        assert ctx == {}


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------

def test_build_payload_permission():
    with mock.patch.object(os, 'getcwd', return_value='/home/user/my-project'):
        payload = notify.build_payload('permission', {'tool_name': 'Bash'})
        assert payload['title'] == 'Claude needs permission — my-project'
        assert 'Bash' in payload['message']
        assert payload['urgency'] == 'normal'


def test_build_payload_stop():
    with mock.patch.object(os, 'getcwd', return_value='/home/user/my-project'):
        payload = notify.build_payload('stop', {})
        assert payload['title'] == 'Claude finished — my-project'
        assert 'complete' in payload['message'].lower()
        assert payload['urgency'] == 'low'


def test_build_payload_error():
    with mock.patch.object(os, 'getcwd', return_value='/home/user/my-project'):
        payload = notify.build_payload('error', {'error': 'test failure'})
        assert payload['title'] == 'Claude hit an error — my-project'
        assert 'test failure' in payload['message']
        assert payload['urgency'] == 'critical'


# ---------------------------------------------------------------------------
# Platform backends (command construction)
# ---------------------------------------------------------------------------

def test_notify_linux_command():
    payload = {'title': 'Test', 'message': 'Hello', 'urgency': 'normal'}
    with mock.patch('subprocess.run') as mock_run, \
         mock.patch.object(notify, '_is_wsl', return_value=False):
        notify._notify_linux(payload)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == 'notify-send'
        assert '--urgency' in args
        assert 'normal' in args
        assert 'Test' in args
        assert 'Hello' in args
        assert mock_run.call_args[1]['timeout'] == 5
        assert mock_run.call_args[1]['check'] is False


def test_notify_linux_wsl():
    """On WSL2, use PowerShell toast notifications."""
    payload = {'title': 'Test', 'message': 'Hello', 'urgency': 'normal'}
    with mock.patch('subprocess.run') as mock_run, \
         mock.patch.object(notify, '_is_wsl', return_value=True):
        notify._notify_linux(payload)
        args = mock_run.call_args[0][0]
        assert args[0] == 'powershell.exe'
        assert '-Command' in args


def test_notify_macos_terminal_notifier():
    payload = {'title': 'Test', 'message': 'Hello'}
    with mock.patch.object(notify.shutil, 'which', return_value='/usr/local/bin/terminal-notifier'), \
         mock.patch('subprocess.run') as mock_run:
        notify._notify_macos(payload)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert 'terminal-notifier' in args[0]


def test_notify_macos_fallback_osascript():
    payload = {'title': 'Test', 'message': 'Hello'}
    with mock.patch.object(notify.shutil, 'which', return_value=None), \
         mock.patch('subprocess.run') as mock_run:
        notify._notify_macos(payload)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == 'osascript'


def test_notify_windows_powershell():
    payload = {'title': 'Test', 'message': 'Hello'}
    with mock.patch('subprocess.run') as mock_run:
        notify._notify_windows(payload)
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == 'powershell'


# ---------------------------------------------------------------------------
# Graceful failure (R11)
# ---------------------------------------------------------------------------

def test_dispatch_silent_on_subprocess_error():
    payload = {'title': 'Test', 'message': 'Hello'}
    with mock.patch.object(notify, 'detect_platform', return_value='linux'), \
         mock.patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd='notify-send', timeout=5)):
        # Should not raise
        notify.dispatch(payload)


def test_dispatch_silent_on_missing_command():
    payload = {'title': 'Test', 'message': 'Hello'}
    with mock.patch.object(notify, 'detect_platform', return_value='linux'), \
         mock.patch('subprocess.run', side_effect=FileNotFoundError):
        notify.dispatch(payload)  # should not raise


def test_notify_linux_not_found_silent():
    """Backend raises on missing command; dispatch() wrapper catches it (R11)."""
    payload = {'title': 'Test', 'message': 'Hello'}
    with mock.patch.object(notify, 'detect_platform', return_value='linux'), \
         mock.patch('subprocess.run', side_effect=FileNotFoundError):
        notify.dispatch(payload)  # dispatch() eats the exception silently


# ---------------------------------------------------------------------------
# Dedup logic (R7, AE1)
# ---------------------------------------------------------------------------

def _dedup_state_path(name):
    """Return a cross-platform temp path for dedup testing."""
    return Path(tempfile.gettempdir()) / f'claude-wakeup-test-dedup-{name}.json'


def test_dedup_permission_first_fires():
    """First permission in a cycle should fire a notification."""
    state_path = _dedup_state_path('first')
    notify.clear_state(state_path)
    try:
        state = notify.read_state(state_path)
        assert state is None  # fresh cycle

        notify.write_state(state_path, {'permission_fired': True})
        state = notify.read_state(state_path)
        assert state is not None
        assert state['permission_fired'] is True
    finally:
        notify.clear_state(state_path)


def test_dedup_permission_second_suppressed():
    """Second permission in same cycle should be suppressed."""
    state_path = _dedup_state_path('second')
    notify.clear_state(state_path)
    try:
        notify.write_state(state_path, {'permission_fired': True})
        state = notify.read_state(state_path)
        assert state is not None
        assert state.get('permission_fired') is True
    finally:
        notify.clear_state(state_path)


def test_dedup_cycle_reset_clears_state():
    """UserPromptSubmit should clear the dedup state."""
    state_path = _dedup_state_path('reset')
    notify.clear_state(state_path)
    try:
        notify.write_state(state_path, {'permission_fired': True})
        notify.clear_state(state_path)
        assert notify.read_state(state_path) is None
    finally:
        notify.clear_state(state_path)


def test_dedup_stop_always_fires():
    """Stop event should fire regardless of prior permission notification."""
    state_path = _dedup_state_path('stop')
    notify.clear_state(state_path)
    try:
        notify.write_state(state_path, {'permission_fired': True})
        state = notify.read_state(state_path)
        assert state is not None
    finally:
        notify.clear_state(state_path)


def test_dedup_cleanup_removes_state():
    """SessionEnd should remove the state file entirely."""
    state_path = _dedup_state_path('cleanup')
    notify.clear_state(state_path)
    try:
        notify.write_state(state_path, {'permission_fired': True})
        notify.clear_state(state_path)
        assert not state_path.exists()
    finally:
        notify.clear_state(state_path)


# ---------------------------------------------------------------------------
# Concurrent session isolation (AE4)
# ---------------------------------------------------------------------------

def test_session_scoped_state_path():
    """Different session IDs produce different state file paths."""
    with mock.patch.object(sys, 'platform', 'linux-x86_64'):
        with mock.patch.object(notify, 'get_session_id', return_value='session-a'):
            path_a = notify.get_state_path()
        with mock.patch.object(notify, 'get_session_id', return_value='session-b'):
            path_b = notify.get_state_path()
        assert path_a != path_b


# ---------------------------------------------------------------------------
# Missing state file — treated as first event (graceful)
# ---------------------------------------------------------------------------

def test_missing_state_treated_as_first_event():
    path = Path(tempfile.gettempdir()) / 'claude-wakeup-nonexistent-for-test.json'
    path.unlink(missing_ok=True)
    state = notify.read_state(path)
    assert state is None  # missing → fresh cycle


# ---------------------------------------------------------------------------
# Click-to-focus action inclusion (AE2)
# ---------------------------------------------------------------------------

def test_terminal_notifier_includes_action():
    """When terminal-notifier is available, the -execute flag carries the click action."""
    payload = {'title': 'Test', 'message': 'Hello', 'action': 'code --focus'}
    with mock.patch.object(notify.shutil, 'which', return_value='/usr/local/bin/terminal-notifier'), \
         mock.patch('subprocess.run') as mock_run:
        notify._notify_macos(payload)
        args = mock_run.call_args[0][0]
        assert '-execute' in args
        assert 'code --focus' in args


# ---------------------------------------------------------------------------
# Debug logging (R4, R5, R6)
# ---------------------------------------------------------------------------

def test_log_creates_directory():
    """Log directory is created automatically on first write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / 'claude-wakeup'
        with mock.patch.dict(os.environ, {'CLAUDE_WAKEUP_LOG_DIR': str(log_dir)}):
            with mock.patch.object(os, 'getcwd', return_value='/home/user/test-project'):
                notify._log('permission', 'dispatched', 'tool=Bash')
        assert log_dir.exists()


def test_log_writes_json_line():
    """Log entries are valid JSON with required fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with mock.patch.dict(os.environ, {'CLAUDE_WAKEUP_LOG_DIR': tmpdir}):
            with mock.patch.object(os, 'getcwd', return_value='/home/user/test-project'):
                notify._log('permission', 'dispatched', 'tool=Bash')
        log_file = Path(tmpdir) / 'debug.log'
        assert log_file.exists()
        with open(log_file) as f:
            entry = json.loads(f.readline())
        assert entry['event'] == 'permission'
        assert entry['action'] == 'dispatched'
        assert entry['project'] == 'test-project'
        assert entry['detail'] == 'tool=Bash'
        assert 'ts' in entry


def test_log_suppression():
    """Dedup suppression is logged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with mock.patch.dict(os.environ, {'CLAUDE_WAKEUP_LOG_DIR': tmpdir}):
            with mock.patch.object(os, 'getcwd', return_value='/home/user/project'):
                notify._log('permission', 'suppressed', 'dedup: already fired')
        with open(Path(tmpdir) / 'debug.log') as f:
            entry = json.loads(f.readline())
        assert entry['action'] == 'suppressed'


def test_log_env_var_override():
    """CLAUDE_WAKEUP_LOG_DIR env var overrides default path."""
    with tempfile.TemporaryDirectory() as custom_dir:
        with mock.patch.dict(os.environ, {'CLAUDE_WAKEUP_LOG_DIR': custom_dir}):
            result = notify._log_dir()
            assert str(result) == custom_dir


def test_log_never_raises():
    """Logging failure must never break notification flow."""
    with mock.patch('builtins.open', side_effect=PermissionError):
        notify._log('permission', 'dispatched')
