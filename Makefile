.PHONY: install test lint clean

VENV := plugin/.venv
PIP   := $(VENV)/bin/pip
PYTHON := $(VENV)/bin/python

$(VENV):
	@python3 -m venv $(VENV)
	@$(PIP) install --upgrade pip -q
	@$(PIP) install -r plugin/requirements.txt -q

install: $(VENV)
	@echo "Claude Wakeup install options:"
	@echo ""
	@echo "  Recommended: /plugin marketplace add EmberPhoenixForge/claude-wakeup"
	@echo "              /plugin install claude-wakeup"
	@echo ""
	@echo "  Manual:     cp -r plugin/ $$HOME/.claude/plugins/claude-wakeup"
	@echo ""
	@echo "See README.md for setup details."

test: $(VENV)
	@echo "Running tests..."
	@$(PYTHON) -m pytest plugin/tests/ -v
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck plugin/hooks/notify.sh; \
	else \
		echo "shellcheck not found — skipping (install: apt install shellcheck)"; \
	fi

lint: $(VENV)
	@echo "Linting..."
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck plugin/hooks/notify.sh || true; \
	fi
	@$(PYTHON) -m py_compile plugin/notify.py && echo "notify.py: OK"

clean:
	@echo "Cleaning..."
	@rm -rf plugin/__pycache__ plugin/.pytest_cache plugin/tests/__pycache__ $(VENV)
