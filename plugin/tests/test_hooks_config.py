"""Validate hooks.json structure against the Claude Code hook spec."""

import json
import sys
from pathlib import Path

# Valid hook event names per Claude Code plugin spec
VALID_EVENTS = {
    'PreToolUse', 'PostToolUse', 'PostToolUseFailure',
    'PermissionRequest', 'UserPromptSubmit',
    'Notification', 'Stop',
    'SubagentStart', 'SubagentStop',
    'Setup', 'SessionStart', 'SessionEnd', 'PreCompact',
}

REQUIRED_HOOK_FIELDS = {'type', 'command', 'timeout'}
VALID_HOOK_TYPES = {'command', 'prompt', 'agent'}


def load_hooks():
    """Load hooks.json and return the inner hooks object."""
    hooks_path = Path(__file__).resolve().parent.parent / 'hooks' / 'hooks.json'
    if not hooks_path.exists():
        print(f'FAIL: hooks.json not found at {hooks_path}')
        sys.exit(1)
    with open(hooks_path) as f:
        data = json.load(f)
    if 'hooks' not in data:
        print('FAIL: hooks.json missing top-level "hooks" key')
        sys.exit(1)
    return data['hooks']


def _all_entries(hooks):
    """Yield every (event_name, group, entry) triple from hooks."""
    for event_name, groups in hooks.items():
        for group in groups:
            for entry in group.get('hooks', []):
                yield event_name, group, entry


def test_all_event_names_valid():
    """Every top-level key must be a valid Claude Code hook event."""
    hooks = load_hooks()
    for event_name in hooks:
        assert event_name in VALID_EVENTS, \
            f'Unknown hook event: "{event_name}". Valid events: {sorted(VALID_EVENTS)}'
    print(f'OK: {len(hooks)} hook events, all valid')


def test_required_events_present():
    """The six events claude-wakeup depends on must be wired."""
    hooks = load_hooks()
    required = {'Notification', 'PermissionRequest', 'Stop',
                'PostToolUseFailure', 'UserPromptSubmit', 'SessionEnd'}
    missing = required - set(hooks.keys())
    assert not missing, f'Missing required hook events: {missing}'
    print(f'OK: all {len(required)} required events present')


def test_events_are_arrays_of_groups():
    """Each event must map to an array of hook group objects."""
    hooks = load_hooks()
    for event_name, groups in hooks.items():
        assert isinstance(groups, list), \
            f'{event_name}: must be an array, got {type(groups).__name__}'
        assert len(groups) > 0, f'{event_name}: no hook groups defined'
        for i, group in enumerate(groups):
            assert isinstance(group, dict), \
                f'{event_name}[{i}]: group must be an object'
            assert 'hooks' in group, \
                f'{event_name}[{i}]: group missing "hooks" array'


def test_hook_entries_have_required_fields():
    """Every hook entry must have type, command, and timeout."""
    for event_name, group, entry in _all_entries(load_hooks()):
        missing = REQUIRED_HOOK_FIELDS - set(entry.keys())
        assert not missing, \
            f'{event_name}: entry missing fields: {missing}'
        assert entry['type'] in VALID_HOOK_TYPES, \
            f'{event_name}: invalid type "{entry["type"]}"'
        assert isinstance(entry['timeout'], (int, float)), \
            f'{event_name}: timeout must be a number'
        assert entry['timeout'] > 0, \
            f'{event_name}: timeout must be positive'


def test_commands_reference_plugin_root():
    """Every hook command must reference ${CLAUDE_PLUGIN_ROOT}."""
    for event_name, group, entry in _all_entries(load_hooks()):
        cmd = entry.get('command', '')
        assert '${CLAUDE_PLUGIN_ROOT}' in cmd, \
            f'{event_name}: command must use ${{CLAUDE_PLUGIN_ROOT}}'


def test_event_mapping_consistency():
    """Commands must pass the expected argv[1] for their event."""
    hooks = load_hooks()
    expected_arg = {
        'Notification': None,  # checked by matcher below
        'PermissionRequest': 'permission',
        'Stop': 'stop',
        'PostToolUseFailure': 'error',
        'UserPromptSubmit': 'cycle-reset',
        'SessionEnd': 'cleanup',
    }
    for event_name, groups in hooks.items():
        expected = expected_arg.get(event_name)
        if expected is None:
            continue  # Notification checked separately, unknown caught earlier
        for group in groups:
            for entry in group.get('hooks', []):
                cmd = entry['command']
                assert expected in cmd, \
                    f'{event_name}: command should pass "{expected}" as argv[1], got: {cmd}'

    # Notification: permission_prompt → permission, idle_prompt → stop
    notif_groups = hooks.get('Notification', [])
    for group in notif_groups:
        matcher = group.get('matcher', '')
        for entry in group.get('hooks', []):
            cmd = entry['command']
            if matcher == 'permission_prompt':
                assert 'permission' in cmd, \
                    f'Notification/{matcher}: command should pass "permission", got: {cmd}'
            elif matcher == 'idle_prompt':
                assert 'stop' in cmd, \
                    f'Notification/{matcher}: command should pass "stop", got: {cmd}'


if __name__ == '__main__':
    test_all_event_names_valid()
    test_required_events_present()
    test_events_are_arrays_of_groups()
    test_hook_entries_have_required_fields()
    test_commands_reference_plugin_root()
    test_event_mapping_consistency()
    print('\nAll hooks.json validations passed.')
