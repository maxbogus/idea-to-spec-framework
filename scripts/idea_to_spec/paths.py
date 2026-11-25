"""Пути репозитория и константы eval-обвязки idea-to-spec-ai.

Единая точка правды по расположению промптов, кейсов и отчётов. Тесты
импортируют константы отсюда, чтобы пути не дублировались по файлам.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

OUTPUT_DIR = REPO_ROOT / "output"

PROMPTS_DIR = REPO_ROOT / "prompts"
ROLES_DIR = PROMPTS_DIR / "roles"
SUBAGENTS_DIR = REPO_ROOT / "subagents"
RULES_FILE = PROMPTS_DIR / "rules.md"

EVAL_DIR = REPO_ROOT / "eval"
EVAL_CONFIG_FILE = EVAL_DIR / "promptfooconfig.yaml"
EVAL_MOCK_CONFIG_FILE = EVAL_DIR / "promptfooconfig.mock.yaml"
EVAL_CASES_FILE = EVAL_DIR / "cases" / "roles.jsonl"

DOCS_EVALUATION_DIR = REPO_ROOT / "docs" / "evaluation"
#: Имя файла отчёта реального прогона. Двоеточие в имени модели недопустимо
#: в путях, поэтому тег модели записывается через дефис: qwen3-8b.
EVAL_REPORT_FILE = DOCS_EVALUATION_DIR / "eval-qwen3-8b.json"
