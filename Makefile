SHELL := /bin/bash
.DEFAULT_GOAL := help

RUN ?= auto-001
OUT_ROOT ?= output
PACKS ?=
PROFILE ?=
STRICT ?=
MMDC ?= mmdc
MMDC_MIN ?= 12.0.0
MERMAID_CFG ?= templates/mermaid-config.json
SLIDES_BG ?= white
CONFIRM ?=
SCRIPTS := $(CURDIR)/scripts
OLLAMA_URL ?= http://localhost:11434
OLLAMA_MODEL ?= qwen3:8b
# Двоеточие в имени модели недопустимо в путях: qwen3:8b -> qwen3-8b.
OLLAMA_TAG ?= $(subst :,-,$(OLLAMA_MODEL))
# Трассировка вызова: метаданные Ollama (prompt_eval_count, eval_count,
# done_reason) и сырые дампы «промпт + ответ». Без них вытеснение контекста и
# битый JSON не воспроизвести: замер волны C («46 КБ -> 4096») остался только в
# рукописном журнале. Пути локальные и в .gitignore; переопределяются env.
EVAL_TRACE ?= docs/evaluation/traces/$(OLLAMA_TAG).jsonl
EVAL_RAW ?= docs/evaluation/raw/$(OLLAMA_TAG)
# promptfoo ставится локально (`make eval-setup`). Родительский каталог не
# используется: фреймворк переносится в чужой проект как самостоятельный.
PROMPTFOO ?= $(CURDIR)/node_modules/.bin/promptfoo
# Интерпретатор Python переопределяем: в Windows его обычно вызывают `python`.
PYTHON ?= python3

.PHONY: help setup check-prereqs scaffold scaffold-full scaffold-all render render-all check check-refs check-fences check-diagrams check-bpmn check-sync check-skills skills-index check-gates gates-index check-gate check-public check-ledger check-cross-refs check-eval-report check-run check-runs check-policy check-dor check-dor-runs list-runs analytics clean-png clean-run start eval-setup check-promptfoo eval eval-target eval-compare eval-mock test-eval lint-py

help: ## Показать список целей
	@echo "Использование: make <target> [RUN=<id>]"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'
	@echo ""
	@echo "Переменные: RUN=$(RUN) OUT_ROOT=$(OUT_ROOT)"

setup: check-prereqs ## Первичная настройка: проверить окружение (node, mmdc, make, uv, git, python)

check-prereqs: ## Проверить node, mmdc >= MMDC_MIN, make, uv, git, python
	@PYTHON="$(PYTHON)" MMDC_MIN="$(MMDC_MIN)" bash $(SCRIPTS)/check-prereqs.sh

scaffold: ## Развернуть каркас прогона: make scaffold RUN=auto-002 (FULL=1 — все диаграммы, PACKS=data,ai — паки)
	@bash $(SCRIPTS)/scaffold-run.sh "$(RUN)" "$(if $(FULL),full,base)" "$(PACKS)" "$(OUT_ROOT)"

scaffold-full: ## Развернуть каркас прогона со всеми диаграммами: make scaffold-full RUN=auto-002
	@bash $(SCRIPTS)/scaffold-run.sh "$(RUN)" full "" "$(OUT_ROOT)"

scaffold-all: ## Каркас + расширенные диаграммы + все паки: make scaffold-all RUN=demo-all
	@bash $(SCRIPTS)/scaffold-run.sh "$(RUN)" all "" "$(OUT_ROOT)"

render: ## Отрендерить .mmd -> .png: make render RUN=auto-001
	@bash $(SCRIPTS)/render-diagrams.sh "$(OUT_ROOT)/$(RUN)/diagrams" "$(MERMAID_CFG)"

render-all: ## Отрендерить диаграммы всех прогонов
	@shopt -s nullglob; \
	found=0; \
	for d in $(OUT_ROOT)/*/diagrams; do \
	  if compgen -G "$$d/*.mmd" >/dev/null; then \
	    echo "== $$d"; \
	    bash $(SCRIPTS)/render-diagrams.sh "$$d" "$(MERMAID_CFG)"; \
	    found=1; \
	  fi; \
	done; \
	if [ $$found -eq 0 ]; then echo "Нет прогонов с диаграммами в $(OUT_ROOT)/"; fi

check: check-prereqs check-refs check-fences check-diagrams check-bpmn check-sync check-skills check-gates check-public check-ledger check-cross-refs check-eval-report check-runs check-dor-runs ## Полная проверка раздатки и диаграмм

check-refs: ## Проверить, что все ссылки на md/mmd резолвятся
	@ok=1; \
	for ref in $$(grep -rhoE '(prompts|methods|skills|subagents|templates)(/[a-zA-Z0-9_*.-]+)*/[a-zA-Z0-9_*.-]+\.(md|mmd|bpmn|json|jsonl)' . --include='*.md' --include='*.mmd' --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.git | sort -u); do \
	  case "$$ref" in *'*'*) continue;; esac; \
	  if [ ! -f "$$ref" ]; then echo "MISSING: $$ref"; ok=0; fi; \
	done; \
	if [ $$ok -eq 1 ]; then echo "check-refs: OK"; else echo "check-refs: FAILED" >&2; exit 1; fi

