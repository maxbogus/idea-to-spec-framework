"""Трансформ переменных promptfoo: собирает промпт роли из файлов-источников.

Зачем. Каждый кейс `eval/cases/roles.jsonl` хранит контракт одной JSON-строкой
в переменной `contract`. Но шаблон промпта читает отдельные переменные:
`role_prompt`, `rules`, `input`, `mode`, `role`. Этот модуль — `transformVars`:
promptfoo вызывает его перед рендером промпта и подмешивает результат в `vars`.

Тексты промптов не дублируются в eval-конфиге: `role_prompt` читается из
`prompts/roles/<role>.md` (или `prompts/orchestrator.md`, `subagents/fact-check.md`,
`subagents/requirements-critic.md`),
`rules` — из `prompts/rules.md`. Это единый source of truth: правим промпт —
eval проверяет уже новую версию.

Подключение в `eval/promptfooconfig*.yaml`:

    defaultTest:
      options:
        transformVars: file://../scripts/promptfoo_transform.py

promptfoo ищет функцию `get_transform` и передаёт ей `(vars, context)`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Пути считаются от самого файла, а не импортом пакета: promptfoo загружает
# модуль напрямую, и `scripts/` не обязан быть в sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROMPTS_DIR = _REPO_ROOT / "prompts"
_ROLES_DIR = _PROMPTS_DIR / "roles"
_RULES_FILE = _PROMPTS_DIR / "rules.md"
_SUBAGENTS_DIR = _REPO_ROOT / "subagents"

#: Роли, чьи промпты лежат не в `prompts/roles/`.
_SPECIAL_ROLE_FILES = {
    "orchestrator": _PROMPTS_DIR / "orchestrator.md",
    "fact-check": _SUBAGENTS_DIR / "fact-check.md",
    "critic": _SUBAGENTS_DIR / "requirements-critic.md",
}


def _contract(vars_block: dict[str, Any]) -> dict[str, Any]:
    """Извлечь контракт кейса из переменной `contract`.

    Args:
        vars_block: Переменные тест-кейса.

    Returns:
        Словарь контракта (пустой, если контракт не передан или не разобран).
    """
    raw = vars_block.get("contract")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _role_file(role: str) -> Path:
    """Вернуть путь к промпту роли.

    Args:
        role: Идентификатор роли (`product-manager`, `orchestrator`, ...).

    Returns:
        Путь к markdown-файлу промпта роли.
    """
    special = _SPECIAL_ROLE_FILES.get(role)
    if special is not None:
        return special
    return _ROLES_DIR / f"{role}.md"


def _read(path: Path) -> str:
    """Прочитать текстовый файл в UTF-8.

    Args:
        path: Путь к файлу.

    Returns:
        Содержимое файла.
    """
    return path.read_text(encoding="utf-8")


def transform_vars(vars_block: dict[str, Any]) -> dict[str, Any]:
    """Развернуть контракт кейса в переменные шаблона промпта.

    Args:
        vars_block: Переменные тест-кейса (содержат `contract`).

    Returns:
        Словарь переменных, которые подставит шаблон промпта.
    """
    contract = _contract(vars_block)
    role = str(contract.get("role") or vars_block.get("role") or "")
    mode = str(contract.get("mode") or vars_block.get("mode") or "auto")
    input_text = str(contract.get("input") or vars_block.get("input") or "")

    result: dict[str, Any] = {}

    if role:
        result["role"] = role
        role_path = _role_file(role)
        if not role_path.is_file():
            raise FileNotFoundError(f"нет промпта роли {role!r}: {role_path}")
        result["role_prompt"] = _read(role_path)

    if _RULES_FILE.exists():
        result["rules"] = _read(_RULES_FILE)

    # Гайд оркестратора НЕ подключается к запросу. Измерено на eval-прогоне:
    # с гайдом в промпте модель отвечала по гайду, а не по формату своей
    # роли (чужие ключи вместо полей ответа): 0 из 5 кейсов оркестратора
    # с гайдом против 5 из 5 без него. Рабочие части гайда перенесены в
    # `prompts/orchestrator.md`, сам гайд остался справочником для человека.

    result["mode"] = mode
    result["input"] = input_text
    return result


def get_transform(vars_block: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Точка входа для promptfoo (`transformVars`).

    Args:
        vars_block: Переменные тест-кейса.
        context: Контекст promptfoo (не используется).

    Returns:
        Словарь переменных, которые подставит шаблон промпта.
    """
    return transform_vars(vars_block)


if __name__ == "__main__":
    print(json.dumps(transform_vars({}), ensure_ascii=False))
