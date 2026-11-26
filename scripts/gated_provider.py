"""Провайдер eval с код-гейтом: пустая идея не доходит до модели.

Зачем. `promptfoo` не умеет отменять вызов провайдера по результату
трансформа, поэтому отсечь пустой вход «до LLM» можно только в самом
провайдере. Этот скрипт — exec-провайдер: он получает от promptfoo
`(prompt, options, context)`, как это делает `scripts/mock_provider.py`.

Логика:
- вход пустой → печатаем детерминированный ответ из
  `idea_to_spec.input_gate` и **не обращаемся к модели**;
- вход непустой → вызываем Ollama через общий клиент
  (`idea_to_spec.ollama_client`: лимиты, трейс, guard контекста, JSON-контракт)
  и печатаем её ответ.

Причина, по которой гейт нужен именно в коде: кейс `NEG-01-empty-idea`
падал на всех семи измеренных моделях (3B–12B, разные семейства) — на
пустом входе модель начинала прогон и писала артефакты. Значит, это не
задача модели, а входная ошибка.

Запуск (promptfoo вызывает так сам):
    exec:python3 ../scripts/gated_provider.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

#: Скрипт запускается из `scripts/`, пакет `idea_to_spec` лежит рядом.
#: Путь добавляется до импорта — иначе модуль не найдётся при запуске
#: exec-провайдера из другого каталога.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from idea_to_spec.input_gate import gate_input  # noqa: E402
from idea_to_spec.ollama_client import call_json  # noqa: E402


def _load_context(raw: str) -> dict[str, Any]:
    """Разобрать JSON-аргумент context.

    Args:
        raw: Строка с JSON.

    Returns:
        Словарь (пустой, если разбор не удался).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _vars(context: dict[str, Any]) -> dict[str, Any]:
    """Извлечь переменные тест-кейса.

    Args:
        context: Разобранный context.

    Returns:
        Словарь переменных (пустой, если их нет).
    """
    vars_block = context.get("vars")
    return vars_block if isinstance(vars_block, dict) else {}


def _contract(vars_block: dict[str, Any]) -> dict[str, Any]:
    """Извлечь контракт кейса из переменной `contract`.

    Args:
        vars_block: Переменные тест-кейса.

    Returns:
        Словарь контракта (пустой, если контракт не передан).
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


def _input_text(vars_block: dict[str, Any], contract: dict[str, Any]) -> str:
    """Получить вход кейса.

    Args:
        vars_block: Переменные тест-кейса.
        contract: Контракт кейса.

    Returns:
        Текст входа (пустая строка, если входа нет).
    """
    return str(contract.get("input") or vars_block.get("input") or "")


def _options(raw: str) -> dict[str, Any]:
    """Разобрать JSON-аргумент options.

    Args:
        raw: Строка с JSON.

    Returns:
        Словарь настроек (пустой, если разбор не удался).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _call_name(vars_block: dict[str, Any], contract: dict[str, Any]) -> str:
    """Имя вызова для трейса и сырого дампа.

    Args:
        vars_block: Переменные тест-кейса.
        contract: Контракт кейса.

    Returns:
        Идентификатор кейса (`ORCH-01-...`) или `gated`.
    """
    return str(contract.get("id") or vars_block.get("id") or "gated")


def main() -> int:
    """Точка входа exec-провайдера.

    Returns:
        Всегда 0 — ответ печатается в stdout.
    """
    prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    options = _options(sys.argv[2] if len(sys.argv) > 2 else "{}")
    context = _load_context(sys.argv[3] if len(sys.argv) > 3 else "{}")
    vars_block = _vars(context)
    contract = _contract(vars_block)

    gated = gate_input(_input_text(vars_block, contract))
    if gated is not None:
        print(gated["answer"])
        return 0

    # Ремонтный повтор при невалидном JSON делает клиент; печатаем ровно тот
    # текст, который вернула модель, — ассерт кейса должен видеть оригинал.
    _payload, reply = call_json(prompt, options, name=_call_name(vars_block, contract))
    print(reply.text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