check-fences: ## Проверить парность ``` во всех .md
	@ok=1; \
	for f in $$(find . -name '*.md' -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*'); do \
	  n=$$(grep -c '^```' "$$f" || true); \
	  if [ $$((n % 2)) -ne 0 ]; then echo "ODD FENCE: $$f ($$n)"; ok=0; fi; \
	done; \
	if [ $$ok -eq 1 ]; then echo "check-fences: OK"; else echo "check-fences: FAILED" >&2; exit 1; fi

check-diagrams: ## Проверить синтаксис всех .mmd рендером в temp
	@command -v $(MMDC) >/dev/null 2>&1 || { echo "ERROR: $(MMDC) не найден (npm i -g @mermaid-js/mermaid-cli)" >&2; exit 1; }; \
	tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT; \
	ok=1; \
	for f in $$(find . -name '*.mmd' -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*'); do \
	  name=$$(echo "$$f" | tr '/' '_'); \
	  if $(MMDC) -i "$$f" -o "$$tmp/$${name%.mmd}.png" -b white >/dev/null 2>&1; then \
	    echo "diagram OK: $$f"; \
	  else echo "diagram FAIL: $$f"; ok=0; fi; \
	done; \
	if [ $$ok -eq 1 ]; then echo "check-diagrams: OK"; else echo "check-diagrams: FAILED" >&2; exit 1; fi

check-bpmn: ## Проверить, что .bpmn — well-formed XML
	@ok=1; \
	found=0; \
	for f in $$(find . -name '*.bpmn' -not -path './.git/*' -not -path './node_modules/*' -not -path './.venv/*'); do \
	  found=1; \
	  if $(PYTHON) -c "import sys, xml.etree.ElementTree as ET; ET.parse(sys.argv[1])" "$$f" 2>/dev/null; then \
	    echo "bpmn OK: $$f"; \
	  else echo "bpmn FAIL: $$f"; ok=0; fi; \
	done; \
	if [ $$found -eq 0 ]; then echo "check-bpmn: нет .bpmn"; exit 0; fi; \
	if [ $$ok -eq 1 ]; then echo "check-bpmn: OK"; else echo "check-bpmn: FAILED" >&2; exit 1; fi

check-sync: ## Проверить, что скилы/шаблоны/скрипты используются и режимы описаны
	@bash $(SCRIPTS)/check-sync.sh

check-cross-refs: ## Проверить согласованность идентификаторов в схемах ролей
	@uv run python scripts/check_cross_refs.py

check-ledger: ## Проверить формат ledger (prompts/ledger/*.jsonl)
	@uv run python scripts/check_ledger.py

check-skills: ## Проверить реестр скилов и актуальность skills/INDEX.md
	@uv run python scripts/check_skills_registry.py
	@uv run python scripts/render_skills_index.py --check

check-gates: ## Проверить, что prompts/gate-checklists.md соответствует YAML
	@uv run python scripts/render_gate_checklists.py --check

gates-index: ## Перегенерировать prompts/gate-checklists.md из YAML
	@uv run python scripts/render_gate_checklists.py --write

check-gate: ## Проверить ответ гейта по чеклисту: make check-gate FILE=gate.json [GATE=BA-gate]
	@uv run python scripts/check_gate.py "$(FILE)" $(if $(GATE),--gate $(GATE),)

skills-index: ## Перегенерировать skills/INDEX.md из реестра и frontmatter
	@uv run python scripts/render_skills_index.py --write


check-public: ## Проверить публикуемость: нет личных путей, секретов и внешних зависимостей
	@$(PYTHON) $(SCRIPTS)/check_public.py --root $(CURDIR)

check-eval-report: ## Проверить, что отчёт прогона соответствует набору (human-review, не fail)
	@uv run python scripts/check_eval_report_fresh.py

check-run: ## Проверить согласованность прогона: make check-run RUN=auto-002
	@$(PYTHON) $(SCRIPTS)/check_run.py "$(OUT_ROOT)/$(RUN)"

check-policy: ## Проверить артефакты на PII/секреты (human-review, не fail)
	@$(PYTHON) $(SCRIPTS)/check_artifact_policy.py "$(OUT_ROOT)/$(RUN)"

check-dor: ## Полнота набора диаграмм: make check-dor RUN=auto-004 [PROFILE=full] [STRICT=1]
	@$(PYTHON) $(SCRIPTS)/check_dor.py "$(OUT_ROOT)/$(RUN)" $(if $(PROFILE),--profile $(PROFILE),) $(if $(STRICT),--strict,)

check-dor-runs: ## Полнота диаграмм всех прогонов (report-only)
	@runs=$$($(PYTHON) $(SCRIPTS)/list_runs.py "$(OUT_ROOT)") || exit 1; \
	for r in $$runs; do \
		$(PYTHON) $(SCRIPTS)/check_dor.py "$(OUT_ROOT)/$$r" 2>&1 | sed 's/^/  /' || true; \
	done; \
	true

# Какие прогоны проверять, решает scripts/list_runs.py: отслеживаемые git
# (свежий scaffold содержит placeholder-ID и по определению не проходит
# check_run), а если git не применим — каталоги с диска. Пустой результат —
# ошибка, а не тихий успех. check_artifact_policy.py гейт не роняет
# (находки -> human-review), поэтому его вывод не влияет на код возврата.
check-runs: ## Проверить согласованность всех прогонов (OUT_ROOT)
	@runs=$$($(PYTHON) $(SCRIPTS)/list_runs.py "$(OUT_ROOT)") || exit 1; \
	ok=1; \
	for r in $$runs; do \
		if $(PYTHON) $(SCRIPTS)/check_run.py "$(OUT_ROOT)/$$r" >/dev/null 2>&1; then \
			echo "run OK: $$r"; \
		else \
			echo "run FAIL: $$r"; \
			$(PYTHON) $(SCRIPTS)/check_run.py "$(OUT_ROOT)/$$r" 2>&1 | sed 's/^/    /'; \
			ok=0; \
		fi; \
		$(PYTHON) $(SCRIPTS)/check_artifact_policy.py "$(OUT_ROOT)/$$r" 2>&1 | sed 's/^/  /'; \
	done; \
	if [ $$ok -eq 1 ]; then echo "check-runs: OK"; else echo "check-runs: FAILED" >&2; exit 1; fi

list-runs: ## Список прогонов (OUT_ROOT)
	@$(PYTHON) $(SCRIPTS)/list_runs.py "$(OUT_ROOT)" 2>/dev/null || echo "нет прогонов"

analytics: ## Сводка метрик прогона: make analytics RUN=auto-002
	@$(PYTHON) $(SCRIPTS)/session_analytics.py "$(OUT_ROOT)/$(RUN)"

clean-png: ## Удалить отрендеренные PNG (source остаются)
	@shopt -s nullglob; \
	n=0; \
	for f in $(OUT_ROOT)/*/diagrams/*.png; do rm -f "$$f"; n=$$((n + 1)); done; \
	echo "clean-png: удалено $$n PNG"

clean-run: ## Удалить прогон (нужно CONFIRM=yes): make clean-run RUN=auto-002 CONFIRM=yes
	@if [ "$(CONFIRM)" != "yes" ]; then \
	  echo "Отказ. Предпросмотр: make -n clean-run RUN=$(RUN)"; \
	  echo "Затем: make clean-run RUN=$(RUN) CONFIRM=yes"; \
	  exit 1; \
	fi; \
	if [ -z "$(RUN)" ] || [ "$(RUN)" = "*" ] || [ "$(RUN)" = "/" ]; then \
	  echo "ERROR: укажи конкретный RUN" >&2; exit 1; \
	fi; \
	if [ ! -d "$(OUT_ROOT)/$(RUN)" ]; then \
	  echo "ERROR: нет $(OUT_ROOT)/$(RUN)" >&2; exit 1; \
	fi; \
	rm -rf "$(OUT_ROOT)/$(RUN)"; \
	echo "clean-run: удалён $(OUT_ROOT)/$(RUN)"

start: ## Показать стартовый промпт prompts/start.md
	@cat prompts/start.md

## Eval

eval-setup: ## Установить зависимости eval (uv sync + npm install)
	@uv sync --all-groups
	@npm install --no-audit --no-fund
	@echo "eval-setup: OK"

check-promptfoo: ## Проверить, что promptfoo установлен (make eval-setup)
	@test -e "$(PROMPTFOO)" || { \
		echo "ERROR: promptfoo не найден: $(PROMPTFOO)" >&2; \
		echo "Выполните: make eval-setup" >&2; \
		exit 1; \
	}

test-eval: ## Прогнать pytest eval-контракты без реальной модели
	@uv run pytest tests -q -m 'not slow'

eval-mock: check-promptfoo ## Детерминированный replay eval-кейсов без LLM (зелёный в CI)
	@echo "==> pytest-контракты (mock)"
	@uv run pytest tests -q -m mock
	@echo "==> promptfoo replay (exec-провайдер, без сети)"
	@uv run python scripts/make_eval_config.py --template eval/promptfooconfig.mock.yaml \
		--out $(CURDIR)/.eval-config-mock.yaml
	@$(PROMPTFOO) eval -c .eval-config-mock.yaml --no-cache --no-progress-bar 2>&1 | tail -5
	@rm -f .eval-config-mock.yaml

# Целевой замер: гоняет только подмножество кейсов, заданное фильтром
# promptfoo. Правило владельца (2026-11-24): измеряем только то, что
# оптимизируем, а не весь набор. Фильтр — регулярное выражение по полю
# metadata кейса (например, "mode=chat" или "scenario=ORCH").
#
# Отчёт пишется в docs/evaluation/eval-<тег>.local.json — путь уже в
# .gitignore, поэтому частичный замер не перезаписывает базовый отчёт
# eval-<тег>.json и не попадает в git.
eval-target: check-promptfoo ## Целевой замер подмножества кейсов (make eval-target FILTER="mode=chat")
	@test -n "$(FILTER)" || { echo "[FAIL] задайте FILTER, например FILTER=\"mode=chat\""; exit 1; }
	@curl -sf $(OLLAMA_URL)/api/tags > /dev/null || { \
		echo "[FAIL] Ollama недоступен на $(OLLAMA_URL)"; exit 1; }
	@echo "==> promptfoo против $(OLLAMA_MODEL), фильтр: $(FILTER)"
	@uv run python scripts/make_eval_config.py --model $(OLLAMA_MODEL) \
		--out $(CURDIR)/.eval-config-$(OLLAMA_TAG).yaml
	@ITSF_TRACE="$(EVAL_TRACE)" ITSF_RAW_DIR="$(EVAL_RAW)" \
		$(PROMPTFOO) eval -c .eval-config-$(OLLAMA_TAG).yaml --no-cache --no-progress-bar \
		--filter-metadata "$(FILTER)" \
		-o docs/evaluation/eval-$(OLLAMA_TAG).local.json 2>&1 | tail -8 || true
	@uv run python scripts/summarize_eval.py docs/evaluation/eval-$(OLLAMA_TAG).local.json
	@echo "trace: $(EVAL_TRACE) | raw: $(EVAL_RAW)"
	@rm -f .eval-config-$(OLLAMA_TAG).yaml

eval: check-promptfoo ## Прогнать eval-кейсы на локальной модели Ollama (make eval OLLAMA_MODEL=qwen3:8b)
	@curl -sf $(OLLAMA_URL)/api/tags > /dev/null || { \
		echo "[FAIL] Ollama недоступен на $(OLLAMA_URL)"; exit 1; }
	@echo "==> promptfoo против $(OLLAMA_MODEL)"
	@mkdir -p docs/evaluation
	@uv run python scripts/make_eval_config.py --model $(OLLAMA_MODEL) \
		--out $(CURDIR)/.eval-config-$(OLLAMA_TAG).yaml
	@ITSF_TRACE="$(EVAL_TRACE)" ITSF_RAW_DIR="$(EVAL_RAW)" \
		$(PROMPTFOO) eval -c .eval-config-$(OLLAMA_TAG).yaml --no-cache --no-progress-bar \
		-o docs/evaluation/eval-$(OLLAMA_TAG).json 2>&1 | tail -8 || true
	@uv run python scripts/summarize_eval.py docs/evaluation/eval-$(OLLAMA_TAG).json
	@echo "trace: $(EVAL_TRACE) | raw: $(EVAL_RAW)"
	@rm -f .eval-config-$(OLLAMA_TAG).yaml

eval-compare: ## Сравнить модели на eval-кейсах (make eval-compare MODELS="qwen3:8b qwen2.5:7b")
	@for m in $(MODELS); do \
		echo "=== $$m ==="; \
		$(MAKE) --no-print-directory eval OLLAMA_MODEL=$$m; \
	done

lint-py: ## Линтинг Python eval-обвязки и пакета: ruff + mypy
	@uv run ruff check scripts tests idea_to_spec_framework.py
	@uv run mypy scripts tests idea_to_spec_framework.py
