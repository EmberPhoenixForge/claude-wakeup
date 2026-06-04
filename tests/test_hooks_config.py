"""Validate hooks.json structure against the Claude Code hook spec."""

import json
import sys
from pathlib import Path

# Valid hook event names per Claude Code plugin spec (docs/specs/claude-code.md)
VALID_EVENTS = {
    'PreToolUse', 'PostToolUse', 'PostToolUseFailure',
    'PermissionRequest', 'UserPromptSubmit',
    'Notification', 'Stop',
    'SubagentStart', 'SubagentStop',
    'Setup', 'SessionStart', 'SessionEnd', 'PreCompact',
}

REQUIRED_HOOK_FIELDS = {'type', 'command', 'timeout'}
VALID_HOOK_TYPES = {'command', 'prompt', 'agent'}


def load_hooks_json():
    """Load and return the hooks.json file."""
    hooks_path = Path(__file__).resolve().parent.parent / 'hooks' / 'hooks.json'
    if not hooks_path.exists():
        print(f'FAIL: hooks.json not found at {hooks_path}')
        sys.exit(1)
    with open(hooks_path) as f:
        return json.load(f)


def test_all_event_names_valid():
    """Every top-level key in hooks.json must be a valid Claude Code hook event."""
    hooks = load_hooks_json()
    for event_name in hooks:
        assert event_name in VALID_EVENTS, \
            f'Unknown hook event: "{event_name}". Valid events: {sorted(VALID_EVENTS)}'
    print(f'OK: {len(hooks)} hook events, all valid')


def test_required_events_present():
    """The five events claude-wakeup depends on must be wired."""
    hooks = load_hooks_json()
    required = {'PermissionRequest', 'Stop', 'PostToolUseFailure',
                'UserPromptSubmit', 'SessionEnd'}
    missing = required - set(hooks.keys())
    assert not missing, f'Missing required hook events: {missing}'
    print(f'OK: all {len(required)} required events present')


def test_matcher_format():
    """Each event has a matcher dict (empty string key for catch-all)."""
    hooks = load_hooks_json()
    for event_name, matchers in hooks.items():
        assert isinstance(matchers, dict), \
            f'{event_name}: matchers must be a dict, got {type(matchers).__name__}'
        # At least one matcher entry
        assert len(matchers) > 0, f'{event_name}: no matchers defined'
        for matcher_key, hook_list in matchers.items():
            assert isinstance(hook_list, list), \
                f'{event_name}["{matcher_key}"]: must be a list of hook entries'


def test_hook_entries_have_required_fields():
    """Every hook entry must have type, command, and timeout."""
    hooks = load_hooks_json()
    for event_name, matchers in hooks.items():
        for matcher_key, hook_list in matchers.items():
            for i, entry in enumerate(hook_list):
                missing = REQUIRED_HOOK_FIELDS - set(entry.keys())
                assert not missing, \
                    f'{event_name}["{matcher_key}"][{i}]: missing fields: {missing}'
                assert entry['type'] in VALID_HOOK_TYPES, \
                    f'{event_name}["{matcher_key}"][{i}]: invalid type "{entry["type"]}"'
                assert isinstance(entry['timeout'], (int, float)), \
                    f'{event_name}["{matcher_key}"][{i}]: timeout must be a number'
                assert entry['timeout'] > 0, \
                    f'{event_name}["{matcher_key}"][{i}]: timeout must be positive'


def test_commands_reference_plugin_root():
    """Every hook command must reference ${CLAUDE_PLUGIN_ROOT}."""
    hooks = load_hooks_json()
    for event_name, matchers in hooks.items():
        for matcher_key, hook_list in matchers.items():
            for i, entry in enumerate(hook_list):
                cmd = entry.get('command', '')
                assert '${CLAUDE_PLUGIN_ROOT}' in cmd, \
                    f'{event_name}["{matcher_key}"][{i}]: command must use ${{CLAUDE_PLUGIN_ROOT}}'


def test_event_mapping_consistency():
    """Event names in hooks.json match the argv[1] values notify.sh expects."""
    hooks = load_hooks_json()
    # The hooks.json commands pass these argv[1] values:
    # permission, stop, error, cycle-reset, cleanup
    # They should match the event they're wired to.
    expected_arg = {
        'PermissionRequest': 'permission',
        'Stop': 'stop',
        'PostToolUseFailure': 'error',
        'UserPromptSubmit': 'cycle-reset',
        'SessionEnd': 'cleanup',
    }
    for event_name, matchers in hooks.items():
        expected = expected_arg.get(event_name)
        if expected is None:
            continue  # unknown event, already caught by test_all_event_names_valid
        for hook_list in matchers.values():
            for entry in hook_list:
                cmd = entry['command']
                assert expected in cmd, \
                    f'{event_name}: command should pass "{expected}" as argv[1], got: {cmd}'


if __name__ == '__main__':
    test_all_event_names_valid()
    test_required_events_present()
    test_matcher_format()
    test_hook_entries_have_required_fields()
    test_commands_reference_plugin_root()
    test_event_mapping_consistency()
    print('\nAll hooks.json validations passed.')
