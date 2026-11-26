"""Многоходовый exec-провайдер: настоящий диалог вместо одного хода.

Зачем. Измерено (F023): `scripts/gated_provider.py` отправляет ровно одно
сообщение (`messages: [{role: user, content: prompt}]`), поэтому кейсы
режимов `chat` и `hybrid` проверяли один ход в режиме диалога, а не сам
диалог. Не покрыты: второй ход, реакция на ответ заказчика (факт с
источником «ответ заказчика»), критерий остановки диалога и развилка в
`hybrid`.

Этот провайдер закрывает разрыв:

1. сам вызывает Ollama (тот же HTTP API, что у `ollama:chat`), но по ходам;
2. берёт вопрос из ответа модели, находит в сценарии кейса пару
   «вопрос → ответ» и формирует следующий запрос С ИСТОРИЕЙ;
3. накапливает ходы, пока сценарий не кончится.

Сценарий лежит в контракте кейса (`eval/cases/roles.jsonl`):

    "dialogue": {
      "turns": [
        {"question_contains": "срок хранения", "answer": "12 месяцев (ответ заказчика)"}
      ]
    }

Кейс без сценария (`dialogue` отсутствует) обрабатывается как обычный
одноходовый вызов: провайдер не ломает существующий набор.

Запуск (promptfoo вызывает так сам):
    exec:python3 ../scripts/multi_turn_provider.py
"""

from __future__ import annotations

import itertools
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

from idea_to_spec.multi_turn import (  # noqa: E402
    DialogueTurn,
    build_history,
    run_turns,
)
from idea_to_spec.ollama_client import call_guarded, call_json  # noqa: E402


def _load_json(raw: str) -> dict[str, Any]:
    """Разобрать JSON-аргумент.

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


def _scenario(contract: dict[str, Any]) -> dict[str, Any]:
    """Извлечь сценарий диалога из контракта кейса.

    Args:
        contract: Контракт кейса.

    Returns:
        Блок `dialogue` (пустой, если сценария нет).
    """
    raw = contract.get("dialogue")
    return raw if isinstance(raw, dict) else {}


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


def _call_ollama(
    prompt: str,
    options: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    name: str = "turn",
) -> str:
    """Вызвать Ollama и вернуть текст ответа.

    Обвязка (параметры генерации, `num_ctx`, трейс, guard контекста) живёт в
    `idea_to_spec.ollama_client` — одна точка правды для обоих провайдеров.

    Args:
        prompt: Текст запроса (промпт роли с входом).
        options: Настройки провайдера (модель, параметры генерации).
        history: История переписки (пустая на первом ходе).
        name: Идентификатор вызова для трейса и сырого дампа (кейс и ход).

    Returns:
        Текст ответа модели.

    Raises:
        RuntimeError: Если Ollama недоступна или ответила ошибкой.
        ContextTruncatedError: Промпт вытеснен или ответ обрезан.
    """
    return call_guarded(prompt, options, history=history, name=name).text


def run_dialogue(
    prompt: str,
    options: dict[str, Any],
    scenario: dict[str, Any],
    mode: str = "",
    input_text: str = "",
    name: str = "",
) -> tuple[str, list[DialogueTurn]]:
    """Провести диалог по сценарию и вернуть последний ответ роли.

    Логика ходов — общая с mock-провайдером (`idea_to_spec.multi_turn.run_turns`),
    чтобы `eval-mock` воспроизводил ровно то, что проверяет реальный прогон.

    Args:
        prompt: Текст запроса (промпт роли с входом).
        options: Настройки провайдера.
        scenario: Блок `dialogue` контракта кейса.
        mode: Режим прогона.
        input_text: Исходный вход кейса.
        name: Идентификатор кейса для трейса и сырых дампов; пустая строка —
            кейс не назван, в имени остаётся только номер хода.

    Returns:
        Последний ответ роли и список состоявшихся ходов.
    """
    turn_number = itertools.count(1)
    prefix = f"{name}-" if name else ""

    def call_turn(current_prompt: str, turns: list[DialogueTurn]) -> str:
        """Вызвать модель для очередного хода, пометив ход номером."""
        return _call_ollama(
            current_prompt,
            options,
            build_history(turns),
            name=f"{prefix}turn{next(turn_number)}",
        )

    return run_turns(prompt, scenario, call_turn, mode=mode, input_text=input_text)


def _call_name(vars_block: dict[str, Any], contract: dict[str, Any]) -> str:
    """Имя вызова для трейса и сырого дампа.

    Args:
        vars_block: Переменные тест-кейса.
        contract: Контракт кейса.

    Returns:
        Идентификатор кейса (`SA-04-...`) или пустая строка, если кейс не назван.
    """
    return str(contract.get("id") or vars_block.get("id") or "")


def main() -> int:
    """Точка входа exec-провайдера.

    Returns:
        Всегда 0 — ответ печатается в stdout.
    """
    prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    options = _options(sys.argv[2] if len(sys.argv) > 2 else "{}")
    context = _load_json(sys.argv[3] if len(sys.argv) > 3 else "{}")
    vars_block = _vars(context)
    contract = _contract(vars_block)
    scenario = _scenario(contract)

    if not scenario:
        # Кейс без сценария — обычный одноходовый вызов. Ремонтный повтор при
        # невалидном JSON делает клиент; печатаем текст модели как есть.
        _payload, reply = call_json(prompt, options, name=_call_name(vars_block, contract))
        print(reply.text)
        return 0

    output, _turns = run_dialogue(
        prompt,
        options,
        scenario,
        mode=str(contract.get("mode") or ""),
        input_text=_input_text(vars_block, contract),
        name=_call_name(vars_block, contract),
    )
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
