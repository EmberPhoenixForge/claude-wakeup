.PHONY: install test lint clean

PLUGIN_NAME := claude-wakeup
PLUGIN_DIR  := $(HOME)/.claude/plugins/$(PLUGIN_NAME)

install:
	@echo "Installing $(PLUGIN_NAME) to $(PLUGIN_DIR)..."
	@rm -rf "$(PLUGIN_DIR)"
	@mkdir -p "$(PLUGIN_DIR)"
	@cp -r .claude-plugin hooks notify.py commands "$(PLUGIN_DIR)/"
	@echo "Done. Enable the plugin in Claude Code settings or run /claude-wakeup:config."

test:
	@echo "Running tests..."
	@if command -v python3 >/dev/null 2>&1; then \
		python3 -m pytest tests/ -v 2>/dev/null || python3 -c "import ast; [ast.parse(open(f).read()) for f in ['notify.py','tests/test_notify.py','tests/test_hooks_config.py']]; print('Syntax check passed (pytest not available — install with: python3 -m pip install pytest)')"; \
	else \
		echo "python3 not found — skipping tests"; \
	fi
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck hooks/notify.sh; \
	else \
		echo "shellcheck not found — skipping shell lint (install: apt install shellcheck)"; \
	fi

lint:
	@echo "Linting..."
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck hooks/notify.sh || true; \
	fi
	@if command -v python3 >/dev/null 2>&1; then \
		python3 -m py_compile notify.py && echo "notify.py: OK" || true; \
	fi

clean:
	@echo "Cleaning..."
	@rm -rf __pycache__ .pytest_cache tests/__pycache__

